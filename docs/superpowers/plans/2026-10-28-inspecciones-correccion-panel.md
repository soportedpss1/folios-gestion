# Corrección desde Inspecciones (paneles JSON) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que las correcciones de los 6 chequeos de inspecciones se hagan desde el propio módulo (modal con fetch) reusando los MISMOS endpoints dueños vía un modo JSON, sin duplicar forms ni reglas.

**Architecture:** `quiere_json()` detecta `Accept: application/json`; las 4 rutas dueñas ganan ramas JSON (GET → `campos_html` de un partial compartido; POST → `ok` o `400` con errores) sin tocar el flujo no-JSON. Un modal genérico en `inspecciones/detalle.html` + `inspecciones_panel.js` hacen el ciclo GET→POST→recarga.

**Tech Stack:** Flask + WTForms/Flask-WTF (CSRF), Jinja2 partials, fetch API + Bootstrap 5 modal, `AppToast` (main.js), pytest/SQLite.

**Spec:** `docs/superpowers/specs/2026-10-28-inspecciones-correccion-panel-design.md` (autoridad vinculante)

## Global Constraints

- Texto en español; todo `flash(...)` con "exitosamente" y **nunca** "correctamente" (invariante `tests/test_ui_lote5.py::test_flashes_sin_correctamente`). Toast JS pineado: `Corregido exitosamente.` / fallo: `No se pudo guardar. Intente de nuevo.`
- Fechas UI: dd/mm/aaaa (`FechaLatinaField` ya acepta ISO como fallback en forms; el test escribe `05/03/2026`).
- Contrato JSON exacto (spec): GET-json → `200 {ok: true, campos_html}`; POST válido → `200 {ok: true}`; error de campo → `400 {ok: false, errores: {campo: primer_mensaje}}`; error de negocio → `400 {ok: false, error: "<msg>"}`. Sin header JSON → comportamiento actual **intacto**.
- Detección única: `quiere_json()` en `app/utils.py` = `request.accept_mimetypes.best == 'application/json'`. Verificado empíricamente: sin header → `None`; `Accept: */*` → `'*/*'`; navegación `text/html,…` → `text/html` — la igualdad estricta **nunca** dispara la rama por accidente (un fetch sin header explícito tampoco).
- Partials (`_form*.html`): **solo campos + errores** — sin `<form>`, sin `csrf_token` (el `hidden_tag()` queda en `edit.html`; el modal pone su propio csrf estático), sin botones.
- Sin migraciones, sin cambios de modelo, sin permisos nuevos. `CHEQUEOS`/queries intactos.
- Tests: `venv/bin/python -m pytest ...`. Un solo usuario autenticado por test (regla de `tests/conftest.py`). CSRF deshabilitado en tests.
- El árbol puede traer cambios sin commitear ajenos: **cada commit usa `git add <archivos explícitos>`**.
- Las ramas JSON cuelgan de los MISMOS decorators (`@login_required` + `@permiso_requerido(...)`) — el modo no otorga permisos.

## Review Focus

Los cinco fallos que la spec implica pero que ningún test trivial atrapa — cada línea con su test en el task dueño:

1. **Rama JSON no debe alterar el flujo normal**: un POST sin `Accept: application/json` debe seguir haciendo redirect/flash igual que hoy → `test_entregas_edit_post_normal_no_es_json` (Task 1) + suites existentes de los 4 módulos.
2. **CSRF en el modal**: un solo token por form (partials sin `hidden_tag`, modal con csrf estático) → asserts `assert 'csrf_token' not in data['campos_html']` (Task 1) y su equivalente en `_form_estado.html` (Task 4); doble token rechazaría todo POST con error 400 de CSRF.
3. **Error de negocio ≠ error de campo en JSON**: entrega de folio devuelto con centro cambiado → `400 {error}` (sin clave `errores`) → `test_entregas_edit_json_error_negocio` (Task 1).
4. **`cambiar_estado` gana GET**: GET sin header JSON no debe filtrar el form (redirect a details) → `test_cambiar_estado_get_normal_no_es_json` (Task 4).
5. **Ajuste de los 2 tests existentes sin pérdida de cobertura**: siguen exigiendo la URL dueña EXACTA (ahora en `data-url`) → `test_detalle_muestra_hallazgo_y_link_corregir` y `test_fechas_futuras_link_por_modulo` ajustados (Task 5).

---

### Task 1: Helper `quiere_json()` + modo JSON en `entregas.edit` + partial

