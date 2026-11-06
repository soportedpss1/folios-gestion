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
