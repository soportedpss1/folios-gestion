# Centros: última entrega y última devolución — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mostrar por centro, en el listado `/centros/` y en sus exports Excel/PDF, la fecha de la última entrega de folios y la última devolución.

**Architecture:** Dos consultas agregadas (`GROUP BY centroId` + `MAX(fecha)`) en `app/centros/__init__.py` devuelven dos dicts `{centroId: date}`; el route los pasa al template y a los dos exports de la lista. Sin cambios de esquema, sin N+1.

**Tech Stack:** Flask + SQLAlchemy + Jinja2 + openpyxl + WeasyPrint (tests PDF con monkeypatch, patrón existente).

**Spec:** `docs/superpowers/specs/2026-01-05-centros-ultima-entrega-devolucion-design.md`

## Global Constraints

- Todo texto de usuario en **espanol**, con tildes.
- Formato de fecha en UI y exports: `dd/mm/aaaa` (`strftime('%d/%m/%Y')`).
- Centros sin registros: `-` en HTML y PDF, cadena vacía `''` en Excel.
- Sin cambios de esquema (no migraciones): las fechas viven en `entrega_folios.fechaEntrega` y `devolucion_folios.fechaDevolucion` (ambas `Date`).
- El listado sigue mostrando **todos** los centros (activos e inactivos), igual que hoy.
- Tests: `python3 -m pytest` (SQLite in-memory, requisitos en `requirements-dev.txt`).

## Review Focus

1. **Centro sin entregas ni devoluciones** — no debe reventar el render ni el export; celdas con `-`/`''`. → Test `test_excel_centro_sin_movimientos_muestra_vacio` (Task 2) y el uso de `dict.get` en todos los consumidores.
2. **`MAX` sobre varios movimientos** — con dos entregas debe mostrar la más reciente, no la primera. → Test `test_index_muestra_ultima_entrega_y_devolucion` (Task 1).
3. **Tests existentes que fijan el número de columnas** — `test_centros_lista_excel_contiene_filas` (header exacto de 5 columnas) y `test_centros_indice_vacio_sin_celdas_extra` (colspan 5) rompen con el cambio; deben actualizarse a 7 columnas. → Tasks 1 y 2 los actualizan y vuelven a correr.
4. **PDF sin libpango en el venv local** — el import de weasyprint revienta con `OSError`; el test nuevo debe hacer `pytest.skip` igual que los PDFs existentes. → Test `test_pdf_lista_muestra_ultimas_fechas` (Task 3).
5. **`fechaEntrega`/`fechaDevolucion` son `Date` no-nulas** — `MAX` nunca devuelve `None` con filas presentes; el `None` solo aparece cuando el centro no tiene filas. Los tres consumidores manejan ambos casos. → cubierto por los tests de los items 1 y 2.

---

### Task 1: Helper `_ultimos_por_centro` + columnas en el listado `/centros/`

**Files:**
- Modify: `app/centros/__init__.py` (imports; función `_ultimos_por_centro`; route `index` en líneas ~85-89)
- Modify: `app/templates/centros/index.html` (thead, tbody, colspan del estado vacío)
- Test: `tests/test_centros_ultimos_movimientos.py` (crear)
- Modify: `tests/test_ui_lote1.py:72-75` (colspan 5 → 7)

**Interfaces:**
- Consumes: `EntregaFolio.centroId`/`fechaEntrega`, `DevolucionFolio.centroId`/`fechaDevolucion` (ya importados en el blueprint), `func` de `sqlalchemy`.
- Produces: `_ultimos_por_centro() -> tuple[dict[int, date], dict[int, date]]` — `(ultima_entrega, ultima_devolucion)`, dicts `{centroId: date}`. Los routes de Excel/PDF (Tasks 2-3) usan exactamente esta firma.
- Template recibe `ultima_entrega` y `ultima_devolucion` como variables Jinja (dicts; índice con `.get(c.id)`).

- [ ] **Step 1: Escribir el test fallido**

Crear `tests/test_centros_ultimos_movimientos.py`:

```python
"""Listado de centros: última entrega y última devolución por centro."""

from datetime import date

from app.extensions import db
from app.models.centro import Centro
from app.models.devolucion_folio import DevolucionFolio
from app.models.entrega_folio import EntregaFolio
from tests.conftest import make_folio


def _seed(centro, tipo, operador):
    """Dos entregas (muestra la más reciente) y una devolución en `centro`."""
    f1 = make_folio(tipo, anio=2026, numero=8001, estado='entregado')
    f2 = make_folio(tipo, anio=2026, numero=8002, estado='devuelto')
    db.session.add(EntregaFolio(folio_id=f1.id, fechaEntrega=date(2026, 3, 10),
                                centroId=centro.id, userId=operador.id))
    db.session.add(EntregaFolio(folio_id=f2.id, fechaEntrega=date(2026, 5, 2),
                                centroId=centro.id, userId=operador.id))
    db.session.add(DevolucionFolio(folio_id=f2.id,
                                   fechaDevolucion=date(2026, 6, 15),
                                   centroId=centro.id, userId=operador.id))
    db.session.commit()


def test_index_muestra_ultima_entrega_y_devolucion(auth_client, app, tipo,
                                                   centro, operador):
    _seed(centro, tipo, operador)
    otro = Centro(name='Centro Sin Movimientos', telefono='1',
                  direccion='d', activo=True)
    db.session.add(otro)
    db.session.commit()

    resp = auth_client.get('/centros/')
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert '<th>Última entrega</th>' in body, 'columna Última entrega ausente'
    assert '<th>Última devolución</th>' in body, 'columna Última devolución ausente'
    assert '02/05/2026' in body, 'debe mostrar la entrega MÁS RECIENTE (no 10/03/2026)'
    assert '10/03/2026' not in body, 'no debe mostrar una entrega antigua como última'
    assert '15/06/2026' in body, 'fecha de última devolución ausente'
    assert 'Centro Sin Movimientos' in body, 'el centro sin datos debe seguir listado'
```

