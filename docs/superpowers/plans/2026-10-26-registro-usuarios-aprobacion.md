# Registro de usuarios con aprobación — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Autorregistro público de operadores desde el login con cuenta nace desactivada (`activo=False`) que un administrador aprueba (= activa) desde `/usuarios`.

**Architecture:** Sin migración ni cambio de modelo — el estado de aprobación es el flag `activo` existente. Ruta nueva `POST/GET /auth/registro` en el blueprint `auth`; el login gana un branch para cuenta inactiva con contraseña correcta; aprobación = `POST /usuarios/<id>/aprobar` con `permiso_requerido('usuarios.gestionar')` + audit log.

**Tech Stack:** Flask 3 + Flask-WTF/WTForms + Flask-Login + Flask-Limiter + Jinja2/Bootstrap 5, pytest (SQLite in-memory).

**Spec:** `docs/superpowers/specs/2026-10-26-registro-usuarios-aprobacion-design.md`

## Global Constraints

- Textos de usuario en **español**, exactos según spec:
  - Registro éxito: `Cuenta creada exitosamente. Un administrador debe aprobarla antes de que pueda iniciar sesión.` (flash `success`; "exitosamente" lo exige `test_flashes_sin_correctamente`)
  - Login inactiva + contraseña correcta: `Su cuenta no está activa. Si acaba de registrarse, un administrador debe aprobarla. Contacte al administrador del sistema.` (flash `warning`)
  - Aprobar éxito: `Usuario aprobado exitosamente.` (flash `success`)
  - Aprobar ya activo: `Ese usuario ya está activo.` (flash `info`)
  - Duplicado en registro: `DUP_USUARIO` existente de `app/services/mensajes.py`
- Registro crea SIEMPRE `rol='operador'` y `activo=False` **explícito** (default de columna es `True`).
- Sin cambios de modelo ni migraciones.
- Rate limit registro: `5/minute` SOLO en `methods=["POST"]` (GET no consume cuota).
- CSRF global: todo form POST lleva `{{ form.hidden_tag() }}` o `csrf_token()`.
- Auditoría con `log_audit` de `app/services/audit.py` (signature:
  `log_audit(user_id, accion, tabla, registro_id, datos_anteriores=None, datos_nuevos=None)`).
- Un solo usuario autenticado por test (fixture `app` reusa app context; `g._login_user` se comparte entre clients del mismo test).
- Tests: `venv/bin/python -m pytest` desde la raíz del repo.

## Review Focus

Inputs/fallos que la spec implica pero ningún caso nominal cubre; cada línea tiene su test en la tarea dueña:

1. **Visitante ya autenticado abre `/auth/registro`** → esperado: redirect a dashboard como en login (no un segundo formulario de registro). → Task 1, `test_registro_autenticado_redirige_a_dashboard`.
2. **Fuerza bruta de registro**: el GET del formulario no debe quemar la cuota; 6º POST → 429. → Task 1, `test_registro_rate_limit_solo_post` (6 POST → 429, luego GET → 200).
3. **Contraseña incorrecta en cuenta inactiva** → esperado: mensaje genérico, el estado no se filtra sin contraseña correcta. → Task 2, `test_login_inactiva_password_mala_es_generico`.
4. **Doble click en Aprobar** → idempotente: segundo POST dice "ya está activo" y NO escribe un segundo audit. → Task 3, `test_aprobar_ya_activo_es_idempotente`.
5. **No-admin con grant `usuarios.gestionar` aprueba** → los grants suman capacidad; esperado: aprueba con éxito. → Task 3, `test_aprobar_con_grant_usuarios_gestionar`.

---

### Task 1: Registro público (`/auth/registro`)

**Files:**
- Modify: `app/auth/forms.py` (agregar `RegistroForm`)
- Modify: `app/auth/__init__.py` (agregar ruta `registro`, importar form)
- Create: `app/templates/auth/registro.html`
- Modify: `app/templates/auth/login.html` (link "Crear una cuenta" tras el submit)
- Test: `tests/test_registro_usuarios.py` (archivo nuevo)

