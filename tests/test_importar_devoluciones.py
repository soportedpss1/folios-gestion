"""Importar devoluciones de folios desde .xlsx (vista previa + confirmación).

La fecha va por fila en el Excel (columna obligatoria `fecha`): no hay campo
de fecha en el formulario ni hidden en la confirmación. Cada movimiento
guarda la fecha de su fila.
"""

import json
from datetime import date
from io import BytesIO

from openpyxl import Workbook, load_workbook

from app.extensions import db
from app.models.centro import Centro
from app.models.devolucion_folio import DevolucionFolio
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
        '/devoluciones/importar',
        data={
            'archivo': (make_xlsx(HEADERS, rows), nombre),
            'centroId': str(centro.id),
        },
        content_type='multipart/form-data',
    )


def confirmar(client, items, centro):
    """items: lista de {'id': folio_id, 'fecha': 'dd/mm/aaaa'|'aaaa-mm-dd'}."""
    return client.post(
        '/devoluciones/importar/confirmar',
        data={
            'payload': json.dumps(items),
            'centroId': str(centro.id),
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
        'la plantilla lleva fecha obligatoria y usuario final (opcional)'


def test_formulario_no_tiene_campo_fecha(admin_client, centro):
    text = admin_client.get('/devoluciones/importar').get_data(as_text=True)
    assert 'id="fechaDevolucion"' not in text, 'la fecha se toma del Excel'


def test_preview_resuelve_entregado_al_centro(admin_client, folio_entregado, centro, tipo):
    resp = post_importar(admin_client,
                         [[folio_entregado.folio, tipo.name, Y, '02/10/2026']], centro)
    text = resp.get_data(as_text=True)
    assert '<strong>1</strong> folio(s) válido(s) de <strong>1</strong>' in text
    assert 'Confirmar importación' in text
    assert '02/10/2026' in text, 'la vista previa muestra la fecha por fila'
    assert '<input type="hidden" name="fecha"' not in text, 'sin hidden de fecha'
    assert DevolucionFolio.query.count() == 0, 'la vista previa no debe crear nada'


def test_preview_rechaza_folio_de_otro_centro(admin_client, folio_entregado, tipo):
    otro = Centro(name='Otro Centro', telefono='555', direccion='Calle 1', activo=True)
    db.session.add(otro)
    db.session.commit()

    resp = post_importar(admin_client,
                         [[folio_entregado.folio, tipo.name, Y, '2026-10-02']], otro)
    text = resp.get_data(as_text=True)
    assert '<strong>0</strong> folio(s) válido(s) de <strong>1</strong>' in text
    assert 'no lo tiene entregado' in text


def test_preview_rechaza_folio_no_entregado(admin_client, tipo, centro):
    make_folio(tipo, anio=Y, numero=1000, estado='disponible')
    resp = post_importar(admin_client, [[1000, tipo.name, Y, '2026-10-02']], centro)
    text = resp.get_data(as_text=True)
    assert '<strong>0</strong> folio(s) válido(s) de <strong>1</strong>' in text
    assert 'no está entregado' in text


def test_preview_rechaza_archivo_sin_columna_fecha(admin_client, folio_entregado, centro, tipo):
    resp = admin_client.post('/devoluciones/importar', data={
        'archivo': (make_xlsx(['folio', 'tipoCert', 'anioCert'],
                              [[folio_entregado.folio, tipo.name, Y]]),
                    'sin-fecha.xlsx'),
        'centroId': str(centro.id),
    }, content_type='multipart/form-data')
    assert 'Encabezados incorrectos' in resp.get_data(as_text=True)


def test_preview_marca_fecha_invalida(admin_client, folio_entregado, centro, tipo):
    resp = post_importar(admin_client,
                         [[folio_entregado.folio, tipo.name, Y, 'mañana']], centro)
    text = resp.get_data(as_text=True)
    assert '<strong>0</strong> folio(s) válido(s) de <strong>1</strong>' in text
    assert 'Fecha inválida' in text


def test_confirm_registra_devolucion(admin_client, folio_entregado, centro, tipo):
    resp = confirmar(admin_client,
                     [{'id': folio_entregado.id, 'fecha': '2026-10-02'}], centro)

    assert resp.status_code == 200
    assert DevolucionFolio.query.count() == 1
    assert db.session.get(Folio, folio_entregado.id).estado == 'devuelto'
    assert DevolucionFolio.query.one().fechaDevolucion == date(2026, 10, 2)
    assert '1 devolución registrada' in resp.get_data(as_text=True)


def test_confirm_respeta_fecha_distinta_por_fila(admin_client, folio_entregado,
                                                 centro, tipo, operador):
    from app.models.entrega_folio import EntregaFolio
    otro = make_folio(tipo, anio=Y, numero=1001, estado='entregado')
    db.session.add(EntregaFolio(folio_id=otro.id, fechaEntrega=date(2026, 9, 1),
                                centroId=centro.id, userId=operador.id))
    db.session.commit()

    resp = confirmar(admin_client, [
        {'id': folio_entregado.id, 'fecha': '2026-10-02'},
        {'id': otro.id, 'fecha': '07/10/2026'},
    ], centro)

    assert resp.status_code == 200
    assert DevolucionFolio.query.count() == 2
    assert {d.fechaDevolucion for d in DevolucionFolio.query.all()} == \
        {date(2026, 10, 2), date(2026, 10, 7)}


def test_confirm_revalida_centro(admin_client, folio_entregado, tipo):
    """Folio entregado a otro centro → confirm no lo devuelve."""
    otro = Centro(name='Otro Centro', telefono='555', direccion='Calle 1', activo=True)
    db.session.add(otro)
    db.session.commit()

    resp = confirmar(admin_client,
                     [{'id': folio_entregado.id, 'fecha': '2026-10-02'}], otro)

    assert DevolucionFolio.query.count() == 0
    assert 'Ningún folio sigue entregado' in resp.get_data(as_text=True)
    assert db.session.get(Folio, folio_entregado.id).estado == 'entregado'


def test_confirm_payload_invalido_no_crea_nada(admin_client, folio_entregado, centro):
    resp = admin_client.post('/devoluciones/importar/confirmar', data={
        'payload': 'no-es-json',
        'centroId': str(centro.id),
    }, follow_redirects=True)

    assert 'inválidos' in resp.get_data(as_text=True)
    assert DevolucionFolio.query.count() == 0


def test_confirm_rechaza_fecha_invalida_en_payload(admin_client, folio_entregado, centro):
    """El hidden del confirm es editable: fecha faltante o basura → rechazo."""
    resp = confirmar(admin_client,
                     [{'id': folio_entregado.id}], centro)

    assert 'inválidos' in resp.get_data(as_text=True)
    assert DevolucionFolio.query.count() == 0
