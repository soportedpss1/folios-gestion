"""Ningún registro de recepción, entrega o devolución con fecha futura.

El límite es el día actual (hora local): hoy se acepta, mañana no. Aplica
a los formularios de create y edit, y a las importaciones — el rechazo en
importaciones va en el preview (fila por fila) y en la confirmación (el
hidden del payload es editable, se revalida ahí).
"""

import json
from datetime import date, timedelta
from io import BytesIO

from openpyxl import Workbook

from app.extensions import db
from app.models.devolucion_folio import DevolucionFolio
from app.models.entrega_folio import EntregaFolio
from app.models.recepcion_folio import RecepcionFolio
from tests.conftest import make_folio

Y = 2026
HOY = date.today()
MANANA = date.today() + timedelta(days=1)
MENSAJE = 'posterior a hoy'

HEADERS_RECEPCION = ['fecha', 'anioCert', 'tipoCert', 'folioInicial',
                     'folioFinal', 'usuario']
HEADERS_MOVIMIENTO = ['folio', 'tipoCert', 'anioCert', 'fecha', 'centro',
                      'usuario']


def ddmmaa(d):
    return d.strftime('%d/%m/%Y')


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


def post_importar(client, url, headers, rows, nombre='import.xlsx'):
    return client.post(url, data={
        'archivo': (make_xlsx(headers, rows), nombre),
    }, content_type='multipart/form-data')


# ------------------------------------------------------------- create forms


def test_recepcion_create_fecha_futura_rechazada(admin_client, tipo):
    resp = admin_client.post('/recepcion/create', data={
        'fecha': ddmmaa(MANANA), 'anioCert': Y, 'tipoCert': tipo.id,
        'folioInicial': 100, 'folioFinal': 105,
    }, follow_redirects=True)

    assert MENSAJE in resp.get_data(as_text=True), \
        'sin mensaje de validación de fecha futura'
    assert RecepcionFolio.query.count() == 0, \
        'una fecha futura no debe crear recepción'


