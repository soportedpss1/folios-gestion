# Módulo de Inspecciones — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detectar errores humanos ya registrados (fechas erróneas, estados y rangos incoherentes) en recepciones, entregas y devoluciones, y llevar al usuario a corregirlos con las pantallas de edición existentes.

**Architecture:** Nuevo blueprint `inspecciones` (solo lectura) cuyos 6 chequeos viven como queries paginables en `app/services/inspecciones.py` (registro `CHEQUEOS`), con link "Corregir" a la edición del módulo dueño. Única adición a un módulo existente: `POST /folios/<id>/estado` (hoy el estado no es editable en la UI), patrón `perder`/`recuperar`.

**Tech Stack:** Flask blueprint + SQLAlchemy `session.query` (union_all, EXISTS correlacionados) + Jinja2/Bootstrap 5 + macro `render_pagination`. Tests pytest con SQLite in-memory.

**Spec:** `docs/superpowers/specs/2026-10-26-inspecciones-design.md`

## Global Constraints

- Texto en español; todo `flash(...)` con "exitosamente" y **nunca** "correctamente" (invariante `tests/test_ui_lote5.py::test_flashes_sin_correctamente`).
- Fechas en UI: dd/mm/aaaa (helper `dmy()` en el servicio; en templates `{{ ...|localtime }}` solo para datetime).
- Permiso nuevo, texto exacto: `'inspecciones.ver': ('Ver inspecciones de datos', 'admin')` en `app/services/permisos.py`.
- Sin migraciones ni cambios de modelo: solo lectura sobre tablas existentes + el campo `estado` ya existente.
- Tests: `venv/bin/python -m pytest ...`. Un solo usuario autenticado por test (regla de `tests/conftest.py`).
- Forms HTML con `csrf_token` oculto (CSRF ya deshabilitado en tests por convención).
- El árbol de trabajo trae cambios sin commitear ajenos a este plan (feature "fecha no futura"): **cada commit usa `git add <archivos explícitos>`, nunca `git add -A/.`**.
- Cada chequeo devuelve una query **con `order_by` incluido** (la paginación sin orden estable solapa páginas).

## Review Focus

Los cinco fallos que la spec implica pero que ningún test trivial atrapa — cada línea con su test en el task dueño:

1. **Falsos positivos**: datos sanos no deben aparecer en ningún chequeo → tests `*_no_alerta` por chequeo (Tasks 1-3).
2. **Solape de rangos sin dedupe**: dos rangos solapados deben dar 2 hallazgos, no 4 (y no omitir ninguno) → `test_rangos_corruptos_detecta_solape_sin_duplicar` con conteo exacto (Task 2).
3. **Límite "hoy no es futuro"** y enlace al módulo dueño correcto en `fechas-futuras` → `test_fechas_futuras_ignora_hoy` (Task 1) + `test_fechas_futuras_link_por_modulo` con los 3 hrefs (Task 4).
4. **Paginación inestable** (sin `order_by` → páginas solapadas/perdidas) → `test_detalle_pagina_estable` con 26 hallazgos: 25 en página 1, el 26º solo en página 2 (Task 4).
5. **Payload manipulado en `cambiar_estado`** (`perdido`, flags `digitado/escaneado/nulo`, cadena vacía) → `test_cambiar_estado_invalido_rechazado`: sin cambio y sin audit (Task 5).

---

### Task 1: Servicio — chequeos de orden de fechas (3 checks)

**Files:**
- Create: `app/services/inspecciones.py`
- Test: `tests/test_inspecciones.py` (archivo nuevo)

**Interfaces:**
- Consumes: modelos `RecepcionFolio, Folio, EntregaFolio, DevolucionFolio`; fixtures `app, tipo, centro, operador` y helpers `make_folio` (`tests/conftest.py`, hace `flush`, no commit); `date.today()`.
- Produces (Tasks 2-4):
  - `dmy(f: date|None) -> str` → `'dd/mm/aaaa'` o `'-'`.
  - `entrega_antes_recepcion() / devolucion_antes_entrega() / fechas_futuras() -> Query` — columnas con nombre; `order_by` incluido.
  - `formatear_entrega_antes_recepcion(row) / formatear_devolucion_antes_entrega(row) / formatear_fechas_futuras(row) -> dict` con claves exactas `titulo`, `detalle`, `modulo`, `registro_id` (modulo ∈ `recepcion|entregas|devoluciones|folios`).
  - `URLS_CORREGIR: dict` → `{'recepcion': 'recepcion.edit', 'entregas': 'entregas.edit', 'devoluciones': 'devoluciones.edit', 'folios': 'folios.details'}`.
  - `CHEQUEOS: OrderedDict` con las 3 claves `'entrega-antes-recepcion'`, `'devolucion-antes-entrega'`, `'fechas-futuras'`; cada entrada `{'titulo', 'descripcion', 'query', 'formatear'}` (`query`/`formatear` son las funciones, sin llamar).
  - Test helpers en `tests/test_inspecciones.py`: `make_cadena(...)` y `hallazgos(query, formatear)` (Tasks 2-3 los importan de este archivo).

- [ ] **Step 1: Escribir los tests fallidos**