**Interfaces:**
- Consumes: `Usuario` (`app/models/usuario.py`, campos `name/username/email/rol/activo` + `set_password`), `log_audit` (`app/services/audit.py`), `DUP_USUARIO` (`app/services/mensajes.py`), `limiter` (`app/extensions.py`), fixtures `client/app/admin_client/auth_client/limiter_client/make_user` (`tests/conftest.py`).
- Produces (para Tasks 2-3):
  - `RegistroForm` con campos `name, username, email, password, confirm_password, submit` (validadores espejo de `UsuarioForm` sin `rol`).
  - Ruta `auth.registro` → `GET/POST /auth/registro`.
  - Helper de tests `make_inactivo(username) -> Usuario` en `tests/test_registro_usuarios.py` (crea `rol='operador'`, `activo=False`, password `pass12345`), usado por Tasks 2 y 3.

- [ ] **Step 1: Escribir los tests fallidos**

En `tests/test_registro_usuarios.py`:

```python
"""Registro público de operadores + aprobación por administrador."""

from app.extensions import db
from app.models.usuario import Usuario
from tests.conftest import make_user

REGISTRO = {'name': 'Nuevo Usuario', 'username': 'nuevo',
            'email': 'nuevo@test.local', 'password': 'secret123',
            'confirm_password': 'secret123'}


def make_inactivo(username='pendiente'):
    """Usuario operador sin aprobar (como lo crea el registro)."""
    user = Usuario(name='Pendiente Test', username=username,
                   email=f'{username}@test.local', rol='operador',
                   activo=False)
    user.set_password('pass12345')
    db.session.add(user)
    db.session.commit()
    return user


def test_login_muestra_link_de_registro(client):
    html = client.get('/auth/login').get_data(as_text=True)
    assert 'Crear una cuenta' in html, 'falta el link al registro en el login'
    assert '/auth/registro' in html


def test_registro_crea_operador_inactivo(client, app):
    resp = client.post('/auth/registro', data=REGISTRO, follow_redirects=True)
    html = resp.get_data(as_text=True)
    assert 'Un administrador debe aprobarla' in html, 'sin flash de pendiente'
    user = Usuario.query.filter_by(username='nuevo').one()
    assert user.rol == 'operador'
    assert user.activo is False, 'la cuenta nace sin aprobar (activo=False)'
    assert user.check_password('secret123')
    assert client.get('/dashboard').status_code == 302, 'el registro creó sesión'


def test_registro_autenticado_redirige_a_dashboard(auth_client, app):
    resp = auth_client.get('/auth/registro')
    assert resp.status_code == 302
    assert '/dashboard' in resp.headers['Location'], \
        'autenticado no debe ver el formulario de registro'


def test_registro_duplicado_no_crea(client, app):
    client.post('/auth/registro', data=REGISTRO, follow_redirects=True)
    otro = dict(REGISTRO, email='otro@test.local')
    resp = client.post('/auth/registro', data=otro, follow_redirects=True)
    assert 'ya está en uso' in resp.get_data(as_text=True)
    assert Usuario.query.filter_by(username='nuevo').count() == 1


def test_registro_datos_invalidos_no_crea(client, app):
    malo = dict(REGISTRO, email='no-es-email', password='corto',
                confirm_password='distinto')
    resp = client.post('/auth/registro', data=malo, follow_redirects=True)
    assert resp.status_code == 200
    assert Usuario.query.count() == 0


def test_registro_rate_limit_solo_post(limiter_client):
    statuses = []
    for i in range(6):
        resp = limiter_client.post(
            '/auth/registro',
            data=dict(REGISTRO, username=f'user{i}',
                      email=f'user{i}@test.local'),
        )
        statuses.append(resp.status_code)
    assert statuses[-1] == 429, f'esperaba 429 en la 6ª petición, llegó {statuses}'
    assert limiter_client.get('/auth/registro').status_code == 200, \
        'el GET del formulario no consume la cuota del rate limit'


def test_registro_deja_audit_insert(client, app):
    client.post('/auth/registro', data=REGISTRO, follow_redirects=True)
    user = Usuario.query.filter_by(username='nuevo').one()
    from app.models.audit_log import AuditLog
    log = AuditLog.query.filter_by(
        user_id=user.id, accion='INSERT', tabla='usuarios',
        registro_id=user.id).one()
    assert log.datos_nuevos['activo'] is False
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `venv/bin/python -m pytest tests/test_registro_usuarios.py -q`
Expected: 7 fallas — `404` en rutas `/auth/registro` y link ausente (el helper no existe hasta que se escribe el archivo, pero los tests fallan por feature ausente, no por import).

- [ ] **Step 3: Implementar `RegistroForm` + ruta `registro` + templates**

- `app/auth/forms.py`: `class RegistroForm(FlaskForm)` espejo de `UsuarioForm` de `app/usuarios/forms.py` sin `rol` ni `submit` homónimo; `submit = SubmitField('Crear Cuenta')`. Mismos validadores y mensajes en español (name Length 3-255, username Length 3-50, email Email+Length≤100, password Length≥6, confirm EqualTo).
- `app/auth/__init__.py`:
  - `@auth_bp.route('/registro', methods=['GET', 'POST'])` + `@limiter.limit("5/minute", methods=["POST"])`.
  - Guard: `if current_user.is_authenticated: return redirect(url_for('dashboard.index'))`.
  - En POST válido: dup check por `username|email` (query) → `flash(DUP_USUARIO, 'danger')`; crear `Usuario(..., rol='operador', activo=False)` + `set_password` + `db.session.add` + `db.session.flush()` + `log_audit(user.id, 'INSERT', 'usuarios', user.id, None, {'username': ..., 'email': ..., 'rol': 'operador', 'activo': False})` + `db.session.commit()` dentro de `try` con `except IntegrityError` → rollback + `DUP_USUARIO`.
  - Éxito → flash de éxito (texto exacto de Global Constraints) → `redirect(url_for('auth.login'))`.
- `app/templates/auth/registro.html`: extiende `base.html`, bloque `auth_content`, misma estructura `login-split` de `auth/login.html` (aside de marca `d-none d-lg-flex` + panel de formulario); form con `hidden_tag()`, campos con label/icono como el login, errores por campo, submit `data-loading`, y link *"¿Ya tiene cuenta? Inicie sesión"* → `auth.login`.
- `app/templates/auth/login.html`: justo después del `</form>` dentro de `.login-form-wrap`, link `<a href="{{ url_for('auth.registro') }}">Crear una cuenta</a>`.

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `venv/bin/python -m pytest tests/test_registro_usuarios.py -q`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add app/auth/forms.py app/auth/__init__.py app/templates/auth/registro.html app/templates/auth/login.html tests/test_registro_usuarios.py
git commit -m "feat(auth): registro público de operadores pendientes de aprobación"
```