def test_recepcion_create_fecha_hoy_aceptada(admin_client, tipo):
    resp = admin_client.post('/recepcion/create', data={
        'fecha': ddmmaa(HOY), 'anioCert': Y, 'tipoCert': tipo.id,
        'folioInicial': 100, 'folioFinal': 105,
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert RecepcionFolio.query.count() == 1, \
        'hoy debe seguir aceptándose (el límite es el día actual)'
    assert RecepcionFolio.query.one().fecha == HOY


def test_entregas_create_fecha_futura_rechazada(
        auth_client, app, tipo, centro, operador):
    folio = make_folio(tipo, anio=Y, numero=8101)
    db.session.commit()

    resp = auth_client.post('/entregas/create', data={
        'folio_ids': [folio.id], 'fechaEntrega': ddmmaa(MANANA),
        'centroId': centro.id,
    }, follow_redirects=True)

    assert MENSAJE in resp.get_data(as_text=True)
    assert EntregaFolio.query.count() == 0, \
        'una fecha futura no debe crear entrega'
    db.session.refresh(folio)
    assert folio.estado == 'disponible', \
        'el folio cambió de estado con una entrega rechazada'


def test_entregas_create_fecha_hoy_aceptada(
        auth_client, app, tipo, centro, operador):
    folio = make_folio(tipo, anio=Y, numero=8102)
    db.session.commit()

    resp = auth_client.post('/entregas/create', data={
        'folio_ids': [folio.id], 'fechaEntrega': ddmmaa(HOY),
        'centroId': centro.id,
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert EntregaFolio.query.count() == 1, 'hoy debe aceptarse'
    assert EntregaFolio.query.one().fechaEntrega == HOY


def test_devoluciones_create_fecha_futura_rechazada(
        auth_client, app, folio_entregado, centro, operador):
    resp = auth_client.post('/devoluciones/create', data={
        'folio_ids': [folio_entregado.id],
        'fechaDevolucion': ddmmaa(MANANA),
        'centroId': centro.id,
    }, follow_redirects=True)

    assert MENSAJE in resp.get_data(as_text=True)
    assert DevolucionFolio.query.count() == 0, \
        'una fecha futura no debe crear devolución'
    db.session.refresh(folio_entregado)
    assert folio_entregado.estado == 'entregado', \
        'el folio cambió de estado con una devolución rechazada'


def test_devoluciones_create_fecha_hoy_aceptada(
        auth_client, app, folio_entregado, centro, operador):
    resp = auth_client.post('/devoluciones/create', data={
        'folio_ids': [folio_entregado.id],
        'fechaDevolucion': ddmmaa(HOY),
        'centroId': centro.id,
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert DevolucionFolio.query.count() == 1, 'hoy debe aceptarse'
    assert DevolucionFolio.query.one().fechaDevolucion == HOY


# --------------------------------------------------------------- edit forms


def test_recepcion_edit_fecha_futura_rechazada(admin_client, tipo, operador):
    admin_client.post('/recepcion/create', data={
        'fecha': '01/10/2026', 'anioCert': Y, 'tipoCert': tipo.id,
        'folioInicial': 100, 'folioFinal': 105,
    }, follow_redirects=True)
    recepcion = RecepcionFolio.query.one()

    resp = admin_client.post(f'/recepcion/{recepcion.id}/edit', data={
        'fecha': ddmmaa(MANANA), 'anioCert': Y, 'tipoCert': tipo.id,
        'folioInicial': 100, 'folioFinal': 105, 'usuario': operador.id,
    }, follow_redirects=True)

    assert MENSAJE in resp.get_data(as_text=True)
    db.session.refresh(recepcion)
    assert recepcion.fecha == date(2026, 10, 1), \
        'una fecha futura no debe sobrescribir la recepción'


def test_entregas_edit_fecha_futura_rechazada(auth_client, app, centro, folio_entregado):
    entrega = folio_entregado.entrega

    resp = auth_client.post(f'/entregas/{entrega.id}/edit', data={
        'folio_id': folio_entregado.id, 'fechaEntrega': ddmmaa(MANANA),
        'centroId': centro.id,
    }, follow_redirects=True)

    assert MENSAJE in resp.get_data(as_text=True)
    db.session.refresh(entrega)
    assert entrega.fechaEntrega == date(2026, 9, 1), \
        'una fecha futura no debe sobrescribir la entrega'


def test_devoluciones_edit_fecha_futura_rechazada(
        auth_client, app, centro, folio_entregado, operador):
    auth_client.post('/devoluciones/create', data={
        'folio_ids': [folio_entregado.id], 'fechaDevolucion': '10/10/2026',
        'centroId': centro.id,
    }, follow_redirects=True)
    devolucion = DevolucionFolio.query.one()

    resp = auth_client.post(f'/devoluciones/{devolucion.id}/edit', data={
        'folio_id': folio_entregado.id,
        'fechaDevolucion': ddmmaa(MANANA),
        'centroId': centro.id,
    }, follow_redirects=True)

    assert MENSAJE in resp.get_data(as_text=True)
    db.session.refresh(devolucion)
    assert devolucion.fechaDevolucion == date(2026, 10, 10), \
        'una fecha futura no debe sobrescribir la devolución'


# -------------------------------------------------------------- importación


def test_preview_recepcion_fecha_futura_rechazada(admin_client, tipo):
    resp = post_importar(admin_client, '/recepcion/importar',
                         HEADERS_RECEPCION,
                         [[MANANA.isoformat(), Y, tipo.name, 1, 5,
                           'adminuser']])
    text = resp.get_data(as_text=True)

    assert MENSAJE in text, 'la fila con fecha futura no se marca en el preview'
    assert '<strong>0</strong> fila(s) válida(s) de <strong>1</strong>' in text
    assert RecepcionFolio.query.count() == 0


def test_preview_recepcion_fecha_hoy_valida(admin_client, tipo):
    resp = post_importar(admin_client, '/recepcion/importar',
                         HEADERS_RECEPCION,
                         [[HOY.isoformat(), Y, tipo.name, 1, 5, 'adminuser']])
    text = resp.get_data(as_text=True)

    assert '<strong>1</strong> fila(s) válida(s) de <strong>1</strong>' in text, \
        'hoy debe seguir siendo fila válida en el preview'


def test_confirm_recepcion_fecha_futura_rechazada(admin_client, tipo):
    payload = json.dumps([{
        'fecha': MANANA.isoformat(), 'anioCert': Y, 'tipoCert_id': tipo.id,
        'folioInicial': 1, 'folioFinal': 5,
    }])
    resp = admin_client.post('/recepcion/importar/confirmar',
                             data={'payload': payload}, follow_redirects=True)

    assert 'inválidos' in resp.get_data(as_text=True)
    assert RecepcionFolio.query.count() == 0, \
        'el hidden editable con fecha futura no debe crear recepciones'


def test_preview_entrega_fecha_futura_rechazada(admin_client, tipo, centro):
    resp = post_importar(admin_client, '/entregas/importar',
                         HEADERS_MOVIMIENTO,
                         [[1000, tipo.name, Y, ddmmaa(MANANA), centro.name,
                           'adminuser']])
    text = resp.get_data(as_text=True)

    assert MENSAJE in text
    assert '<strong>0</strong> folio(s) válido(s) de <strong>1</strong>' in text
    assert EntregaFolio.query.count() == 0


def test_preview_entrega_fecha_hoy_valida(admin_client, tipo, centro):
    make_folio(tipo, anio=Y, numero=1000)
    db.session.commit()

    resp = post_importar(admin_client, '/entregas/importar',
                         HEADERS_MOVIMIENTO,
                         [[1000, tipo.name, Y, ddmmaa(HOY), centro.name,
                           'adminuser']])
    text = resp.get_data(as_text=True)

    assert '<strong>1</strong> folio(s) válido(s) de <strong>1</strong>' in text, \
        'hoy debe seguir siendo fila válida en el preview'


def test_confirm_entrega_fecha_futura_rechazada(admin_client, tipo, centro):
    folio = make_folio(tipo, anio=Y, numero=1000)
    db.session.commit()

    resp = admin_client.post('/entregas/importar/confirmar', data={
        'payload': json.dumps([{'id': folio.id,
                                'fecha': MANANA.isoformat(),
                                'centroId': centro.id}]),
    }, follow_redirects=True)

    assert 'inválidos' in resp.get_data(as_text=True)
    assert EntregaFolio.query.count() == 0, \
        'el hidden editable con fecha futura no debe crear entregas'
    db.session.refresh(folio)
    assert folio.estado == 'disponible'


def test_preview_devolucion_fecha_futura_rechazada(admin_client, tipo, centro):
    resp = post_importar(admin_client, '/devoluciones/importar',
                         HEADERS_MOVIMIENTO,
                         [[1000, tipo.name, Y, ddmmaa(MANANA), centro.name,
                           'adminuser']])
    text = resp.get_data(as_text=True)

    assert MENSAJE in text
    assert '<strong>0</strong> folio(s) válido(s) de <strong>1</strong>' in text
    assert DevolucionFolio.query.count() == 0


def test_preview_devolucion_fecha_hoy_valida(admin_client, folio_entregado, centro, tipo):
    resp = post_importar(admin_client, '/devoluciones/importar',
                         HEADERS_MOVIMIENTO,
                         [[folio_entregado.folio, tipo.name, Y, ddmmaa(HOY),
                           centro.name, 'operador']])
    text = resp.get_data(as_text=True)

    assert '<strong>1</strong> folio(s) válido(s) de <strong>1</strong>' in text, \
        'hoy debe seguir siendo fila válida en el preview'


def test_confirm_devolucion_fecha_futura_rechazada(admin_client, folio_entregado, centro):
    resp = admin_client.post('/devoluciones/importar/confirmar', data={
        'payload': json.dumps([{'id': folio_entregado.id,
                                'fecha': MANANA.isoformat(),
                                'centroId': centro.id}]),
    }, follow_redirects=True)

    assert 'inválidos' in resp.get_data(as_text=True)
    assert DevolucionFolio.query.count() == 0, \
        'el hidden editable con fecha futura no debe crear devoluciones'
    db.session.refresh(folio_entregado)
    assert folio_entregado.estado == 'entregado'