En `tests/test_inspecciones.py`. Imports: `from datetime import date`, `from app.extensions import db`, modelos `RecepcionFolio, EntregaFolio, DevolucionFolio`, `from app.services.inspecciones import (CHEQUEOS, entrega_antes_recepcion, devolucion_antes_entrega, fechas_futuras, formatear_entrega_antes_recepcion, formatear_devolucion_antes_entrega, formatear_fechas_futuras)`, `from tests.conftest import make_folio`.

Helpers (también los usan Tasks 2-3):

```python
def make_cadena(tipo, centro, user, *, numero=1000, rangoId=1,
                fecha_rec=date(2026, 3, 1), fecha_ent=None, fecha_dev=None,
                estado=None):
    """Recepción de un folio + opcional entrega/devolución. Devuelve el Folio.

    estado default derivado: con fecha_ent → 'entregado'; con fecha_dev →
    'devuelto'; si no → 'disponible'. `estado` explícito permite crear
    estados incoherentes para los chequeos."""
    rec = RecepcionFolio(fecha=fecha_rec, anioCert=2026, tipoCert_id=tipo.id,
                         folioInicial=numero, folioFinal=numero,
                         rangoId=rangoId, userId=user.id)
    db.session.add(rec)
    folio = make_folio(tipo, anio=2026, numero=numero, rangoId=rangoId,
                       estado=estado or ('entregado' if fecha_ent else
                                         'devuelto' if fecha_dev else 'disponible'))
    if fecha_ent:
        db.session.add(EntregaFolio(folio_id=folio.id, fechaEntrega=fecha_ent,
                                    centroId=centro.id, userId=user.id))
    if fecha_dev:
        db.session.add(DevolucionFolio(folio_id=folio.id,
                                       fechaDevolucion=fecha_dev,
                                       centroId=centro.id, userId=user.id))
    db.session.commit()
    return folio


def hallazgos(query, formatear):
    return [formatear(r) for r in query.all()]
```

Tests:

```python
def test_entrega_antes_recepcion_detecta(app, tipo, centro, operador):
    # entrega 01/03/2026 < recepción 10/03/2026
    folio = make_cadena(tipo, centro, operador,
                        fecha_rec=date(2026, 3, 10), fecha_ent=date(2026, 3, 1))
    res = hallazgos(entrega_antes_recepcion(), formatear_entrega_antes_recepcion)
    assert len(res) == 1
    assert res[0]['modulo'] == 'entregas'
    assert res[0]['registro_id']  # id de la EntregaFolio
    assert f'Folio {folio.folio}' in res[0]['titulo']
    assert '01/03/2026' in res[0]['detalle'] and '10/03/2026' in res[0]['detalle']


def test_entrega_antes_recepcion_no_alerta_orden_correcto(app, tipo, centro, operador):
    make_cadena(tipo, centro, operador, numero=2000, rangoId=2,
                fecha_rec=date(2026, 3, 1), fecha_ent=date(2026, 3, 10))
    make_cadena(tipo, centro, operador, numero=3000, rangoId=3,
                fecha_rec=date(2026, 3, 1))          # sin entrega
    assert hallazgos(entrega_antes_recepcion(),
                     formatear_entrega_antes_recepcion) == []


def test_devolucion_antes_entrega_detecta(app, tipo, centro, operador):
    folio = make_cadena(tipo, centro, operador, fecha_ent=date(2026, 3, 10),
                        fecha_dev=date(2026, 3, 1))
    res = hallazgos(devolucion_antes_entrega(), formatear_devolucion_antes_entrega)
    assert len(res) == 1
    assert res[0]['modulo'] == 'devoluciones'
    assert f'Folio {folio.folio}' in res[0]['titulo']
    assert '01/03/2026' in res[0]['detalle'] and '10/03/2026' in res[0]['detalle']


def test_devolucion_antes_entrega_no_alerta_orden_correcto(app, tipo, centro, operador):
    make_cadena(tipo, centro, operador, numero=2000, rangoId=2,
                fecha_ent=date(2026, 3, 1), fecha_dev=date(2026, 3, 10))
    assert hallazgos(devolucion_antes_entrega(),
                     formatear_devolucion_antes_entrega) == []


def test_fechas_futuras_cubre_los_tres_modulos(app, tipo, centro, operador):
    make_cadena(tipo, centro, operador, numero=1000, rangoId=1,
                fecha_rec=date(2027, 1, 1))
    make_cadena(tipo, centro, operador, numero=2000, rangoId=2,
                fecha_rec=date(2026, 3, 1), fecha_ent=date(2027, 1, 1))
    make_cadena(tipo, centro, operador, numero=3000, rangoId=3,
                fecha_rec=date(2026, 3, 1), fecha_ent=date(2026, 3, 1),
                fecha_dev=date(2027, 1, 1))
    res = hallazgos(fechas_futuras(), formatear_fechas_futuras)
    assert len(res) == 3
    por_modulo = {h['modulo']: h for h in res}
    assert set(por_modulo) == {'recepcion', 'entregas', 'devoluciones'}
    assert por_modulo['recepcion']['registro_id']  # id de la RecepcionFolio
    assert por_modulo['entregas']['titulo'].startswith('Entrega')
    assert all('01/01/2027' in h['detalle'] for h in res)


def test_fechas_futuras_ignora_hoy_y_el_pasado(app, tipo, centro, operador):
    # El límite es hoy: hoy NO es futuro (date.today(), hora local).
    make_cadena(tipo, centro, operador, numero=4000, rangoId=4,
                fecha_rec=date.today(), fecha_ent=date(2026, 1, 1),
                fecha_dev=date(2026, 1, 2))
    assert hallazgos(fechas_futuras(), formatear_fechas_futuras) == []


def test_chequeos_incluye_las_tres_claves():
    assert list(CHEQUEOS)[:3] == ['entrega-antes-recepcion',
                                  'devolucion-antes-entrega', 'fechas-futuras']
    for c in CHEQUEOS.values():
        assert c['titulo'] and c['descripcion']
        assert callable(c['query']) and callable(c['formatear'])
```