---

### Task 2: Login — cuenta inactiva

**Files:**
- Modify: `app/auth/__init__.py::login`
- Test: `tests/test_registro_usuarios.py`

**Interfaces:**
- Consumes: `make_inactivo` de Task 1.
- Produces: comportamiento del login para `activo=False` (mensaje combinado); sin nombres nuevos.

- [ ] **Step 1: Escribir los tests fallidos**

Append a `tests/test_registro_usuarios.py`:

```python
def test_login_cuenta_inactiva_mensaje_combinado(client, app):
    make_inactivo('pendiente1')
    resp = client.post('/auth/login', data={
        'username': 'pendiente1', 'password': 'pass12345',
    }, follow_redirects=True)
    html = resp.get_data(as_text=True)
    assert ('Su cuenta no está activa. Si acaba de registrarse, un '
            'administrador debe aprobarla') in html, \
        'falta el mensaje combinado para cuenta inactiva'
    assert client.get('/dashboard').status_code == 302, 'creó sesión igual'


def test_login_inactiva_password_mala_es_generico(client, app):
    make_inactivo('pendiente2')
    resp = client.post('/auth/login', data={
        'username': 'pendiente2', 'password': 'mala',
    }, follow_redirects=True)
    html = resp.get_data(as_text=True)
    assert 'Usuario o contraseña incorrectos.' in html
    assert 'no está activa' not in html, \
        'sin contraseña correcta no se filtra el estado de la cuenta'
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `venv/bin/python -m pytest tests/test_registro_usuarios.py::test_login_cuenta_inactiva_mensaje_combinado tests/test_registro_usuarios.py::test_login_inactiva_password_mala_es_generico -q`
Expected: FAIL #1 (hoy `activo=False` cae al genérico `Usuario o contraseña incorrectos.`), FAIL #2 (afirma `'no está activa' not in` — con el genérico pasa… ver nota).

Nota de implementador: el segundo test puede pasar desde el inicio (el estado ya no se muestra). Si pasa en RED, el primero es el que prueba la feature; el segundo queda como guarda de regresión. No forzar su fallo.

- [ ] **Step 3: Implementar el branch de cuenta inactiva en `login`**

En `app/auth/__init__.py::login`, reestructurar la condición (contraseña primero, estado después):

```python
if user and user.check_password(form.password.data):
    if user.activo:
        # cuerpo actual de login (login_user, session.permanent, flash
        # 'Sesión iniciada exitosamente.', next_page seguro, redirect)
    else:
        flash('Su cuenta no está activa. Si acaba de registrarse, un '
              'administrador debe aprobarla. Contacte al administrador '
              'del sistema.', 'warning')