**Files:**
- Modify: `app/utils.py` (helper)
- Modify: `app/entregas/__init__.py` (ramas JSON en `edit`)
- Create: `app/templates/entregas/_form.html`; Modify: `app/templates/entregas/edit.html` (include)
- Test: `tests/test_inspecciones_panel.py` (archivo nuevo)

**Interfaces:**
- Consumes: `EntregaEditForm` y la ruta `edit` actuales; fixtures `admin_client, app, tipo, centro, operador`; `make_folio` de `tests/conftest.py`.
- Produces (Tasks 2-5):
  - `quiere_json() -> bool` en `app/utils.py` (Tasks 2-4 lo importan).
  - Partial `entregas/_form.html` con vars `form`, `entrega`: solo `{{ form.folio_id }}` (hidden), display de folio, `fechaEntrega`, `centroId` + sus `errors` — sin form/csrf/botones.
  - JSON shapes de la spec (GET/POST ok/POST `errores`/POST `error`).

- [ ] **Step 1: Escribir los tests fallidos**

`tests/test_inspecciones_panel.py`:

```python
"""Paneles de corrección: modo JSON en las rutas dueñas."""

from datetime import date

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.centro import Centro
from app.models.devolucion_folio import DevolucionFolio
from app.models.entrega_folio import EntregaFolio
from tests.conftest import make_folio

JSON = {'Accept': 'application/json'}


def _entrega(tipo, centro, operador, numero=8000, rangoId=40):
    folio = make_folio(tipo, anio=2026, numero=numero, rangoId=rangoId,
                       estado='entregado')
    db.session.flush()
    entrega = EntregaFolio(folio_id=folio.id, fechaEntrega=date(2026, 3, 1),
                           centroId=centro.id, userId=operador.id)
    db.session.add(entrega)
    db.session.commit()
    return entrega


def test_entregas_edit_json_get_campos(admin_client, app, tipo, centro,
                                       operador):
    entrega = _entrega(tipo, centro, operador)
    resp = admin_client.get(f'/entregas/{entrega.id}/edit', headers=JSON)
    data = resp.get_json()
    assert data['ok'] is True
    assert 'name="fechaEntrega"' in data['campos_html']
    assert 'csrf_token' not in data['campos_html'], 'el modal pone su csrf'


def test_entregas_edit_json_post_ok(admin_client, app, tipo, centro,
                                    operador):
    entrega = _entrega(tipo, centro, operador, numero=8001, rangoId=41)
    resp = admin_client.post(
        f'/entregas/{entrega.id}/edit', headers=JSON,
        data={'folio_id': entrega.folio_id, 'fechaEntrega': '05/03/2026',
              'centroId': centro.id})
    assert resp.get_json() == {'ok': True}
    assert db.session.get(EntregaFolio, entrega.id).fechaEntrega == date(2026, 3, 5)
    assert AuditLog.query.filter_by(accion='UPDATE', tabla='entrega_folios',
                                    registro_id=entrega.id).count() == 1


def test_entregas_edit_json_post_fecha_futura(admin_client, app, tipo, centro,
                                              operador):
    entrega = _entrega(tipo, centro, operador, numero=8002, rangoId=42)
    resp = admin_client.post(
        f'/entregas/{entrega.id}/edit', headers=JSON,
        data={'folio_id': entrega.folio_id, 'fechaEntrega': '01/01/2030',
              'centroId': centro.id})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['ok'] is False and 'fechaEntrega' in data['errores']
    assert 'posterior a hoy' in data['errores']['fechaEntrega']
    assert db.session.get(EntregaFolio, entrega.id).fechaEntrega == date(2026, 3, 1)
    assert AuditLog.query.filter_by(tabla='entrega_folios',
                                    registro_id=entrega.id).count() == 0


def test_entregas_edit_json_error_negocio(admin_client, app, tipo, centro,
                                          operador):
    entrega = _entrega(tipo, centro, operador, numero=8003, rangoId=43)
    otro = Centro(name='Otro Centro', telefono='555', direccion='Calle 2',
                  activo=True)
    db.session.add(otro)
    db.session.add(DevolucionFolio(
        folio_id=entrega.folio_id, fechaDevolucion=date(2026, 3, 10),
        centroId=centro.id, userId=operador.id))
    db.session.commit()
    # El folio ya fue devuelto: mover su entrega a otro centro lo rechaza.
    resp = admin_client.post(
        f'/entregas/{entrega.id}/edit', headers=JSON,
        data={'folio_id': entrega.folio_id, 'fechaEntrega': '01/03/2026',
              'centroId': otro.id})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['ok'] is False and 'ya fue devuelto' in data['error']
    assert 'errores' not in data
    assert db.session.get(EntregaFolio, entrega.id).centroId == centro.id


def test_entregas_edit_post_normal_no_es_json(admin_client, app, tipo, centro,
                                              operador):
    # Sin Accept: application/json → flujo viejo intacto (redirect al índice).
    entrega = _entrega(tipo, centro, operador, numero=8004, rangoId=44)
    resp = admin_client.post(
        f'/entregas/{entrega.id}/edit',
        data={'folio_id': entrega.folio_id, 'fechaEntrega': '05/03/2026',
              'centroId': centro.id})
    assert resp.status_code == 302
    assert '/entregas' in resp.headers['Location']
    assert resp.mimetype != 'application/json'
```