- [ ] **Step 2: Verificar RED**

Run: `venv/bin/python -m pytest tests/test_inspecciones.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.inspecciones'`

- [ ] **Step 3: Implementar el servicio en `app/services/inspecciones.py`**

Enfoque (firmas exactas arriba; el cuerpo lo escribe el implementador):

- `dmy(f)` → `f.strftime('%d/%m/%Y') if f else '-'`.
- `URLS_CORREGIR` (lo consume Task 4): `{'recepcion': 'recepcion.edit', 'entregas': 'entregas.edit', 'devoluciones': 'devoluciones.edit', 'folios': 'folios.details'}`.
- `entrega_antes_recepcion()`: `db.session.query` con `EntregaFolio.id.label('registro_id')`, `EntregaFolio.fechaEntrega`, `RecepcionFolio.fecha`, `Folio.folio`; joins: `EntregaFolio → Folio (folio_id)` y `Folio → RecepcionFolio (Folio.rangoId == RecepcionFolio.rangoId)`; `filter(EntregaFolio.fechaEntrega < RecepcionFolio.fecha)`; `order_by(EntregaFolio.id)`.
- `devolucion_antes_entrega()`: columnas `DevolucionFolio.id.label('registro_id')`, `DevolucionFolio.fechaDevolucion`, `EntregaFolio.fechaEntrega`, `Folio.folio`; join `DevolucionFolio → EntregaFolio (mismo folio_id)` y `→ Folio`; `filter(fechaDevolucion < fechaEntrega)`; `order_by(DevolucionFolio.id)`.
- `fechas_futuras()`: `hoy = date.today()`; tres `db.session.query(literal('<modulo>').label('modulo'), <Modelo>.id.label('registro_id'), <fecha>.label('fecha')).filter(<fecha> > hoy)` — `recepcion`/`fecha`, `entregas`/`fechaEntrega`, `devoluciones`/`fechaDevolucion` — unidos con `.union_all(...)` y `.order_by('modulo', 'registro_id')`. (Solo columnas crudas: el UNION no admite CONCAT portable entre SQLite y MySQL; el contexto lo da el link de corrección.)
- `formatear_fechas_futuras`: `titulo = f'{NOMBRES[modulo]} #{registro_id}'` con `NOMBRES = {'recepcion': 'Recepción', 'entregas': 'Entrega', 'devoluciones': 'Devolución'}`; `detalle = f'Fecha futura: {dmy(fecha)}'`.
- Cada `formatear_*` devuelve el dict de 4 claves; los tres primeros chequeos fijan `modulo` en constante (`'entregas'`, `'devoluciones'` respectivos) y toman `registro_id` de la fila.
- `CHEQUEOS` al final del archivo, en orden, con las 3 entradas y títulos/descripciones en español (la descripción explica QUÉ detecta cada chequeo).

- [ ] **Step 4: Verificar GREEN**

Run: `venv/bin/python -m pytest tests/test_inspecciones.py -q`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add app/services/inspecciones.py tests/test_inspecciones.py
git commit -m "feat(inspecciones): servicio con chequeos de orden de fechas"
```

---

### Task 2: Chequeos de centro de devolución y rangos corruptos

**Files:**
- Modify: `app/services/inspecciones.py`
- Test: `tests/test_inspecciones.py`

**Interfaces:**
- Consumes de Task 1: `dmy`, `CHEQUEOS`, patrón `query()`/`formatear_*`; test helpers `make_cadena`, `hallazgos` (importados del propio archivo de tests).
- Produce: claves `'centro-devolucion-distinto'` y `'rangos-corruptos'` en `CHEQUEOS` (Task 4 espera las 6 claves en este orden: los 4 de Task 1… es decir, orden final:
  `entrega-antes-recepcion, devolucion-antes-entrega, fechas-futuras, centro-devolucion-distinto, rangos-corruptos, estado-inconsistente`).

- [ ] **Step 1: Escribir los tests fallidos**

Append a `tests/test_inspecciones.py` (imports: `from app.models.centro import Centro` ya disponible vía fixture, `date`):

```python
def make_rango(tipo, user, ini, fin, rangoId, anio=2026, fecha=date(2026, 3, 1)):
    """Recepción sin folios individuales (el chequeo de rangos solo mira
    recepcion_folios)."""
    rec = RecepcionFolio(fecha=fecha, anioCert=anio, tipoCert_id=tipo.id,
                         folioInicial=ini, folioFinal=fin, rangoId=rangoId,
                         userId=user.id)
    db.session.add(rec)
    db.session.commit()
    return rec


