"""Importar entregas de folios desde .xlsx (vista previa + confirmación)."""

import json
from io import BytesIO

from openpyxl import Workbook, load_workbook

from app.extensions import db
from app.models.entrega_folio import EntregaFolio
from app.models.folio import Folio
from tests.conftest import make_folio

HEADERS = ['folio', 'tipoCert', 'anioCert']
Y = 2026


def make_xlsx(headers, rows):
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio


def post_importar(client, rows, centro, fecha='2026-10-01', nombre='import.xlsx'):
    return client.post(
        '/entregas/importar',
        data={
            'archivo': (make_xlsx(HEADERS, rows), nombre),
            'centroId': str(centro.id),
            'fechaEntrega': fecha,
        },
        content_type='multipart/form-data',
    )


def confirmar(client, ids, centro, fecha='2026-10-01'):
    return client.post(
        '/entregas/importar/confirmar',
        data={
            'payload': json.dumps(ids),
            'centroId': str(centro.id),
            'fecha': fecha,
        },
        follow_redirects=True,
    )


def test_importar_requiere_login(client):
    assert client.get('/entregas/importar').status_code == 302
    assert client.post('/entregas/importar/confirmar').status_code == 302


def test_plantilla_es_xlsx_con_headers(admin_client):
    resp = admin_client.get('/entregas/plantilla')
    assert resp.status_code == 200
    assert 'spreadsheetml' in resp.content_type
    wb = load_workbook(BytesIO(resp.data))
    assert [c.value for c in wb.active[1]] == HEADERS + ['usuario'], \
        'la plantilla trae la columna usuario final (opcional al importar)'


def test_preview_resuelve_disponible(admin_client, tipo, centro):
    make_folio(tipo, anio=Y, numero=1000)
    resp = post_importar(admin_client, [[1000, tipo.name, Y]], centro)
    text = resp.get_data(as_text=True)
    assert '<strong>1</strong> folio(s) válido(s) de <strong>1</strong>' in text
    assert 'Confirmar importación' in text
    assert EntregaFolio.query.count() == 0, 'la vista previa no debe crear nada'


def test_preview_marca_no_disponible(admin_client, tipo, centro):
    make_folio(tipo, anio=Y, numero=1000, estado='entregado')
    resp = post_importar(admin_client, [[1000, tipo.name, Y]], centro)
    text = resp.get_data(as_text=True)
    assert '<strong>0</strong> folio(s) válido(s) de <strong>1</strong>' in text
    assert 'no está disponible' in text


def test_preview_marca_inexistente(admin_client, tipo, centro):
    resp = post_importar(admin_client, [[9999, tipo.name, Y]], centro)
    text = resp.get_data(as_text=True)
    assert '<strong>0</strong> folio(s) válido(s) de <strong>1</strong>' in text
    assert 'no existe' in text


def test_confirm_registra_entrega(admin_client, tipo, centro):
    folio = make_folio(tipo, anio=Y, numero=1000)
    resp = confirmar(admin_client, [folio.id], centro)

    assert resp.status_code == 200
    assert EntregaFolio.query.count() == 1
    assert db.session.get(Folio, folio.id).estado == 'entregado'
    assert '1 entrega registrada' in resp.get_data(as_text=True)


def test_confirm_revalida_estado(admin_client, tipo, centro):
    """Folio que dejó de estar disponible entre previa y confirm → omitido."""
    folio = make_folio(tipo, anio=Y, numero=1000, estado='entregado')
    resp = confirmar(admin_client, [folio.id], centro)

    assert EntregaFolio.query.count() == 0
    assert 'Ningún folio sigue disponible' in resp.get_data(as_text=True)


def test_confirm_payload_invalido_no_crea_nada(admin_client, tipo, centro):
    resp = admin_client.post('/entregas/importar/confirmar', data={
        'payload': 'no-es-json',
        'centroId': str(centro.id),
        'fecha': '2026-10-01',
    }, follow_redirects=True)

    assert 'inválidos' in resp.get_data(as_text=True)
    assert EntregaFolio.query.count() == 0