else:
    flash('Usuario o contraseña incorrectos.', 'danger')
```

Texto exacto de los flashes en Global Constraints.

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `venv/bin/python -m pytest tests/test_registro_usuarios.py -q`
Expected: todos los del archivo passed (los de Task 1 siguen verdes)

- [ ] **Step 5: Commit**

```bash
git add app/auth/__init__.py tests/test_registro_usuarios.py
git commit -m "feat(auth): login distingue cuenta pendiente con mensaje combinado"
```

---

### Task 3: Aprobación en `/usuarios`

**Files:**
- Modify: `app/usuarios/__init__.py` (ruta `aprobar`)
- Modify: `app/templates/usuarios/index.html` (botón Aprobar)
- Test: `tests/test_registro_usuarios.py`

**Interfaces:**
- Consumes: `make_inactivo` (Task 1), `log_audit`, `get_or_404` (`app/services/queries.py`), `permiso_requerido` (`app/decorators.py`), `make_user` y fixtures (`tests/conftest.py`), `PermisoUsuario` (`app/models/permiso_usuario.py`).
- Produces: `POST /usuarios/<id>/aprobar` → endpoint `usuarios.aprobar` (los tests y el template lo referencian por `url_for('usuarios.aprobar', id=...)`).

- [ ] **Step 1: Escribir los tests fallidos**

Append a `tests/test_registro_usuarios.py` (importar arriba: `from app.models.audit_log import AuditLog`, `from app.models.permiso_usuario import PermisoUsuario`):

```python
def test_aprobar_activa_cuenta_y_audita(admin_client, app, admin):
    user = make_inactivo('pendiente3')
    resp = admin_client.post(f'/usuarios/{user.id}/aprobar',
                             follow_redirects=True)
    assert 'Usuario aprobado exitosamente.' in resp.get_data(as_text=True)
    db.session.refresh(user)
    assert user.activo is True, 'aprobar no activó la cuenta'
    log = AuditLog.query.filter_by(
        accion='UPDATE', tabla='usuarios', registro_id=user.id).one()
    assert log.user_id == admin.id, 'el audit debe tener al admin como actor'
    assert log.datos_anteriores == {'activo': False}
    assert log.datos_nuevos == {'activo': True}


def test_aprobar_sin_sesion_no_activa(client, app):
    user = make_inactivo('pendiente4')
    resp = client.post(f'/usuarios/{user.id}/aprobar')
    assert resp.status_code == 302
    assert db.session.get(Usuario, user.id).activo is False