- [ ] **Step 2: Verificar RED**

Run: `venv/bin/python -m pytest tests/test_inspecciones_panel.py -q`
Expected: FAIL — el GET con Accept json devuelve HTML (200, `get_json()` → None → AttributeError o assert).

- [ ] **Step 3: Implementar**

a) `app/utils.py`: `def quiere_json(): return request.accept_mimetypes.best == 'application/json'` (importar `request` si no está).

b) Extraer de `entregas/edit.html` a `entregas/_form.html`: el contenido de `<form>` desde `{{ form.hidden_tag() }}` **excluido** hasta antes de `<hr>` — o sea solo el `div.row.g-3` con los 3 campos + errores (sin form, sin csrf, sin Cancelar/submit). `edit.html` queda: `<form method="POST" data-loading>{{ form.hidden_tag() }}{% include 'entregas/_form.html' %}<hr>…botones…</form>`.

c) `entregas.edit` — 3 puntos de inserción (el resto intacto):
- Tras poblar choices y, en GET, los datos: `if request.method == 'GET' and quiere_json(): return jsonify(ok=True, campos_html=render_template('entregas/_form.html', form=form, entrega=entrega))`.
- Cada `return render_template('entregas/edit.html', ...)` que es **respuesta a POST fallido** (devolución-conflicto ×2, IntegrityError): anteceder `if quiere_json(): return jsonify(ok=False, error='<el mismo mensaje del flash>'), 400` (el flash solo en modo normal).
- `if form.validate_on_submit():` → al final del éxito, antes del flash/redirect: `if quiere_json(): return jsonify(ok=True)`.
- Invalid de WTForms (cae en el render final del GET/POST): `if quiere_json(): return jsonify(ok=False, errores={k: v[0] for k, v in form.errors.items()}), 400`.
- `jsonify` se importa donde ya esté (Blueprint file imports `jsonify` — verificar; si no, añadirlo).

- [ ] **Step 4: Verificar GREEN**

Run: `venv/bin/python -m pytest tests/test_inspecciones_panel.py -q`
Expected: PASS (5 tests)

- [ ] **Step 5: No regresión del módulo dueño + Commit**

Run: `venv/bin/python -m pytest tests/test_entregas*.py tests/test_ui_lote5.py -q`
Expected: PASS (los tests viejos de entregas + invariante de toasts)

```bash
git add app/utils.py app/entregas/__init__.py app/templates/entregas/_form.html app/templates/entregas/edit.html tests/test_inspecciones_panel.py
git commit -m "feat(entregas): modo JSON en edición de entrega + partial"
```

---

### Task 2: Modo JSON en `devoluciones.edit` + partial

**Files:**
- Modify: `app/devoluciones/__init__.py`
- Create: `app/templates/devoluciones/_form.html`; Modify: `app/templates/devoluciones/edit.html`
- Test: `tests/test_inspecciones_panel.py`

**Interfaces:**
- Consumes: `quiere_json()` (Task 1), patrón exacto de Task 1.
- Produce: partial `devoluciones/_form.html` con vars `form`, `devolucion` (Task 5).

- [ ] **Step 1: Escribir los tests fallidos**

Append a `tests/test_inspecciones_panel.py` (helper nuevo):

