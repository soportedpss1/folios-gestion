"""Lote 1 de fixes UI/UX: badges de auditoría, colspan de estados vacíos,
Cancelar de importar nulos, fechas de sincronización, persistencia de filtros
de reportes y data-loading anti doble submit en formularios lentos."""

import re

import pytest

from app.extensions import db
from app.models.sync_config import get_config, registrar_intento
from app.services.audit import log_audit
from tests.conftest import make_user
from tests.test_importar_nulos import post_importar_nulos

Y = 2026


# --- auditoría: acciones no CRUD deben mostrar su badge ---


def test_auditoria_muestra_badge_para_backup_y_restore(admin_client, app, admin):
    with app.test_request_context():
        log_audit(admin.id, 'BACKUP', 'backup', 1, None, {'tablas': ['folios']})
        log_audit(admin.id, 'RESTORE', 'backup', 2, None, None)
        db.session.commit()

    body = admin_client.get('/auditoria/').get_data(as_text=True)
    assert '<span class="badge bg-secondary">BACKUP</span>' in body, \
        'la acción BACKUP queda con la celda vacía'
    assert '<span class="badge bg-secondary">RESTORE</span>' in body, \
        'la acción RESTORE queda con la celda vacía'


# --- estados vacíos: una sola celda con el colspan correcto ---


def _fila_vacia(client, ruta, texto):
    resp = client.get(ruta)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert texto in body, 'sin datos no se muestra el estado vacío'
    return body


def test_entregas_indice_vacio_colspan_sin_celdas_extra(app):
    make_user('lectura', 'lectura')
    client = app.test_client()
    client.post('/auth/login', data={'username': 'lectura', 'password': 'pass12345'})

    body = _fila_vacia(client, '/entregas/', 'No hay entregas registradas')
    assert '<td class="text-center text-muted py-4" colspan="5">' in body, \
        'sin permiso de edición hay 5 columnas: el colspan debe ser 5'
    assert 'padding:0;width:0' not in body, 'celdas fantasma en la fila vacía'


def test_devoluciones_indice_vacio_colspan_sin_celdas_extra(app):
    make_user('lectura', 'lectura')
    client = app.test_client()
    client.post('/auth/login', data={'username': 'lectura', 'password': 'pass12345'})

    body = _fila_vacia(client, '/devoluciones/', 'No hay devoluciones registradas')
    assert '<td class="text-center text-muted py-4" colspan="5">' in body
    assert 'padding:0;width:0' not in body


def test_recepcion_indice_vacio_sin_celdas_extra(admin_client):
    body = _fila_vacia(admin_client, '/recepcion/', 'No hay recepciones registradas')
    assert '<td class="text-center text-muted py-4" colspan="8">' in body
    assert 'padding:0;width:0' not in body


def test_centros_indice_vacio_sin_celdas_extra(admin_client):
    body = _fila_vacia(admin_client, '/centros/', 'No hay centros registrados')
    assert '<td class="text-center text-muted py-4" colspan="5">' in body
    assert 'padding:0;width:0' not in body


def test_certificados_indice_vacio_sin_celdas_extra(admin_client):
    body = _fila_vacia(admin_client, '/certificados/',
                       'No hay tipos de certificado registrados')
    assert '<td class="text-center text-muted py-4" colspan="6">' in body
    assert '<td></td>' not in body, 'celdas fantasma en la fila vacía'


# --- importar nulos: Cancelar debe volver a su flujo, no al de digitado ---


def test_preview_nulos_cancelar_apunta_a_flujo_nulos(admin_client, tipo, folio):
    resp = post_importar_nulos(admin_client, [[1000]])
    body = resp.get_data(as_text=True)
    match = re.search(r'<a href="([^"]+)"[^>]*>Cancelar</a>', body)
    assert match, 'falta el enlace Cancelar en la vista previa'
    assert match.group(1) == '/folios/importar-nulos', \
        'Cancelar del modo nulos sale al flujo de digitado'


# --- reportes: los filtros de la URL deben marcarse en los selects ---


def test_reportes_filtros_persisten_en_selects(admin_client, app, tipo, centro):
    resp = admin_client.get(
        f'/reportes/?anioCert={Y}&tipoCert={tipo.id}'
        f'&centroId={centro.id}&estado=entregado')
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert f'<option value="{tipo.id}" selected>' in body, \
        'el tipo elegido no aparece marcado tras F5'
    assert f'<option value="{centro.id}" selected>' in body, \
        'el centro elegido no aparece marcado tras F5'
    assert '<option value="entregado" selected>' in body, \
        'el estado elegido no aparece marcado tras F5'


# --- sincronización: fechas legibles, no datetime crudo con microsegundos ---


def test_sincronizacion_fechas_formateadas(admin_client, app):
    cfg = get_config()
    cfg.activo = True
    db.session.commit()
    registrar_intento(cfg, error='fallo de prueba')

    body = admin_client.get('/sincronizacion/').get_data(as_text=True)
    assert 'Próximo intento' in body
    assert not re.search(r'\d{2}:\d{2}:\d{2}\.\d+', body), \
        'la página muestra datetime crudo con microsegundos'


# --- anti doble submit: forms lentos con data-loading ---


@pytest.mark.parametrize('ruta', [
    '/folios/importar',
    '/folios/importar-nulos',
    '/centros/importar',
    '/recepcion/importar',
    '/entregas/importar',
    '/devoluciones/importar',
    '/escaneos/subir',
    '/marca/',
    '/backup/',
    '/sincronizacion/',
])
def test_forms_lentos_tienen_data_loading(admin_client, ruta):
    resp = admin_client.get(ruta)
    assert resp.status_code == 200
    assert 'data-loading' in resp.get_data(as_text=True), \
        f'{ruta} sin data-loading: doble submit posible'


def test_preview_confirmar_importacion_tiene_data_loading(admin_client, tipo, folio):
    resp = post_importar_nulos(admin_client, [[1000]])
    body = resp.get_data(as_text=True)
    match = re.search(
        r'<form method="POST" action="[^"]*importar-nulos/confirmar"[^>]*>', body)
    assert match, 'falta el form de confirmación en la vista previa'
    assert 'data-loading' in match.group(0), \
        'Confirmar importación sin data-loading: doble clic = doble POST'
