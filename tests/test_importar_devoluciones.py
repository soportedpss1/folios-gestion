"""Importar devoluciones de folios desde .xlsx (vista previa + confirmación)."""

import json
from io import BytesIO

from openpyxl import Workbook, load_workbook

from app.extensions import db
from app.models.centro import Centro
from app.models.devolucion_folio import DevolucionFolio
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


def post_importar(client, rows, centro, fecha='2026-10-02', nombre='import.xlsx'):
    return client.post(
        '/devoluciones/importar',
        data={
            'archivo': (make_xlsx(HEADERS, rows), nombre),
            'centroId': str(centro.id),
            'fechaDevolucion': fecha,
        },
        content_type='multipart/form-data',
    )


def confirmar(client, ids, centro, fecha='2026-10-02'):
    return client.post(
        '/devoluciones/importar/confirmar',
        data={
            'payload': json.dumps(ids),
            'centroId': str(centro.id),
            'fecha': fecha,
        },
        follow_redirects=True,
    )


def test_importar_requiere_login(client):
    assert client.get('/devoluciones/importar').status_code == 302
    assert client.post('/devoluciones/importar/confirmar').status_code == 302


def test_plantilla_es_xlsx_con_headers(admin_client):
    resp = admin_client.get('/devoluciones/plantilla')
    assert resp.status_code == 200
    assert 'spreadsheetml' in resp.content_type
    wb = load_workbook(BytesIO(resp.data))
    assert [c.value for c in wb.active[1]] == HEADERS + ['usuario'], \
        'la plantilla trae la columna usuario final (opcional al importar)'


def test_preview_resuelve_entregado_al_centro(admin_client, folio_entregado, centro, tipo):
    resp = post_importar(admin_client, [[folio_entregado.folio, tipo.name, Y]], centro)
    text = resp.get_data(as_text=True)
    assert '<strong>1</strong> folio(s) válido(s) de <strong>1</strong>' in text
    assert 'Confirmar importación' in text
    assert DevolucionFolio.query.count() == 0, 'la vista previa no debe crear nada'


def test_preview_rechaza_folio_de_otro_centro(admin_client, folio_entregado, tipo):
    otro = Centro(name='Otro Centro', telefono='555', direccion='Calle 1', activo=True)
    db.session.add(otro)
    db.session.commit()

    resp = post_importar(admin_client, [[folio_entregado.folio, tipo.name, Y]], otro)
    text = resp.get_data(as_text=True)
    assert '<strong>0</strong> folio(s) válido(s) de <strong>1</strong>' in text
    assert 'no lo tiene entregado' in text


def test_preview_rechaza_folio_no_entregado(admin_client, tipo, centro):
    make_folio(tipo, anio=Y, numero=1000, estado='disponible')
    resp = post_importar(admin_client, [[1000, tipo.name, Y]], centro)
    text = resp.get_data(as_text=True)
    assert '<strong>0</strong> folio(s) válido(s) de <strong>1</strong>' in text
    assert 'no está entregado' in text


def test_confirm_registra_devolucion(admin_client, folio_entregado, centro, tipo):
    resp = confirmar(admin_client, [folio_entregado.id], centro)

    assert resp.status_code == 200
    assert DevolucionFolio.query.count() == 1
    assert db.session.get(Folio, folio_entregado.id).estado == 'devuelto'
    assert '1 devolución registrada' in resp.get_data(as_text=True)


def test_confirm_revalida_centro(admin_client, folio_entregado, tipo):
    """Folio entregado a otro centro → confirm no lo devuelve."""
    otro = Centro(name='Otro Centro', telefono='555', direccion='Calle 1', activo=True)
    db.session.add(otro)
    db.session.commit()

    resp = confirmar(admin_client, [folio_entregado.id], otro)

    assert DevolucionFolio.query.count() == 0
    assert 'Ningún folio sigue entregado' in resp.get_data(as_text=True)
    assert db.session.get(Folio, folio_entregado.id).estado == 'entregado'


def test_confirm_payload_invalido_no_crea_nada(admin_client, folio_entregado, centro):
    resp = admin_client.post('/devoluciones/importar/confirmar', data={
        'payload': 'no-es-json',
        'centroId': str(centro.id),
        'fecha': '2026-10-02',
    }, follow_redirects=True)

    assert 'inválidos' in resp.get_data(as_text=True)
    assert DevolucionFolio.query.count() == 0