```python
def _devolucion(tipo, centro, operador, numero=8100, rangoId=50):
    folio = make_folio(tipo, anio=2026, numero=numero, rangoId=rangoId,
                       estado='devuelto')
    db.session.flush()
    dev = DevolucionFolio(folio_id=folio.id,
                          fechaDevolucion=date(2026, 3, 10),
                          centroId=centro.id, userId=operador.id)
    db.session.add(dev)
    db.session.commit()
    return dev


def test_devoluciones_edit_json_get_campos(admin_client, app, tipo, centro,
                                           operador):
    dev = _devolucion(tipo, centro, operador)
    data = admin_client.get(f'/devoluciones/{dev.id}/edit',
                            headers=JSON).get_json()
    assert data['ok'] is True
    assert 'name="fechaDevolucion"' in data['campos_html']
    assert 'csrf_token' not in data['campos_html']


def test_devoluciones_edit_json_post_ok(admin_client, app, tipo, centro,
                                        operador):
    dev = _devolucion(tipo, centro, operador, numero=8101, rangoId=51)
    resp = admin_client.post(
        f'/devoluciones/{dev.id}/edit', headers=JSON,
        data={'folio_id': dev.folio_id, 'fechaDevolucion': '05/03/2026',
              'centroId': centro.id})
    assert resp.get_json() == {'ok': True}
    assert db.session.get(DevolucionFolio, dev.id).fechaDevolucion == date(2026, 3, 5)
    assert AuditLog.query.filter_by(accion='UPDATE', tabla='devolucion_folios',
                                    registro_id=dev.id).count() == 1


def test_devoluciones_edit_json_post_fecha_futura(admin_client, app, tipo,
                                                  centro, operador):
    dev = _devolucion(tipo, centro, operador, numero=8102, rangoId=52)
    resp = admin_client.post(
        f'/devoluciones/{dev.id}/edit', headers=JSON,
        data={'folio_id': dev.folio_id, 'fechaDevolucion': '01/01/2030',
              'centroId': centro.id})
    assert resp.status_code == 400
    assert 'posterior a hoy' in resp.get_json()['errores']['fechaDevolucion']
    assert db.session.get(DevolucionFolio, dev.id).fechaDevolucion == date(2026, 3, 10)
```

- [ ] **Step 2: Verificar RED**

Run: `venv/bin/python -m pytest tests/test_inspecciones_panel.py -q -k devoluciones`
Expected: FAIL (JSON no existe aún → `get_json()` None)

- [ ] **Step 3: Implementar**

Mismo patrón que Task 1: partial `devoluciones/_form.html` (div.row con folio hidden+display, fechaDevolucion, centroId + errors) incluido desde `edit.html`; ramas JSON en GET/POST de `edit` (aquí solo hay errores WTForms + IntegrityError como `error`, y éxito → `{ok:true}`).

- [ ] **Step 4: Verificar GREEN**

Run: `venv/bin/python -m pytest tests/test_inspecciones_panel.py -q`
Expected: PASS (los 5 de Task 1 + 3 nuevos = 8)

- [ ] **Step 5: No regresión + Commit**

Run: `venv/bin/python -m pytest tests/test_devoluciones*.py -q`
Expected: PASS

```bash
git add app/devoluciones/__init__.py app/templates/devoluciones/_form.html app/templates/devoluciones/edit.html tests/test_inspecciones_panel.py
git commit -m "feat(devoluciones): modo JSON en edición de devolución + partial"
```

---

### Task 3: Modo JSON en `recepcion.edit` + partial

**Files:**
- Modify: `app/recepcion/__init__.py`
- Create: `app/templates/recepcion/_form.html`; Modify: `app/templates/recepcion/edit.html`
- Test: `tests/test_inspecciones_panel.py`

**Interfaces:**
- Consumes: `quiere_json()` (Task 1); helpers `make_rango` y `hallazgos` de `tests/test_inspecciones.py` (import: `from tests.test_inspecciones import make_rango, hallazgos`); `rangos_corruptos, formatear_rangos_corruptos` del servicio.
- Produce: partial `recepcion/_form.html` con vars `form`, `recepcion` — campos (fecha, anioCert, tipoCert, folioInicial, folioFinal, usuario + errors). **La alerta de preview (div.alert-info) y el `extra_js` se QUEDAN en `edit.html`**, fuera del include.

- [ ] **Step 1: Escribir los tests fallidos**

Append a `tests/test_inspecciones_panel.py`:

```python
from app.services.inspecciones import (  # añadir a los imports del archivo
    rangos_corruptos, formatear_rangos_corruptos)
from tests.test_inspecciones import make_rango, hallazgos


def test_recepcion_edit_json_get_campos(admin_client, app, tipo, operador):
    r = make_rango(tipo, operador, ini=1, fin=100, rangoId=60)
    data = admin_client.get(f'/recepcion/{r.id}/edit',
                            headers=JSON).get_json()
    assert data['ok'] is True
    assert 'name="folioInicial"' in data['campos_html']
    assert 'csrf_token' not in data['campos_html']


def test_recepcion_edit_json_corrige_solape(admin_client, app, tipo, operador):
    a = make_rango(tipo, operador, ini=1, fin=100, rangoId=61)
    b = make_rango(tipo, operador, ini=50, fin=150, rangoId=62)  # solapa
    assert hallazgos(rangos_corruptos(), formatear_rangos_corruptos)  # RED
    resp = admin_client.post(
        f'/recepcion/{b.id}/edit', headers=JSON,
        data={'fecha': '01/03/2026', 'anioCert': 2026, 'tipoCert': tipo.id,
              'folioInicial': 101, 'folioFinal': 150, 'usuario': operador.id})
    assert resp.get_json() == {'ok': True}
    assert hallazgos(rangos_corruptos(), formatear_rangos_corruptos) == []
    assert AuditLog.query.filter_by(accion='UPDATE',
                                    tabla='recepcion_folios',
                                    registro_id=b.id).count() == 1


def test_recepcion_edit_json_post_crea_solape(admin_client, app, tipo,
                                              operador):
    a = make_rango(tipo, operador, ini=1, fin=100, rangoId=63)
    b = make_rango(tipo, operador, ini=101, fin=200, rangoId=64)
    resp = admin_client.post(
        f'/recepcion/{b.id}/edit', headers=JSON,
        data={'fecha': '01/03/2026', 'anioCert': 2026, 'tipoCert': tipo.id,
              'folioInicial': 50, 'folioFinal': 200, 'usuario': operador.id})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['ok'] is False and data.get('errores')
    assert db.session.get(RecepcionFolio, b.id).folioInicial == 101
```

Añadir `from app.models.recepcion_folio import RecepcionFolio` a los imports del archivo si falta.

- [ ] **Step 2: Verificar RED**

Run: `venv/bin/python -m pytest tests/test_inspecciones_panel.py -q -k recepcion`
Expected: FAIL (modo JSON inexistente)

- [ ] **Step 3: Implementar**

- Partial: de `recepcion/edit.html` extraer el `div.row.g-3` completo **sin** el bloque `div.col-12` de la alerta (esa se queda tras el `{% include %}` en `edit.html`, junto a su script `extra_js` — sin cambios).
- Ramas JSON en `recepcion.edit`, mismos 4 puntos que Task 1. Casos especiales de esta ruta:
  - Folios usados (`flash + redirect recepcion.index`) → `if quiere_json(): return jsonify(ok=False, error=<mensaje>), 400` antes del flash.
  - IntegrityError → igual, `error`.
  - Errores WTForms (solape u otros) → `errores` map.

- [ ] **Step 4: Verificar GREEN**

Run: `venv/bin/python -m pytest tests/test_inspecciones_panel.py -q`
Expected: PASS (8 + 3 = 11)

- [ ] **Step 5: No regresión + Commit**

Run: `venv/bin/python -m pytest tests/test_recepcion*.py tests/test_inspeccion*.py -q`
Expected: PASS

```bash
git add app/recepcion/__init__.py app/templates/recepcion/_form.html app/templates/recepcion/edit.html tests/test_inspecciones_panel.py
git commit -m "feat(recepcion): modo JSON en edición de recepción + partial"
```

---

### Task 4: `cambiar_estado` con GET + modo JSON + partial de estado

**Files:**
- Modify: `app/folios/__init__.py` (`cambiar_estado`: `methods=['GET','POST']`, ramas JSON)
- Create: `app/templates/folios/_form_estado.html`; Modify: `app/templates/folios/details.html` (include del form header)
- Test: `tests/test_inspecciones_panel.py`

**Interfaces:**
- Consumes: `quiere_json()` (Task 1); el form de estado actual del header de `details.html` (select `estado` + csrf + botón, dentro de `puede('folios.actualizar')` y de la condición de incoherencia).
- Produce: partial `folios/_form_estado.html` con var `folio` — **solo el `<select name="estado">` con las 3 opciones** (sin form/csrf/botón — details.html los mantiene alrededor del include; el modal pone los suyos). JSON shapes igual que las rutas WTForms pero sin mapa de campos: error → `{ok: false, error}`.

- [ ] **Step 1: Escribir los tests fallidos**

Append a `tests/test_inspecciones_panel.py`:

```python
def _folio_incoherente(tipo):
    folio = make_folio(tipo, anio=2026, numero=8200, rangoId=70,
                       estado='entregado')
    db.session.commit()
    return folio


def test_cambiar_estado_json_get_campos(admin_client, app, tipo):
    folio = _folio_incoherente(tipo)
    data = admin_client.get(f'/folios/{folio.id}/estado',
                            headers=JSON).get_json()
    assert data['ok'] is True
    assert 'name="estado"' in data['campos_html']
    assert 'csrf_token' not in data['campos_html']
    assert 'perdido' not in data['campos_html'], 'perdido es flujo propio'


def test_cambiar_estado_json_post_ok(admin_client, app, tipo):
    folio = _folio_incoherente(tipo)
    resp = admin_client.post(f'/folios/{folio.id}/estado', headers=JSON,
                             data={'estado': 'disponible'})
    assert resp.get_json() == {'ok': True}
    assert db.session.get(Folio, folio.id).estado == 'disponible'
    assert AuditLog.query.filter_by(accion='UPDATE', tabla='folios',
                                    registro_id=folio.id).count() == 1


def test_cambiar_estado_json_post_invalido(admin_client, app, tipo):
    folio = _folio_incoherente(tipo)
    resp = admin_client.post(f'/folios/{folio.id}/estado', headers=JSON,
                             data={'estado': 'perdido'})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['ok'] is False and 'inválido' in data['error']
    assert db.session.get(Folio, folio.id).estado == 'entregado'
    assert AuditLog.query.filter_by(tabla='folios',
                                    registro_id=folio.id).count() == 0


def test_cambiar_estado_get_normal_no_es_json(admin_client, app, tipo):
    # GET sin header JSON: no filtra el form, redirige al detalle.
    folio = _folio_incoherente(tipo)
    resp = admin_client.get(f'/folios/{folio.id}/estado')
    assert resp.status_code == 302
    assert f'/folios/{folio.id}' in resp.headers['Location']
```

(`Folio` y `AuditLog` ya importados en el archivo; añadir `from app.models.folio import Folio` si el archivo de panel no lo tiene.)

- [ ] **Step 2: Verificar RED**

Run: `venv/bin/python -m pytest tests/test_inspecciones_panel.py -q -k cambiar_estado`
Expected: FAIL — 404 (GET no permitido en la ruta) y/o JSON inexistente.

- [ ] **Step 3: Implementar**

a) Extraer el `<select name="estado">...</select>` del form de estado en `details.html` a `folios/_form_estado.html`; `details.html` lo referencia con `{% include 'folios/_form_estado.html' %}` (form/csrf/botón quedan donde están; la condición de incoherencia también).

b) `cambiar_estado`: `methods=['GET', 'POST']` + tres ramas:
- GET: `if quiere_json(): return jsonify(ok=True, campos_html=render_template('folios/_form_estado.html', folio=folio))` — sin JSON → `return redirect(url_for('folios.details', id=folio.id))`.
- POST inválido/igual: los dos flashes existentes → `if quiere_json(): return jsonify(ok=False, error='<mensaje>'), 400` (el flash solo en modo normal).
- POST éxito: `if quiere_json(): return jsonify(ok=True)` antes del flash/redirect.

- [ ] **Step 4: Verificar GREEN + no regresión de details**

Run: `venv/bin/python -m pytest tests/test_inspecciones_panel.py tests/test_folios_estado.py tests/test_folios_perdidos.py -q`
Expected: PASS (los 11 anteriores + 4 + folios)

- [ ] **Step 5: Commit**

```bash
git add app/folios/__init__.py app/templates/folios/_form_estado.html app/templates/folios/details.html tests/test_inspecciones_panel.py
git commit -m "feat(folios): cambiar_estado con GET y modo JSON + partial"
```

---

### Task 5: Modal en inspecciones, botones de panel y JS

**Files:**
- Modify: `app/services/inspecciones.py` (añadir `PERMISOS_EDITAR`)
- Modify: `app/inspecciones/__init__.py` (vista `detalle`: `h['url_panel']`)
- Modify: `app/templates/inspecciones/detalle.html` (botones + modal + block extra_js)
- Create: `app/static/js/inspecciones_panel.js`
- Modify: `tests/test_inspecciones.py` (ajustar 2 tests)
- Test: `tests/test_inspecciones_panel.py`

**Interfaces:**
- Consumes: los 4 endpoints con modo JSON (Tasks 1-4), partials (`entregas/_form.html` etc. renderizados por el GET dueño), la vista `detalle` (hoy: `h['url'] = url_for(URLS_CORREGIR[h['modulo']], id=h['registro_id'])`), helpers `make_cadena`/`make_rango`/`hallazgos` de `tests/test_inspecciones.py`, `AppToast` (global vía main.js), `{% block extra_js %}` de `base.html`.
- **Ojo con folios**: `URLS_CORREGIR['folios']` = `folios.details` — el link plano de estado sigue hacia el detalle (allí vive el form de estado condicional), pero el `data-url` del panel debe apuntar al **endpoint JSON** `/folios/<id>/estado`. La vista agrega `h['url_panel']`: `url_for('folios.cambiar_estado', id=…)` si `h['modulo'] == 'folios'`, si no = `h['url']`.
- Produce: `PERMISOS_EDITAR` en `app/services/inspecciones.py`:
  `{'recepcion': 'recepcion.gestionar', 'entregas': 'entregas.gestionar', 'devoluciones': 'devoluciones.gestionar', 'folios': 'folios.actualizar'}`.

