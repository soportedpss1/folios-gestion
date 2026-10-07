"""F5 — API de tendencia mensual (entregas/devoluciones) para el gráfico del dashboard."""

from datetime import date

from app.extensions import db
from app.models.entrega_folio import EntregaFolio
from app.models.devolucion_folio import DevolucionFolio
from tests.conftest import make_folio

Y = 2026


def _sembrar(app, tipo, centro, operador):
    f1 = make_folio(tipo, anio=Y, numero=7001, estado='entregado')
    f2 = make_folio(tipo, anio=Y, numero=7002, estado='entregado')
    f3 = make_folio(tipo, anio=Y, numero=7003, estado='devuelto')
    f4 = make_folio(tipo, anio=Y - 1, numero=7004, estado='entregado')
    # enero x2 entregas, marzo x1 devolución, y una entrega fuera del año
    db.session.add(EntregaFolio(folio_id=f1.id, fechaEntrega=date(Y, 1, 10),
                                centroId=centro.id, userId=operador.id))
    db.session.add(EntregaFolio(folio_id=f2.id, fechaEntrega=date(Y, 1, 20),
                                centroId=centro.id, userId=operador.id))
    db.session.add(EntregaFolio(folio_id=f4.id, fechaEntrega=date(Y - 1, 2, 10),
                                centroId=centro.id, userId=operador.id))
    db.session.add(DevolucionFolio(folio_id=f3.id, fechaDevolucion=date(Y, 3, 5),
                                   centroId=centro.id, userId=operador.id))
    db.session.commit()


def test_tendencia_mes_a_mes(auth_client, app, tipo, centro, operador):
    _sembrar(app, tipo, centro, operador)

    resp = auth_client.get(f'/dashboard/api/tendencia?anio={Y}')
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data['entregas']) == 12, 'entregas sin 12 meses'
    assert len(data['devoluciones']) == 12, 'devoluciones sin 12 meses'
    assert data['entregas'][0] == 2, 'enero debe tener 2 entregas'
    assert data['entregas'][1] == 0, 'febrero sin entregas'
    assert data['entregas'][2] == 0, 'marzo sin entregas'
    assert data['devoluciones'][2] == 1, 'marzo debe tener 1 devolución'
    assert data['devoluciones'][0] == 0, 'enero sin devoluciones'
    # entrega de año anterior fuera del conteo
    assert sum(data['entregas']) == 2, 'se coló una entrega de otro año'


def test_tendencia_anio_invalido(auth_client):
    resp = auth_client.get('/dashboard/api/tendencia?anio=1999')
    assert resp.status_code == 400
    assert 'error' in resp.get_json()


def test_tendencia_requiere_login(client):
    resp = client.get('/dashboard/api/tendencia')
    assert resp.status_code == 302


def test_tendencia_anio_no_numerico(auth_client):
    """?anio=abc debe ser 400, no caer al año actual en silencio."""
    resp = auth_client.get('/dashboard/api/tendencia?anio=abc')
    assert resp.status_code == 400, f'devolvió {resp.status_code} en vez de 400'
