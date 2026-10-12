"""Importar entregas de folios desde .xlsx (vista previa + confirmación).

La fecha va por fila en el Excel (columna obligatoria `fecha`): no hay campo
de fecha en el formulario ni hidden en la confirmación. Cada movimiento
guarda la fecha de su fila.
"""

import json
from datetime import date
from io import BytesIO

from openpyxl import Workbook, load_workbook

from app.extensions import db
from app.models.entrega_folio import EntregaFolio
from app.models.folio import Folio
from tests.conftest import make_folio

HEADERS = ['folio', 'tipoCert', 'anioCert', 'fecha']
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


def post_importar(client, rows, centro, nombre='import.xlsx'):
    return client.post(
        '/entregas/importar',
        data={
            'archivo': (make_xlsx(HEADERS, rows), nombre),
            'centroId': str(centro.id),
        },
        content_type='multipart/form-data',
    )


def confirmar(client, items, centro):
    """items: lista de {'id': folio_id, 'fecha': 'dd/mm/aaaa'|'aaaa-mm-dd'}."""
    return client.post(
        '/entregas/importar/confirmar',
        data={
            'payload': json.dumps(items),
            'centroId': str(centro.id),
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
        'la plantilla lleva fecha obligatoria y usuario final (opcional)'


def test_formulario_no_tiene_campo_fecha(admin_client, centro):
    text = admin_client.get('/entregas/importar').get_data(as_text=True)
    assert 'id="fechaEntrega"' not in text, 'la fecha se toma del Excel'


def test_preview_resuelve_disponible(admin_client, tipo, centro):
    make_folio(tipo, anio=Y, numero=1000)
    resp = post_importar(admin_client, [[1000, tipo.name, Y, '01/10/2026']], centro)
    text = resp.get_data(as_text=True)
    assert '<strong>1</strong> folio(s) válido(s) de <strong>1</strong>' in text
    assert 'Confirmar importación' in text
    assert '01/10/2026' in text, 'la vista previa muestra la fecha por fila'
    assert '<input type="hidden" name="fecha"' not in text, 'sin hidden de fecha'
    assert EntregaFolio.query.count() == 0, 'la vista previa no debe crear nada'


def test_preview_marca_no_disponible(admin_client, tipo, centro):
    make_folio(tipo, anio=Y, numero=1000, estado='entregado')
    resp = post_importar(admin_client, [[1000, tipo.name, Y, '2026-10-01']], centro)
    text = resp.get_data(as_text=True)
    assert '<strong>0</strong> folio(s) válido(s) de <strong>1</strong>' in text
    assert 'no está disponible' in text


def test_preview_marca_inexistente(admin_client, tipo, centro):
    resp = post_importar(admin_client, [[9999, tipo.name, Y, '2026-10-01']], centro)
    text = resp.get_data(as_text=True)
    assert '<strong>0</strong> folio(s) válido(s) de <strong>1</strong>' in text
    assert 'no existe' in text


def test_preview_rechaza_archivo_sin_columna_fecha(admin_client, tipo, centro):
    resp = admin_client.post('/entregas/importar', data={
        'archivo': (make_xlsx(['folio', 'tipoCert', 'anioCert'],
                              [[1000, tipo.name, Y]]), 'sin-fecha.xlsx'),
        'centroId': str(centro.id),
    }, content_type='multipart/form-data')
    assert 'Encabezados incorrectos' in resp.get_data(as_text=True)


def test_preview_marca_fecha_invalida(admin_client, tipo, centro):
    make_folio(tipo, anio=Y, numero=1000)
    resp = post_importar(admin_client, [[1000, tipo.name, Y, 'ayer']], centro)
    text = resp.get_data(as_text=True)
    assert '<strong>0</strong> folio(s) válido(s) de <strong>1</strong>' in text
    assert 'Fecha inválida' in text


def test_confirm_registra_entrega(admin_client, tipo, centro):
    folio = make_folio(tipo, anio=Y, numero=1000)
    resp = confirmar(admin_client,
                     [{'id': folio.id, 'fecha': '2026-10-01'}], centro)

    assert resp.status_code == 200
    assert EntregaFolio.query.count() == 1
    assert db.session.get(Folio, folio.id).estado == 'entregado'
    assert EntregaFolio.query.one().fechaEntrega == date(2026, 10, 1)
    assert '1 entrega registrada' in resp.get_data(as_text=True)


def test_confirm_respeta_fecha_distinta_por_fila(admin_client, tipo, centro):
    f1 = make_folio(tipo, anio=Y, numero=1000)
    f2 = make_folio(tipo, anio=Y, numero=1001)
    resp = confirmar(admin_client, [
        {'id': f1.id, 'fecha': '2026-10-01'},
        {'id': f2.id, 'fecha': '05/10/2026'},
    ], centro)

    assert resp.status_code == 200
    assert EntregaFolio.query.count() == 2
    assert {e.fechaEntrega for e in EntregaFolio.query.all()} == \
        {date(2026, 10, 1), date(2026, 10, 5)}


def test_confirm_revalida_estado(admin_client, tipo, centro):
    """Folio que dejó de estar disponible entre previa y confirm → omitido."""
    folio = make_folio(tipo, anio=Y, numero=1000, estado='entregado')
    resp = confirmar(admin_client,
                     [{'id': folio.id, 'fecha': '2026-10-01'}], centro)

    assert EntregaFolio.query.count() == 0
    assert 'Ningún folio sigue disponible' in resp.get_data(as_text=True)


def test_confirm_payload_invalido_no_crea_nada(admin_client, tipo, centro):
    resp = admin_client.post('/entregas/importar/confirmar', data={
        'payload': 'no-es-json',
        'centroId': str(centro.id),
    }, follow_redirects=True)

    assert 'inválidos' in resp.get_data(as_text=True)
    assert EntregaFolio.query.count() == 0


def test_confirm_rechaza_fecha_invalida_en_payload(admin_client, tipo, centro):
    """El hidden del confirm es editable: fecha faltante o basura → rechazo."""
    folio = make_folio(tipo, anio=Y, numero=1000)
    resp = confirmar(admin_client, [{'id': folio.id, 'fecha': 'no-fecha'}],
                     centro)

    assert 'inválidos' in resp.get_data(as_text=True)
    assert EntregaFolio.query.count() == 0
