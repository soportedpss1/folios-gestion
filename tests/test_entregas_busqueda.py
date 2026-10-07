"""Fase 4 — endpoint de búsqueda de folios para entregas (select sin miles de options)."""

from datetime import date

from app.extensions import db
from app.models.entrega_folio import EntregaFolio
from tests.conftest import make_folio

Y = 2026


def test_api_disponibles_solo_disponibles_no_nulos(auth_client, app, tipo):
    disponible = make_folio(tipo, anio=Y, numero=1001)
    make_folio(tipo, anio=Y, numero=1002, estado='entregado')
    make_folio(tipo, anio=Y, numero=1003, nulo=True)

    resp = auth_client.get('/entregas/api/folios-disponibles')
    assert resp.status_code == 200, f'endpoint no existe: {resp.status_code}'
    ids = [item['id'] for item in resp.get_json()]
    assert ids == [disponible.id]


def test_api_disponibles_filtro_q_por_numero(auth_client, app, tipo):
    make_folio(tipo, anio=Y, numero=7001)
    esperado = make_folio(tipo, anio=Y, numero=7777)

    resp = auth_client.get('/entregas/api/folios-disponibles?q=7777')
    assert resp.status_code == 200
    ids = [item['id'] for item in resp.get_json()]
    assert ids == [esperado.id]


def test_api_disponibles_limita_resultados(auth_client, app, tipo):
    for n in range(8001, 8151):  # 150 folios disponibles
        make_folio(tipo, anio=Y, numero=n)
    db.session.commit()

    resp = auth_client.get('/entregas/api/folios-disponibles')
    assert resp.status_code == 200
    assert len(resp.get_json()) == 100, 'sin límite de resultados'


def test_api_disponibles_requiere_sesion(client, app, tipo):
    make_folio(tipo, anio=Y, numero=1001)
    resp = client.get('/entregas/api/folios-disponibles')
    assert resp.status_code == 302, 'endpoint abierto sin login'


def test_create_entrega_sigue_funcionando(auth_client, app, tipo, centro):
    folio = make_folio(tipo, anio=Y, numero=4001)

    resp = auth_client.post(
        '/entregas/create',
        data={'folio_ids': [folio.id], 'fechaEntrega': '2026-09-28', 'centroId': centro.id},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(folio)
    assert folio.estado == 'entregado'
    assert EntregaFolio.query.filter_by(folio_id=folio.id).count() == 1


def test_create_entrega_rechaza_folio_no_disponible(auth_client, app, tipo, centro):
    folio = make_folio(tipo, anio=Y, numero=4002, estado='entregado')

    resp = auth_client.post(
        '/entregas/create',
        data={'folio_ids': [folio.id], 'fechaEntrega': '2026-09-28', 'centroId': centro.id},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    # no se crea una segunda entrega (validación de choices/estado)
    assert EntregaFolio.query.filter_by(folio_id=folio.id).count() == 0