def test_centro_devolucion_distinto_detecta(app, tipo, centro, operador):
    otro = Centro(name='Otro Centro', telefono='555', direccion='Calle 2',
                  activo=True)
    db.session.add(otro)
    db.session.commit()
    folio = make_cadena(tipo, centro, operador, fecha_ent=date(2026, 3, 1),
                        fecha_dev=date(2026, 3, 10))
    folio.devolucion.centroId = otro.id
    db.session.commit()
    res = hallazgos(centro_devolucion_distinto(),
                    formatear_centro_devolucion_distinto)
    assert len(res) == 1
    assert res[0]['modulo'] == 'devoluciones'
    assert res[0]['registro_id'] == folio.devolucion.id
    assert centro.name in res[0]['detalle'] and otro.name in res[0]['detalle']


def test_centro_devolucion_igual_no_alerta(app, tipo, centro, operador):
    make_cadena(tipo, centro, operador, numero=2000, rangoId=2,
                fecha_ent=date(2026, 3, 1), fecha_dev=date(2026, 3, 10))
    assert hallazgos(centro_devolucion_distinto(),
                     formatear_centro_devolucion_distinto) == []


def test_rangos_corruptos_detecta_invertido(app, tipo, operador):
    make_rango(tipo, operador, ini=500, fin=400, rangoId=10)
    res = hallazgos(rangos_corruptos(), formatear_rangos_corruptos)
    assert len(res) == 1
    assert res[0]['modulo'] == 'recepcion'
    assert 'invertido' in res[0]['detalle']


def test_rangos_corruptos_detecta_solape_sin_duplicar(app, tipo, operador):
    make_rango(tipo, operador, ini=1, fin=100, rangoId=11)
    make_rango(tipo, operador, ini=50, fin=150, rangoId=12)   # solapa con 1-100
    res = hallazgos(rangos_corruptos(), formatear_rangos_corruptos)
    assert len(res) == 2, 'cada rango del par debe aparecer exactamente una vez'
    assert all('solapa' in h['detalle'] for h in res)
    assert {h['registro_id'] for h in res} == {r.id for r in
           RecepcionFolio.query.order_by(RecepcionFolio.id).all()}


def test_rangos_sanos_no_alertan(app, tipo, operador):
    make_rango(tipo, operador, ini=1, fin=100, rangoId=13)
    make_rango(tipo, operador, ini=101, fin=200, rangoId=14)  # adyacente no solapa
    make_rango(tipo, operador, ini=1, fin=100, rangoId=15, anio=2025)  # otro año
    assert hallazgos(rangos_corruptos(), formatear_rangos_corruptos) == []
```

- [ ] **Step 2: Verificar RED**

Run: `venv/bin/python -m pytest tests/test_inspecciones.py -q -k "centro or rangos"`
Expected: FAIL — `ImportError: cannot import name 'centro_devolucion_distinto'`

- [ ] **Step 3: Implementar los dos chequeos y registrarlos**

- `centro_devolucion_distinto()`: columnas `DevolucionFolio.id.label('registro_id')`, nombres de ambos centros; joins: `DevolucionFolio → EntregaFolio (folio_id)`, `DevolucionFolio → Folio`, y **dos joins a `Centro` con `aliased`** (uno por `DevolucionFolio.centroId`, otro por `EntregaFolio.centroId`); `filter(DevolucionFolio.centroId != EntregaFolio.centroId)`; `order_by(DevolucionFolio.id)`.
- `rangos_corruptos()`: subquery EXISTS correlacionada — `otro = aliased(RecepcionFolio)`; `solapa = db.session.query(otro).filter(otro.anioCert == RecepcionFolio.anioCert, otro.tipoCert_id == RecepcionFolio.tipoCert_id, otro.id != RecepcionFolio.id, otro.folioInicial <= RecepcionFolio.folioFinal, otro.folioFinal >= RecepcionFolio.folioInicial).exists()`; query principal con `RecepcionFolio.id.label('registro_id')`, `folioInicial`, `folioFinal`, booleano `(folioInicial > folioFinal).label('invertido')` y `solapa.label('solapa')`; `filter(or_(invertido, solapa))`; `order_by(RecepcionFolio.id)`.
- `formatear_centro_devolucion_distinto`: `detalle` con los dos nombres de centro (detecta cuál es la devolución y cuál la entrega); `formatear_rangos_corruptos`: une con `' y '` las partes presentes (`f'rango invertido ({ini}-{fin})'`, `'solapa con otro rango del mismo año y tipo'`) prefijadas por `Recepción con `.
- Registrar ambas entradas en `CHEQUEOS` (en su posición: `centro-devolucion-distinto` cuarta, `rangos-corruptos` quinta).

- [ ] **Step 4: Verificar GREEN**

Run: `venv/bin/python -m pytest tests/test_inspecciones.py -q`
Expected: PASS (los 7 del Task 1 + 5 nuevos = 12)

- [ ] **Step 5: Commit**

```bash
git add app/services/inspecciones.py tests/test_inspecciones.py
git commit -m "feat(inspecciones): chequeos de centro de devolución y rangos corruptos"
```

---

### Task 3: Chequeo de estado inconsistente

**Files:**
- Modify: `app/services/inspecciones.py`
- Test: `tests/test_inspecciones.py`

**Interfaces:**
- Consumes de Task 1: `dmy`, `CHEQUEOS`, `hallazgos`.
- Produce: clave `'estado-inconsistente'` — sexta y última de `CHEQUEOS` (Task 4 asume `len(CHEQUEOS) == 6`). `modulo` fijo `'folios'` (endpoint `folios.details`).

- [ ] **Step 1: Escribir los tests fallidos**

```python
def test_estado_entregado_sin_entrega_detectado(app, tipo, centro, operador):
    folio = make_cadena(tipo, centro, operador, numero=5000, rangoId=20,
                        estado='entregado')            # sin fila de entrega
    res = hallazgos(estado_inconsistente(), formatear_estado_inconsistente)
    assert len(res) == 1
    assert res[0]['modulo'] == 'folios'
    assert res[0]['registro_id'] == folio.id
    assert "sin registro de entrega" in res[0]['detalle']