def test_aprobar_operador_sin_permiso_no_activa(auth_client, app):
    user = make_inactivo('pendiente5')
    resp = auth_client.post(f'/usuarios/{user.id}/aprobar',
                            follow_redirects=True)
    assert 'No tiene permisos' in resp.get_data(as_text=True)
    db.session.refresh(user)
    assert user.activo is False


def test_aprobar_con_grant_usuarios_gestionar(client, app):
    lector = make_user('lector_aprueba', 'lectura')
    db.session.add(PermisoUsuario(user_id=lector.id,
                                  permiso='usuarios.gestionar'))
    db.session.commit()
    user = make_inactivo('pendiente6')
    client.post('/auth/login',
                data={'username': 'lector_aprueba', 'password': 'pass12345'})
    resp = client.post(f'/usuarios/{user.id}/aprobar', follow_redirects=True)
    assert 'Usuario aprobado exitosamente.' in resp.get_data(as_text=True)
    db.session.refresh(user)
    assert user.activo is True, 'un grant de usuarios.gestionar debe aprobar'


def test_aprobar_ya_activo_es_idempotente(admin_client, app):
    activo = make_user('activo_existente', 'operador')
    resp = admin_client.post(f'/usuarios/{activo.id}/aprobar',
                             follow_redirects=True)
    assert 'Ese usuario ya está activo.' in resp.get_data(as_text=True)
    assert AuditLog.query.filter_by(
        accion='UPDATE', tabla='usuarios', registro_id=activo.id).count() == 0, \
        'reaprobación no debe escribir audit'


def test_index_muestra_boton_aprobar_solo_inactivos(admin_client, app):
    inactivo = make_inactivo('pendiente7')
    html = admin_client.get('/usuarios/').get_data(as_text=True)
    assert f'aria-label="Aprobar usuario {inactivo.username}"' in html, \
        'sin botón de aprobación para el inactivo'
    assert 'Aprobar usuario adminuser' not in html, \
        'los activos no llevan botón de aprobar'
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `venv/bin/python -m pytest tests/test_registro_usuarios.py -q`
Expected: FAIL — 404 en `/aprobar` (5 tests de endpoint) y botón ausente (1 test); los de Task 1-2 siguen verdes.

- [ ] **Step 3: Implementar ruta `aprobar` y botón en el template**

- `app/usuarios/__init__.py`:

```python
@usuarios_bp.route('/<int:id>/aprobar', methods=['POST'])
@login_required
@permiso_requerido('usuarios.gestionar')
def aprobar(id):
    ...
```

Cuerpo: `get_or_404(Usuario, id)`; si `user.activo` → flash `'Ese usuario ya está activo.'` (`info`) y redirect index; si no → `user.activo = True` +
`log_audit(current_user.id, 'UPDATE', 'usuarios', user.id, {'activo': False}, {'activo': True})` + commit +
flash `'Usuario aprobado exitosamente.'` (`success`) + redirect index. Sin lógica de último-admin (activar nunca degrada).

- `app/templates/usuarios/index.html`, columna Acciones, antes del link de editar:

```jinja
{% if not u.activo %}
<form method="POST" action="{{ url_for('usuarios.aprobar', id=u.id) }}" class="d-inline" data-confirm data-title="¿Aprobar este usuario? Se activará la cuenta.">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <button type="submit" class="btn btn-sm btn-outline-success" title="Aprobar" aria-label="Aprobar usuario {{ u.username }}">
        <i class="fas fa-user-check" aria-hidden="true"></i>
    </button>
</form>
{% endif %}
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `venv/bin/python -m pytest tests/test_registro_usuarios.py -q`
Expected: todos passed

- [ ] **Step 5: Correr la suite completa**

Run: `venv/bin/python -m pytest -q`
Expected: todos passed (baseline 724 + ~14 nuevos), 13 skipped

- [ ] **Step 6: Commit**

```bash
git add app/usuarios/__init__.py app/templates/usuarios/index.html tests/test_registro_usuarios.py
git commit -m "feat(usuarios): aprobación de cuentas registradas desde /usuarios"
```
