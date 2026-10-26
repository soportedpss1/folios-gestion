# Registro de usuarios con aprobación de administrador

Fecha: 2026-10-26
Estado: aprobada en diseño (secciones A y B), pendiente de revisión de spec

## Objetivo

Permitir que cualquier visitante se registre desde la pantalla de login con
rol `operador`. La cuenta nace **desactivada** (`activo=False`) y solo puede
iniciar sesión cuando un administrador la aprueba (= la activa). Sin
migración ni cambio de modelo: el estado de aprobación es el propio flag
`activo`.

## Decisiones tomadas con el usuario

| Decisión | Elección |
|---|---|
| Estados del modelo | Sin columna nueva. Registro crea `activo=False`; aprobar = `activo=True` |
| Login con cuenta inactiva y contraseña correcta | Mensaje combinado (cubre pendiente y desactivada) |
| Acciones de aprobación | Solo "Aprobar" (activar). Rechazar = no activar / desactivar con el flujo existente |
| Disponibilidad del registro | Link siempre visible en el login |
| Rol del registro | Fijo `operador` (no elige rol) |

## Sección A — Registro y Login

### Registro

- Ruta nueva `GET/POST /auth/registro` en el blueprint `auth` (público, sin
  `login_required`).
- `RegistroForm` en `app/auth/forms.py`, espejo de `UsuarioForm` **sin `rol`**:
  - `name`: DataRequired, Length(3-255)
  - `username`: DataRequired, Length(3-50)
  - `email`: DataRequired, Email, Length(≤100)
  - `password`: DataRequired, Length(≥6)
  - `confirm_password`: DataRequired, EqualTo('password')
- Crea `Usuario(name, username, email, rol='operador', activo=False)` +
  `set_password`. `activo=False` explícito (el default de columna es `True`).
- Duplicados (username|email en consulta previa, e `IntegrityError` por
  carrera): mensaje existente `DUP_USUARIO`, re-render del form.
- Rate limit propio: `@limiter.limit("5/minute")` (login es 10/min).
- Éxito → `flash('Cuenta creada correctamente. Un administrador debe aprobarla
  antes de que pueda iniciar sesión.', 'success')` → redirect `/auth/login`.
- Auditoría: `log_audit(user.id, 'INSERT', 'usuarios', user.id, None,
  {username, email, rol, activo: False})` tras `flush()` — actor = usuario
  nuevo (único posible viniendo de anónimo).

### Login (`app/auth/__init__.py::login`)

Contraseña se verifica primero; el estado no se filtra sin contraseña correcta:

```
if user and user.check_password(...):
    if user.activo:            → login normal (como hoy)
    else:                      → flash(mensaje combinado, 'warning'), sin sesión
else:                          → 'Usuario o contraseña incorrectos.' (como hoy)
```

Mensaje combinado:

> Su cuenta no está activa. Si acaba de registrarse, un administrador debe
> aprobarla. Contacte al administrador del sistema.

### Templates

- `app/templates/auth/registro.html`: extiende `base.html`, bloque
  `auth_content`, misma estructura `login-split` del login (aside de marca
  `d-none d-lg-flex` + panel de formulario) para que ambas pantallas se
  vean como una sola familia.
- `app/templates/auth/login.html`: link *"Crear una cuenta"* bajo el submit,
  hacia `auth.registro`.

## Sección B — Aprobación en /usuarios

### Endpoint `POST /usuarios/<id>/aprobar`

- `@login_required` + `@permiso_requerido('usuarios.gestionar')` — un no-admin
  con el *grant* también aprueba (aprobar no es escalada; coherente con cómo
  los grants suman capacidad hoy).
- `get_or_404(Usuario, id)`.
- Si `user.activo` ya es `True` → flash `'Ese usuario ya está activo.'`
  (`info`) y redirect al index — idempotente, sin audit.
- No aplica la lógica de último-admin (activar nunca degrada/desactiva).
- Acción: `user.activo = True` +
  `log_audit(current_user.id, 'UPDATE', 'usuarios', id,
  {'activo': False}, {'activo': True})` + commit.
- Flash `'Usuario aprobado exitosamente.'` (`success`) → redirect index.

### Template `app/templates/usuarios/index.html`

- Columna Acciones: para cada usuario **inactivo** (y que no sea el
  `current_user`, que siempre es activo), botón "Aprobar": form POST con
  `csrf_token()`, `data-confirm` con título *"¿Aprobar este usuario? Se
  activará la cuenta."*, icono `fa-user-check`, clase
  `btn btn-sm btn-outline-success`, `aria-label="Aprobar usuario <username>"`.
- El badge de estado existente ("Activo"/"Inactivo") no cambia; no hay badge
  "Pendiente" (con `activo` solo no se distingue pendiente de desactivado).
- Editar/Desactivar existentes quedan como están.

### Seguridad

- CSRF: global vía Flask-WTF; los formularios POST llevan token.
- Rate limits: registro 5/min propio; `/usuarios/aprobar` cubierto por el
  límite global 300/h.
- Enumeración: registro responde `DUP_USUARIO` (consistente con la gestión de
  usuarios; sistema interno, login con rate limit). La visibilidad de estado
  en login exige contraseña correcta.

## Fuera de alcance

- Transferencias de folios y demás campos de fecha (tarea anterior, hecha).
- Notificación por email al admin o al usuario (no hay infraestructura de
  correo).
- Estados de aprobación diferenciados (columna `aprobado`/`estado`) —
  descartado por decisión del usuario.
- Cambiar quién puede crear usuarios con rol `admin` (guard existente intacto).

## Tests (TDD, `tests/test_registro_usuarios.py`)

1. Login muestra el link "Crear una cuenta".
2. Registro crea operador inactivo + flash de pendiente + redirect login.
3. Login con cuenta inactiva y contraseña correcta → mensaje combinado, sin
   sesión (no redirect a dashboard).
4. Login con contraseña incorrecta en cuenta inactiva → mensaje genérico.
5. Registro duplicado (username o email) → `DUP_USUARIO`, no crea.
6. Registro con datos inválidos (email malformado, contraseña corta, confirm
   desigual) → no crea.
7. Rate limit de registro 5/min (`limiter_client`).
8. Aprobar: admin activa la cuenta + flash + `audit_logs` UPDATE con actor
   admin.
9. `POST /aprobar` sin sesión → 302 sin activar; con operador (sin permiso) →
   rechazado, sin activar.
10. Aprobar usuario ya activo → mensaje "ya está activo", sin audit nuevo.
11. `/usuarios` muestra el botón "Aprobar" a un admin, solo para inactivos.
12. Registro deja `audit_logs` INSERT con actor = usuario nuevo.