def test_estado_devuelto_sin_devolucion_detectado(app, tipo, centro, operador):
    folio = make_cadena(tipo, centro, operador, numero=5001, rangoId=21,
                        fecha_ent=date(2026, 3, 1))   # estado 'entregado'
    folio.estado = 'devuelto'                          # sin fila de devolución
    db.session.commit()
    res = hallazgos(estado_inconsistente(), formatear_estado_inconsistente)
    assert len(res) == 1 and res[0]['registro_id'] == folio.id
    assert "sin registro de devolución" in res[0]['detalle']


def test_estado_disponible_con_entrega_detectado(app, tipo, centro, operador):
    folio = make_cadena(tipo, centro, operador, numero=5002, rangoId=22,
                        fecha_ent=date(2026, 3, 1), estado='disponible')
    res = hallazgos(estado_inconsistente(), formatear_estado_inconsistente)
    assert len(res) == 1 and res[0]['registro_id'] == folio.id
    assert 'con entrega registrada' in res[0]['detalle']


def test_estados_coherentes_y_perdido_no_alertan(app, tipo, centro, operador):
    make_cadena(tipo, centro, operador, numero=6001, rangoId=23)   # disponible solo
    make_cadena(tipo, centro, operador, numero=6002, rangoId=24,
                fecha_ent=date(2026, 3, 1))                       # entregado ok
    make_cadena(tipo, centro, operador, numero=6003, rangoId=25,
                fecha_ent=date(2026, 3, 1), fecha_dev=date(2026, 3, 10))  # devuelto ok
    make_cadena(tipo, centro, operador, numero=6004, rangoId=26,
                fecha_ent=date(2026, 3, 1), estado='perdido')      # fuera de alcance
    assert hallazgos(estado_inconsistente(),
                     formatear_estado_inconsistente) == []


def test_chequeos_completos_son_seis():
    assert len(CHEQUEOS) == 6
    assert list(CHEQUEOS)[-1] == 'estado-inconsistente'
```

- [ ] **Step 2: Verificar RED**

Run: `venv/bin/python -m pytest tests/test_inspecciones.py -q -k "estado or seis"`
Expected: FAIL — `ImportError: cannot import name 'estado_inconsistente'`

- [ ] **Step 3: Implementar y registrar**

- `estado_inconsistente()`: dos EXISTS correlacionados (`con_entrega`, `con_devolucion` sobre `Folio.id`); query de `Folio` con columnas `id.label('registro_id')`, `folio`, `estado`, `con_entrega.label('tiene_entrega')`, `con_devolucion.label('tiene_devolucion')`; `filter(or_(and_(estado=='entregado', ~con_entrega), and_(estado=='devuelto', ~con_devolucion), and_(estado=='disponible', con_entrega)))`; `order_by(Folio.id)`. El estado `perdido` no entra en ninguna rama (por diseño).
- `formatear_estado_inconsistente`: `titulo = f'Folio {row.folio}'`; `detalle` según `row.estado` con los textos exactos que pinesan los tests ("Estado 'entregado' sin registro de entrega", "Estado 'devuelto' sin registro de devolución", "Estado 'disponible' con entrega registrada"); `modulo='folios'`.
- Registrar entrada sexta en `CHEQUEOS`.

- [ ] **Step 4: Verificar GREEN**

Run: `venv/bin/python -m pytest tests/test_inspecciones.py -q`
Expected: PASS (17 tests)

- [ ] **Step 5: Commit**

```bash
git add app/services/inspecciones.py tests/test_inspecciones.py
git commit -m "feat(inspecciones): chequeo de estado inconsistente (registro completo)"
```

---

### Task 4: Rutas, templates, permiso y sidebar

**Files:**
- Create: `app/inspecciones/__init__.py`
- Create: `app/templates/inspecciones/index.html`
- Create: `app/templates/inspecciones/detalle.html`
- Modify: `app/services/permisos.py` (agregar clave `inspecciones.ver` junto a `auditoria.ver`)
- Modify: `app/__init__.py` (import + `register_blueprint`, junto a `escaneos_bp`)
- Modify: `app/templates/components/sidebar.html` (bloque nuevo después de Auditoría)
- Test: `tests/test_inspecciones.py`

**Interfaces:**
- Consumes de Tasks 1-3: `CHEQUEOS`, `URLS_CORREGIR` (firmas arriba).
- Produce: endpoints `inspecciones.index` (`GET /inspecciones/`) y `inspecciones.detalle` (`GET /inspecciones/<clave>`); clave `inspecciones.ver`.

- [ ] **Step 1: Escribir los tests fallidos**

Append a `tests/test_inspecciones.py` (imports nuevos: `from app.models.permiso_usuario import PermisoUsuario`, `from tests.conftest import make_user`, `import re`):

```python
CHEQUEO_CLAVES = ['entrega-antes-recepcion', 'devolucion-antes-entrega',
                  'fechas-futuras', 'centro-devolucion-distinto',
                  'rangos-corruptos', 'estado-inconsistente']