- [ ] **Step 2: Correr el test para verlo fallar**

Run: `python3 -m pytest tests/test_centros_ultimos_movimientos.py -v`
Expected: FAIL — `'Última entrega' in body` (la columna no existe).

- [ ] **Step 3: Implementar helper, route y template**

En `app/centros/__init__.py`:
- Añadir `func` al import de sqlalchemy existente (`from sqlalchemy.orm import selectinload` → agregar `from sqlalchemy import func`).
- Nueva función junto a `_datos_del_centro`:

```python
def _ultimos_por_centro():
    """(ultima_entrega, ultima_devolucion): {centroId: date} con el MAX de cada tabla."""
```

Cuerpo: dos `db.session.query(<tabla>.centroId, func.max(<tabla>.<fecha>)).group_by(<tabla>.centroId).all()` convertidos a `dict(...)`; retorna la tupla `(entregas, devoluciones)`.

- Route `index`: `ultima_entrega, ultima_devolucion = _ultimos_por_centro()` y pasar ambos a `render_template`.
- `app/templates/centros/index.html`: dos `<th>` entre Dirección y Estado; dos `<td>` en el mismo lugar del loop:

```jinja
<td>{{ ultima_entrega[c.id].strftime('%d/%m/%Y') if ultima_entrega.get(c.id) else '-' }}</td>
<td>{{ ultima_devolucion[c.id].strftime('%d/%m/%Y') if ultima_devolucion.get(c.id) else '-' }}</td>
```

- Mismo template: `colspan="5"` → `colspan="7"` en la fila vacía.
- `tests/test_ui_lote1.py:74`: actualizar el assert a `colspan="7"` (con comentario: 7 columnas desde que el listado muestra últimas fechas).

- [ ] **Step 4: Correr los tests del listado**

Run: `python3 -m pytest tests/test_centros_ultimos_movimientos.py tests/test_ui_lote1.py -v`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add app/centros/__init__.py app/templates/centros/index.html tests/test_centros_ultimos_movimientos.py tests/test_ui_lote1.py
git commit -m "feat(centros): última entrega y última devolución en el listado"
```

---

### Task 2: Columnas en el export Excel de la lista

**Files:**
- Modify: `app/centros/__init__.py` (`export_lista_excel`, líneas ~320-361)
- Test: `tests/test_centros_ultimos_movimientos.py` (añadir)
- Modify: `tests/test_exports_contenido.py:189-202` (`test_centros_lista_excel_contiene_filas`)

**Interfaces:**
- Consumes: `_ultimos_por_centro()` (Task 1).

- [ ] **Step 1: Escribir el test fallido**

Añadir a `tests/test_centros_ultimos_movimientos.py`:

```python
from io import BytesIO

from openpyxl import load_workbook


def test_excel_lista_muestra_ultimas_fechas(auth_client, app, tipo, centro,
                                            operador):
    _seed(centro, tipo, operador)
    resp = auth_client.get('/centros/export/excel')
    assert resp.status_code == 200
    wb = load_workbook(BytesIO(resp.data))
    filas = list(wb.active.iter_rows(values_only=True))
    assert filas[0] == ('#', 'Nombre', 'Teléfono', 'Dirección',
                        'Última entrega', 'Última devolución', 'Estado')
    fila = next(r for r in filas[1:] if r[1] == centro.name)
    assert fila[4] == '02/05/2026', 'última entrega en dd/mm/aaaa'
    assert fila[5] == '15/06/2026', 'última devolución en dd/mm/aaaa'


def test_excel_centro_sin_movimientos_muestra_vacio(auth_client, app, centro):
    resp = auth_client.get('/centros/export/excel')
    assert resp.status_code == 200
    wb = load_workbook(BytesIO(resp.data))
    filas = list(wb.active.iter_rows(values_only=True))
    fila = next(r for r in filas[1:] if r[1] == centro.name)
    assert fila[4] == '' and fila[5] == '', \
        'centro sin movimientos: celdas vacías, no None ni crash'