- [ ] **Step 1: Escribir los tests fallidos**

Append a `tests/test_inspecciones_panel.py` (imports nuevos: `import re`, `from app.models.permiso_usuario import PermisoUsuario`, `from tests.conftest import make_user`, `from tests.test_inspecciones import make_cadena` — `make_rango` ya se importó en Task 3):

```python
def _los_seis_chequeos(tipo, centro, operador):
    """Un hallazgo (mínimo) por cada chequeo, en sus módulos dueños."""
    # entrega-antes-recepcion (entregas)
    make_cadena(tipo, centro, operador, numero=9000, rangoId=80,
                fecha_rec=date(2026, 3, 10), fecha_ent=date(2026, 3, 1))
    # devolucion-antes-entrega + centro-devolucion-distinto (devoluciones)
    f = make_cadena(tipo, centro, operador, numero=9001, rangoId=81,
                    fecha_ent=date(2026, 3, 10), fecha_dev=date(2026, 3, 1))
    otro = Centro(name='Otro Centro', telefono='555', direccion='Calle 2',
                  activo=True)
    db.session.add(otro)
    db.session.flush()
    f.devolucion.centroId = otro.id
    # fechas-futuras: recepcion + entregas + devoluciones (3 hallazgos)
    make_cadena(tipo, centro, operador, numero=9002, rangoId=82,
                fecha_rec=date(2027, 1, 1))
    make_cadena(tipo, centro, operador, numero=9003, rangoId=83,
                fecha_rec=date(2026, 3, 1), fecha_ent=date(2027, 1, 1))
    make_cadena(tipo, centro, operador, numero=9004, rangoId=84,
                fecha_rec=date(2026, 3, 1), fecha_ent=date(2026, 3, 1),
                fecha_dev=date(2027, 1, 1))
    # rangos-corruptos (recepcion) + estado-inconsistente (folios)
    make_rango(tipo, operador, ini=500, fin=400, rangoId=85)
    make_cadena(tipo, centro, operador, numero=9005, rangoId=86,
                estado='entregado')
    db.session.commit()


ESPERADOS = {'entrega-antes-recepcion': 1, 'devolucion-antes-entrega': 1,
             'fechas-futuras': 3, 'centro-devolucion-distinto': 1,
             'rangos-corruptos': 1, 'estado-inconsistente': 1}


def test_detalle_botones_panel_los_seis_chequeos(admin_client, app, tipo,
                                                 centro, operador):
    _los_seis_chequeos(tipo, centro, operador)
    prefijos = set()
    for clave, n in ESPERADOS.items():
        html = admin_client.get(f'/inspecciones/{clave}').get_data(as_text=True)
        assert html.count('data-panel') == n, f'{clave}: {n} esperados'
        prefijos |= set(re.findall(r'data-url="(/[^"/]+)', html))
    assert {'/entregas', '/devoluciones', '/recepcion', '/folios'} <= prefijos
    assert 'modal-corregir' in admin_client.get(
        '/inspecciones/entrega-antes-recepcion').get_data(as_text=True)


def test_detalle_link_plano_sin_permiso_de_edicion(app, client, tipo, centro,
                                                   operador):
    make_cadena(tipo, centro, operador, numero=9100, rangoId=90,
                fecha_rec=date(2026, 3, 10), fecha_ent=date(2026, 3, 1))
    entrega_id = db.session.query(EntregaFolio).one().id
    lector = make_user('lector_panel', 'lectura')
    db.session.add(PermisoUsuario(user_id=lector.id,
                                  permiso='inspecciones.ver'))
    db.session.commit()
    client.post('/auth/login', data={'username': lector.username,
                                     'password': 'pass12345'})
    html = client.get('/inspecciones/entrega-antes-recepcion') \
        .get_data(as_text=True)
    assert f'<a href="/entregas/{entrega_id}/edit"' in html, 'sin link plano'
    assert 'data-panel' not in html, 'lector sin edición no debe ver panel'
```

Ajuste de los 2 tests existentes en `tests/test_inspecciones.py` — hoy solo exigen que la URL dueña aparezca como substring suelta (pasarían con `href` o con `data-url`); se endurecen para exigir el **atributo** `data-url` (cobertura del botón de panel, no solo de la URL):