def test_index_muestra_los_seis_chequeos(admin_client, app):
    html = admin_client.get('/inspecciones/').get_data(as_text=True)
    for clave in CHEQUEO_CLAVES:
        assert f'/inspecciones/{clave}' in html, f'falta tarjeta {clave}'
    assert 'Sin inconsistencias' in html, 'DB limpia → tarjetas verdes'


def test_index_enlaza_detalle_con_hallazgo(app, tipo, centro, operador,
                                           admin_client):
    make_cadena(tipo, centro, operador, fecha_rec=date(2026, 3, 10),
                fecha_ent=date(2026, 3, 1))
    html = admin_client.get('/inspecciones/').get_data(as_text=True)
    assert '/inspecciones/entrega-antes-recepcion' in html


def test_detalle_muestra_hallazgo_y_link_corregir(app, tipo, centro, operador,
                                                  admin_client):
    make_cadena(tipo, centro, operador, fecha_rec=date(2026, 3, 10),
                fecha_ent=date(2026, 3, 1))
    entrega = EntregaFolio.query.one()
    html = admin_client.get('/inspecciones/entrega-antes-recepcion') \
        .get_data(as_text=True)
    assert f'/entregas/{entrega.id}/edit' in html, 'sin link de corrección'
    assert '01/03/2026' in html and '10/03/2026' in html


def test_fechas_futuras_link_por_modulo(app, tipo, centro, operador, admin_client):
    make_cadena(tipo, centro, operador, numero=1000, rangoId=1,
                fecha_rec=date(2027, 1, 1))
    make_cadena(tipo, centro, operador, numero=2000, rangoId=2,
                fecha_rec=date(2026, 3, 1), fecha_ent=date(2027, 1, 1))
    make_cadena(tipo, centro, operador, numero=3000, rangoId=3,
                fecha_rec=date(2026, 3, 1), fecha_ent=date(2026, 3, 1),
                fecha_dev=date(2027, 1, 1))
    rec, ent, dev = (RecepcionFolio.query.one(), EntregaFolio.query.one(),
                     DevolucionFolio.query.one())
    html = admin_client.get('/inspecciones/fechas-futuras') \
        .get_data(as_text=True)
    assert f'/recepcion/{rec.id}/edit' in html
    assert f'/entregas/{ent.id}/edit' in html
    assert f'/devoluciones/{dev.id}/edit' in html


def test_detalle_404_clave_desconocida(admin_client, app):
    assert admin_client.get('/inspecciones/no-existe').status_code == 404


def test_detalle_pagina_estable(app, tipo, centro, operador, admin_client):
    # 26 hallazgos: 25 en página 1, el 26º solo en la 2 (order_by estable).
    for n in range(26):
        make_cadena(tipo, centro, operador, numero=1000 + n, rangoId=100 + n,
                    fecha_rec=date(2026, 3, 10), fecha_ent=date(2026, 3, 1))
    p1 = admin_client.get('/inspecciones/entrega-antes-recepcion') \
        .get_data(as_text=True)
    p2 = admin_client.get('/inspecciones/entrega-antes-recepcion?page=2') \
        .get_data(as_text=True)
    assert 'Folio 1000' in p1 and 'Folio 1000' not in p2
    assert 'Folio 1025' in p2 and 'Folio 1025' not in p1
    assert len(re.findall(r'/entregas/\d+/edit', p1)) == 25


def test_sin_permiso_redirige_a_dashboard(app, client):
    lectura = make_user('lectura_insp', 'lectura')
    client.post('/auth/login', data={'username': lectura.username,
                                     'password': 'pass12345'})
    for url in ('/inspecciones/', '/inspecciones/fechas-futuras'):
        resp = client.get(url)
        assert resp.status_code == 302
        assert '/dashboard' in resp.headers['Location']


def test_grant_inspecciones_ver_permite_ver(app, client):
    lectura = make_user('lectura_insp2', 'lectura')
    db.session.add(PermisoUsuario(user_id=lectura.id,
                                  permiso='inspecciones.ver'))
    db.session.commit()
    client.post('/auth/login', data={'username': lectura.username,
                                     'password': 'pass12345'})
    assert client.get('/inspecciones/').status_code == 200


def test_sidebar_link_visible_para_admin(admin_client, app):
    html = admin_client.get('/dashboard/').get_data(as_text=True)
    assert '/inspecciones/' in html, 'admin debe ver el link'


def test_sidebar_link_oculto_para_lectura_sin_grant(app, client):
    # Dos usuarios autenticados en el mismo test chocan con g._login_user:
    # este test solo loguea a la lectura (regla de un usuario por test).
    lectura = make_user('lectura_insp3', 'lectura')
    client.post('/auth/login', data={'username': lectura.username,
                                     'password': 'pass12345'})
    html = client.get('/dashboard/').get_data(as_text=True)
    assert '/inspecciones/' not in html, 'lector sin grant no ve el link'
```

- [ ] **Step 2: Verificar RED**

Run: `venv/bin/python -m pytest tests/test_inspecciones.py -q`
Expected: FAIL — `TypeError`/404 en las rutas nuevas (blueprint no existe aún)

- [ ] **Step 3: Implementar**

a) `app/services/permisos.py`: `'inspecciones.ver': ('Ver inspecciones de datos', 'admin'),` (junto a `auditoria.ver`).

b) `app/inspecciones/__init__.py`:

```python
inspecciones_bp = Blueprint('inspecciones', __name__, url_prefix='/inspecciones')

