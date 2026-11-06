"""Listado de centros: última entrega y última devolución por centro."""

from datetime import date
from io import BytesIO

from openpyxl import load_workbook

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
    # openpyxl serializa '' como celda vacía: al leerla vuelve None
    assert not fila[4] and not fila[5], \
        'centro sin movimientos: celdas vacías, no None ni crash'