```python
# test_detalle_muestra_hallazgo_y_link_corregir — excluir el href suelto:
    assert f'data-url="/entregas/{entrega.id}/edit"' in html, 'sin panel'

# test_fechas_futuras_link_por_modulo — los 3 substrings sueltos → data-url:
    assert f'data-url="/recepcion/{rec.id}/edit"' in html
    assert f'data-url="/entregas/{ent.id}/edit"' in html
    assert f'data-url="/devoluciones/{dev.id}/edit"' in html
```

(El resto de esos tests — fechas en detalle, etc. — sin cambios.)

- [ ] **Step 2: Verificar RED**

Run: `venv/bin/python -m pytest tests/test_inspecciones_panel.py tests/test_inspecciones.py -q`
Expected: FAIL — sin `data-panel`/`modal-corregir` (hoy hay `<a href>`) → los 2 ajustados + los 2 nuevos fallan.

- [ ] **Step 3: Implementar**

a) `app/services/inspecciones.py`: `PERMISOS_EDITAR` (dict del bloque Interfaces) junto a `URLS_CORREGIR`.

b) `app/inspecciones/__init__.py` (vista `detalle`), tras la línea que construye `h['url']`:
`h['url_panel'] = url_for('folios.cambiar_estado', id=h['registro_id']) if h['modulo'] == 'folios' else h['url']`.

c) `inspecciones/detalle.html` — cada fila: si `puede(PERMISOS_EDITAR[h['modulo']])` →
`<button type="button" class="btn btn-sm btn-outline-primary" data-panel data-url="{{ h['url_panel'] }}" data-titulo="{{ h['titulo'] }}"><i class="fas fa-pen me-1"></i>Corregir</button>`; si no → el `<a href="{{ h['url'] }}">` actual (para folios: el detalle, como hasta ahora).

d) Al final de `detalle.html`: modal único

```html
<div class="modal fade" id="modal-corregir" tabindex="-1">
  <div class="modal-dialog modal-lg modal-dialog-scrollable">
    <div class="modal-content">
      <div class="modal-header"><h5 class="modal-title" id="panel-titulo"></h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
      <form id="panel-form" method="POST">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <div class="modal-body"><div id="panel-campos"></div>
          <div id="panel-error" class="alert alert-danger d-none" role="alert"></div></div>
        <div class="modal-footer">
          <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Cerrar</button>
          <button type="submit" form="panel-form" class="btn btn-primary">Guardar</button>
        </div>
      </form>
    </div>
  </div>
</div>
{% block extra_js %}<script src="{{ url_for('static', filename='js/inspecciones_panel.js') }}"></script>{% endblock %}
```

e) `app/static/js/inspecciones_panel.js` — comportamiento (cuerpo libre, contratos fijos):
1. Click `[data-panel]`: título = `data-titulo`; GET `data-url` con `Accept: application/json` → `#panel-campos.innerHTML = campos_html` (limpiar `#panel-error`); abrir modal (`new bootstrap.Modal(...)`).
2. Submit de `#panel-form`: `preventDefault`; `fetch(action, {method:'POST', body: new FormData(form), headers:{'Accept':'application/json'}})`.
3. `200` → `AppToast.mostrar('Corregido exitosamente.', 'success')`, cerrar, `location.reload()`.
4. `400` JSON con `errores`: por campo → buscar `[name="<campo>"]`, marcar `.is-invalid` + insertar `.invalid-feedback` con el mensaje (limpiar marcas previas antes). Con `error`: mostrarlo en `#panel-error` (quitar `d-none`).
5. No-JSON (p. ej. 302/HTML por permiso) o red caída → `AppToast.mostrar('No se pudo guardar. Intente de nuevo.', 'danger')`, modal abierto.

- [ ] **Step 4: Verificar GREEN**

Run: `venv/bin/python -m pytest tests/test_inspecciones_panel.py tests/test_inspecciones.py -q`
Expected: PASS (los 15 del panel anteriores + 2 nuevos = 17, y los de inspecciones con los 2 ajustados)

- [ ] **Step 5: Suite completa**

Run: `venv/bin/python -m pytest -q`
Expected: PASS, 0 failures — total esperado **791 passed** (774 base + 17 nuevos: 5+3+3+4+2), 13 skipped

- [ ] **Step 6: Commit**

```bash
git add app/services/inspecciones.py app/inspecciones/__init__.py app/templates/inspecciones/detalle.html app/static/js/inspecciones_panel.js tests/test_inspecciones_panel.py tests/test_inspecciones.py
git commit -m "feat(inspecciones): paneles de corrección modal con reuso de endpoints"
```