```

- [ ] **Step 2: Correr para verlo fallar**

Run: `python3 -m pytest tests/test_centros_ultimos_movimientos.py -k excel -v`
Expected: FAIL — el header no tiene las columnas nuevas.

- [ ] **Step 3: Implementar en `export_lista_excel`**

- `ultima_entrega, ultima_devolucion = _ultimos_por_centro()` antes del loop.
- `headers`: `['#', 'Nombre', 'Teléfono', 'Dirección', 'Última entrega', 'Última devolución', 'Estado']`.
- En el loop por centro, tras la celda de Dirección:

```python
e = ultima_entrega.get(c.id)
d = ultima_devolucion.get(c.id)
ws.cell(row=row, column=5, value=e.strftime('%d/%m/%Y') if e else '')
ws.cell(row=row, column=6, value=d.strftime('%d/%m/%Y') if d else '')
```

- `Estado` pasa a columna 7.

- [ ] **Step 4: Actualizar el test existente que fija el header**

En `tests/test_exports_contenido.py::test_centros_lista_excel_contiene_filas` (líneas 196-202): header a la tupla de 7 columnas; `rows[1][4] == ''` y `rows[1][5] == ''` (ese centro no tiene movimientos en el test); `rows[1][6] == 'Activo'`.

- [ ] **Step 5: Correr los tests de Excel**

Run: `python3 -m pytest tests/test_centros_ultimos_movimientos.py tests/test_exports_contenido.py -k "excel or Excel or lista" -v`
Expected: PASS (todos, incluidos los actualizados).

- [ ] **Step 6: Commit**

```bash
git add app/centros/__init__.py tests/test_centros_ultimos_movimientos.py tests/test_exports_contenido.py
git commit -m "feat(centros): últimas fechas en el export Excel de la lista"
```

---

### Task 3: Columnas en el export PDF de la lista

**Files:**
- Modify: `app/centros/__init__.py` (`export_lista_pdf`, líneas ~364-431)
- Test: `tests/test_centros_ultimos_movimientos.py` (añadir)

**Interfaces:**
- Consumes: `_ultimos_por_centro()` (Task 1), patrón de test PDF con `monkeypatch` de `weasyprint.HTML` (ya usado en `tests/test_exports_contenido.py:205-229`).

- [ ] **Step 1: Escribir el test fallido**

Añadir a `tests/test_centros_ultimos_movimientos.py` (importar `pytest`):

```python
def test_pdf_lista_muestra_ultimas_fechas(auth_client, app, tipo, centro,
                                          operador, monkeypatch):
    try:
        import weasyprint
    except OSError as exc:
        pytest.skip(f'weasyprint sin libpango (solo Docker): {exc}')

    class _FakeHTML:
        captured = []

        def __init__(self, string=None, **kwargs):
            _FakeHTML.captured.append(string)

        def write_pdf(self):
            return b'%PDF-1.4 fake'

    _seed(centro, tipo, operador)
    _FakeHTML.captured = []
    monkeypatch.setattr(weasyprint, 'HTML', _FakeHTML)

    resp = auth_client.get('/centros/export/pdf')
    assert resp.status_code == 200
    assert len(_FakeHTML.captured) == 1
    html = _FakeHTML.captured[0]
    assert '<th>Última entrega</th>' in html
    assert '<th>Última devolución</th>' in html
    assert '02/05/2026' in html, 'última entrega ausente en el PDF'
    assert '15/06/2026' in html, 'última devolución ausente en el PDF'
```

- [ ] **Step 2: Correr para verlo fallar**

Run: `python3 -m pytest tests/test_centros_ultimos_movimientos.py::test_pdf_lista_muestra_ultimas_fechas -v`
Expected: FAIL — las columnas no existen en el HTML del PDF.

- [ ] **Step 3: Implementar en `export_lista_pdf`**

- `ultima_entrega, ultima_devolucion = _ultimos_por_centro()` tras el `from weasyprint import HTML`.
- En el `<thead>`, tras `<th>Dirección</th>`: `<th>Última entrega</th>` y `<th>Última devolución</th>`.
- En el loop de filas, tras la celda de Dirección (mismo patrón del Excel, `-` en vez de `''`):

```python
e = ultima_entrega.get(c.id)
d = ultima_devolucion.get(c.id)
... e.strftime('%d/%m/%Y') if e else '-' ...
... d.strftime('%d/%m/%Y') if d else '-' ...
```

- `Estado` pasa a la última celda de la fila.

- [ ] **Step 4: Correr el test PDF y el resto del módulo**

Run: `python3 -m pytest tests/test_centros_ultimos_movimientos.py tests/test_exports_contenido.py -v`
Expected: PASS (el test PDF puede hacer skip en un venv sin pango; en Docker pasa).

- [ ] **Step 5: Suite completa**

Run: `python3 -m pytest`
Expected: todos PASS (los tests PDF corren de verdad solo en Docker: `docker compose exec app python -m pytest`).

- [ ] **Step 6: Commit**

```bash
git add app/centros/__init__.py tests/test_centros_ultimos_movimientos.py
git commit -m "feat(centros): últimas fechas en el export PDF de la lista"
```