@inspecciones_bp.route('/')
@login_required
@permiso_requerido('inspecciones.ver')   # default hacia='dashboard'
def index():
    # conteos: {clave: c['query']().count() for clave, c in CHEQUEOS.items()}
    # render inspecciones/index.html con chequeos=CHEQUEOS, conteos

@inspecciones_bp.route('/<clave>')
@login_required
@permiso_requerido('inspecciones.ver')
def detalle(clave):
    # chequeo = CHEQUEOS.get(clave); if None → abort(404)
    # pag = chequeo['query']().paginate(page=request.args.get('page', 1, type=int), per_page=25, error_out=False)
    # para cada row: h = chequeo['formatear'](row); h['url'] = url_for(URLS_CORREGIR[h['modulo']], id=h['registro_id'])
    # render inspecciones/detalle.html con clave, chequeo, hallazgos, pagination=pag
```

c) `app/__init__.py`: import de `inspecciones_bp` + `app.register_blueprint(inspecciones_bp)` (bloque junto a `escaneos_bp`).

d) `index.html`: `{% extends 'base.html' %}`, bloque `content`, h4 "Inspecciones", grilla `row row-cols-1 row-cols-md-2 row-cols-lg-3 g-3`; por cada `clave, c in chequeos.items()`: card con `c['titulo']`, `c['descripcion']`, y `{% if conteos[clave] %}` badge con el conteo + link `url_for('inspecciones.detalle', clave=clave)` "Ver hallazgos" `{% else %}` `<span class="badge bg-success">Sin inconsistencias</span>`.

e) `detalle.html`: `{% extends 'base.html' %}`, bloque `content`; link de vuelta a `inspecciones.index`; `c['titulo']` + `c['descripcion']`; tabla Bootstrap `Registro | Detalle | Corregir` donde cada fila usa `h['titulo']`, `h['detalle']` y `<a href="{{ h['url'] }}" class="btn btn-sm btn-outline-primary">Corregir</a>`; debajo `{{ render_pagination(pagination) }}` con `{% from 'components/pagination.html' import render_pagination %}` arriba (`pagina_url` es template global, no lleva argumentos).

f) `sidebar.html`, después del bloque `{% if puede('auditoria.ver') %}`: bloque idéntico en forma con `{% if puede('inspecciones.ver') %}`, icono `fas fa-clipboard-check`, texto " Inspecciones", `request.endpoint and 'inspecciones' in request.endpoint` para `active`.

- [ ] **Step 4: Verificar GREEN**

Run: `venv/bin/python -m pytest tests/test_inspecciones.py -q`
Expected: PASS (17 + 10 = 27 tests)

- [ ] **Step 5: Commit**

```bash
git add app/inspecciones app/templates/inspecciones app/services/permisos.py \
        app/__init__.py app/templates/components/sidebar.html tests/test_inspecciones.py
git commit -m "feat(inspecciones): rutas de resumen y detalle con permiso y sidebar"
```

---

### Task 5: Corrección manual de estado en el detalle del folio

**Files:**
- Modify: `app/folios/__init__.py` (ruta `cambiar_estado` + renombrar helper)
- Modify: `app/templates/folios/details.html` (form de estado en el header)
- Test: `tests/test_folios_estado.py` (archivo nuevo)

**Interfaces:**
- Consumes: `get_or_404`, `log_audit`, `permiso_requerido('folios.actualizar', hacia='blueprint')` (patrón idéntico de `perder`/`recuperar` en `app/folios/__init__.py:277-301`), fixtures `auth_client`/`client`, `make_folio` de conftest.
- Produce: endpoint `folios.cambiar_estado` (`POST /folios/<id>/estado`); helper `_cambiar_estado(folio, destino)` (renombre del actual `_cambiar_estado_perdido`, usado solo en `perder`, `recuperar` y la ruta nueva).

- [ ] **Step 1: Escribir los tests fallidos**

`tests/test_folios_estado.py`:

```python
"""Corrección manual de estado del folio desde su detalle."""

from datetime import date

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.folio import Folio
from tests.conftest import make_folio


def _folio_entregado_sin_registro(tipo):
    folio = make_folio(tipo, numero=7000, rangoId=30, estado='entregado')
    db.session.commit()
    return folio


def test_cambiar_estado_valido_y_audita(auth_client, app, tipo):
    folio = _folio_entregado_sin_registro(tipo)
    resp = auth_client.post(f'/folios/{folio.id}/estado',
                            data={'estado': 'disponible'},
                            follow_redirects=True)
    assert 'Estado actualizado exitosamente.' in resp.get_data(as_text=True)
    assert db.session.get(Folio, folio.id).estado == 'disponible'
    log = AuditLog.query.filter_by(accion='UPDATE', tabla='folios',
                                   registro_id=folio.id).one()
    assert log.datos_anteriores == {'estado': 'entregado'}
    assert log.datos_nuevos == {'estado': 'disponible'}


def test_cambiar_estado_invalido_rechazado(auth_client, app, tipo):
    folio = _folio_entregado_sin_registro(tipo)
    for malo in ('perdido', 'digitado', 'escaneado', 'nulo', '', 'basura'):
        auth_client.post(f'/folios/{folio.id}/estado', data={'estado': malo})
    assert db.session.get(Folio, folio.id).estado == 'entregado'
    assert AuditLog.query.filter_by(accion='UPDATE', tabla='folios',
                                    registro_id=folio.id).count() == 0


def test_cambiar_estado_igual_no_audita(auth_client, app, tipo):
    folio = _folio_entregado_sin_registro(tipo)
    resp = auth_client.post(f'/folios/{folio.id}/estado',
                            data={'estado': 'entregado'},
                            follow_redirects=True)
    assert 'Ese ya es el estado del folio.' in resp.get_data(as_text=True)
    assert AuditLog.query.filter_by(accion='UPDATE', tabla='folios',
                                    registro_id=folio.id).count() == 0


def test_cambiar_estado_sin_permiso_no_cambia(app, client, tipo):
    from tests.conftest import make_user
    folio = _folio_entregado_sin_registro(tipo)
    lectura = make_user('lectura_estado', 'lectura')
    client.post('/auth/login', data={'username': lectura.username,
                                     'password': 'pass12345'})
    resp = client.post(f'/folios/{folio.id}/estado',
                       data={'estado': 'disponible'})
    assert resp.status_code == 302
    assert '/folios' in resp.headers['Location']
    assert db.session.get(Folio, folio.id).estado == 'entregado'


def test_details_muestra_form_de_estado(auth_client, app, tipo):
    folio = _folio_entregado_sin_registro(tipo)
    html = auth_client.get(f'/folios/{folio.id}').get_data(as_text=True)
    assert 'name="estado"' in html
    assert '<option value="disponible"' in html
    assert '<option value="devuelto"' in html
    assert '<option value="perdido"' not in html, 'perdido es flujo propio'


def test_details_oculta_form_a_lectura(app, client, tipo):
    from tests.conftest import make_user
    folio = _folio_entregado_sin_registro(tipo)
    lectura = make_user('lectura_estado2', 'lectura')
    client.post('/auth/login', data={'username': lectura.username,
                                     'password': 'pass12345'})
    html = client.get(f'/folios/{folio.id}').get_data(as_text=True)
    assert 'name="estado"' not in html
```

- [ ] **Step 2: Verificar RED**

Run: `venv/bin/python -m pytest tests/test_folios_estado.py -q`
Expected: FAIL — 404 en `POST /folios/<id>/estado` y `name="estado"` ausente

- [ ] **Step 3: Implementar**

a) En `app/folios/__init__.py`, junto al bloque `perder`/`recuperar`:
- Renombrar `_cambiar_estado_perdido` → `_cambiar_estado` (3 usos en el mismo archivo; correr los tests de perdidos en el paso siguiente lo pina).
- `ESTADOS_CORREGIBLES = ('disponible', 'entregado', 'devuelto')` (sin `perdido` ni los flags — son columnas separadas).
- Ruta (esqueleto; cuerpo refleja `perder`):

```python
@folios_bp.route('/<int:id>/estado', methods=['POST'])
@permiso_requerido('folios.actualizar', hacia='blueprint')
def cambiar_estado(id):
    folio = get_or_404(Folio, id)
    nuevo = request.form.get('estado', '').strip()
    # 1) nuevo not in ESTADOS_CORREGIBLES → flash 'Estado inválido.' (danger) + redirect a details
    # 2) nuevo == folio.estado → flash 'Ese ya es el estado del folio.' (info) + redirect (sin audit)
    # 3) _cambiar_estado(folio, nuevo); db.session.commit();
    #    flash 'Estado actualizado exitosamente.' (success); redirect a details
```

b) En `app/templates/folios/details.html`, dentro del `<div class="d-flex gap-2">` del header y del `{% if puede('folios.actualizar') %}` existente:

```html
<form method="POST" action="{{ url_for('folios.cambiar_estado', id=folio.id) }}"
      data-confirm data-title="¿Cambiar el estado del folio?"
      data-text="Se guardará con registro de auditoría." data-icon="question"
      class="d-flex gap-1 align-items-center">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <select name="estado" class="form-select form-select-sm w-auto"
            aria-label="Estado del folio">
        <option value="disponible" {% if folio.estado == 'disponible' %}selected{% endif %}>Disponible</option>
        <option value="entregado" {% if folio.estado == 'entregado' %}selected{% endif %}>Entregado</option>
        <option value="devuelto" {% if folio.estado == 'devuelto' %}selected{% endif %}>Devuelto</option>
    </select>
    <button type="submit" class="btn btn-sm btn-outline-primary">Guardar estado</button>
</form>
```

- [ ] **Step 4: Verificar GREEN + no regresión del helper renombrado**

Run: `venv/bin/python -m pytest tests/test_folios_estado.py tests/test_folios_perdidos.py tests/test_folios_update_status.py -q`
Expected: PASS

- [ ] **Step 5: Suite completa**

Run: `venv/bin/python -m pytest -q`
Expected: PASS, 0 failures (incluye `test_ui_lote5::test_flashes_sin_correctamente` y los tests de catálogo de permisos que iteran `PERMISOS`)

- [ ] **Step 6: Commit**

```bash
git add app/folios/__init__.py app/templates/folios/details.html tests/test_folios_estado.py
git commit -m "feat(folios): corrección manual de estado desde el detalle del folio"
```
