"""Copias de respaldo: descarga, validación y restauración transaccional."""

import io
import json
import re

import pytest

from app.extensions import db
from app.models.centro import Centro
from app.models.permiso_usuario import PermisoUsuario
from app.models.usuario import Usuario
from app.services.backup import TABLAS_ORDEN, _json_default, crear_backup, restaurar_backup
from tests.conftest import make_user


def _crudo(payload):
    return (payload if isinstance(payload, bytes)
            else json.dumps(payload, default=_json_default).encode('utf-8'))


def _analizar(client, payload, filename='respaldo.json'):
    """POST /backup/previsualizar: analiza el archivo SIN restaurar nada."""
    return client.post(
        '/backup/previsualizar',
        data={'archivo': (io.BytesIO(_crudo(payload)), filename)},
        content_type='multipart/form-data',
        follow_redirects=True,
    )


def _token(html):
    """Token de confirmación que el preview deja en la página."""
    encuentro = re.search(r'name="token"[^>]*value="([^"]+)"', html)
    assert encuentro, 'el preview no ofreció confirmación'
    return encuentro.group(1)


def _restaurar(client, payload, filename='respaldo.json'):
    """Flujo completo: analizar y luego confirmar con el token del preview."""
    preview = _analizar(client, payload, filename)
    token = _token(preview.get_data(as_text=True))
    return client.post('/backup/restaurar', data={'token': token},
                       follow_redirects=True)


def test_operador_no_accede(auth_client):
    assert auth_client.get('/backup/').status_code == 302
    assert auth_client.get('/backup/descargar').status_code == 302
    assert auth_client.post('/backup/previsualizar').status_code == 302
    assert auth_client.post('/backup/restaurar').status_code == 302


def test_admin_panel(admin_client):
    resp = admin_client.get('/backup/')
    text = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert 'Copias de respaldo' in text
    assert 'usuarios' in text


def test_descargar_incluye_todas_las_tablas(admin_client, centro):
    resp = admin_client.get('/backup/descargar')
    assert resp.status_code == 200
    assert 'attachment' in resp.headers['Content-Disposition']

    payload = json.loads(resp.get_data())
    assert payload['meta']['formato'] == 1
    assert set(TABLAS_ORDEN) <= set(payload['meta']['tablas'])
    assert payload['meta']['tablas']['centros'] == 1
    assert payload['datos']['centros'][0]['name'] == centro.name
    assert payload['meta']['alembic'] is None  # SQLite sin alembic_version


def test_descargar_deja_auditoria(admin_client):
    from app.models.audit_log import AuditLog
    admin_client.get('/backup/descargar')
    assert AuditLog.query.filter_by(accion='BACKUP').count() == 1


def test_roundtrip(admin_client, centro):
    respaldo = json.loads(admin_client.get('/backup/descargar').get_data())

    db.session.delete(centro)
    db.session.commit()
    assert Centro.query.count() == 0

    resp = _restaurar(admin_client, respaldo)
    assert 'Respaldo restaurado' in resp.get_data(as_text=True)
    assert Centro.query.filter_by(name='Centro de Prueba').count() == 1


def test_json_invalido_no_toca_datos(admin_client, centro):
    resp = _analizar(admin_client, b'no es json {{{')
    assert 'no es JSON válido' in resp.get_data(as_text=True)
    assert Centro.query.count() == 1


def test_formato_desconocido_rechazado(admin_client, centro):
    resp = _analizar(admin_client, {'meta': {'formato': 99}, 'datos': {'centros': []}})
    assert 'Formato de respaldo desconocido' in resp.get_data(as_text=True)
    assert Centro.query.count() == 1


def test_alembic_distinto_con_esquema_se_restaura(admin_client, centro):
    """El esquema declarado basta: la versión de Alembic deja de bloquear."""
    respaldo = crear_backup()
    respaldo['meta']['alembic'] = 'version_que_no_es'
    resp = _restaurar(admin_client, respaldo)
    assert 'Respaldo restaurado' in resp.get_data(as_text=True)
    assert Centro.query.filter_by(name='Centro de Prueba').count() == 1


def test_respaldo_viejo_sin_esquema_y_alembic_distinto_rechazado(admin_client, centro):
    respaldo = crear_backup()
    del respaldo['meta']['esquema']
    respaldo['meta']['alembic'] = 'version_que_no_es'
    resp = _analizar(admin_client, respaldo)
    assert 'otra versión del esquema' in resp.get_data(as_text=True)
    assert Centro.query.count() == 1


def test_tabla_desconocida_rechazado(admin_client, centro):
    resp = _analizar(admin_client, {'meta': {'formato': 1, 'alembic': None},
                                    'datos': {'tabla_inexistente': []}})
    assert 'Tabla desconocida' in resp.get_data(as_text=True)
    assert Centro.query.count() == 1


def test_fila_invalida_no_toca_datos(admin_client, centro):
    respaldo = crear_backup()
    # Fila sin columnas: pasa la validación de claves, falla el NOT NULL al
    # insertar → rollback total, los datos originales quedan intactos.
    respaldo['datos']['centros'] = [{}]
    resp = _restaurar(admin_client, respaldo)
    assert 'no se aplicó ningún cambio' in resp.get_data(as_text=True)
    assert Centro.query.filter_by(name='Centro de Prueba').count() == 1


def test_restore_deja_auditoria(admin_client, centro):
    from app.models.audit_log import AuditLog
    respaldo = json.loads(admin_client.get('/backup/descargar').get_data())
    _restaurar(admin_client, respaldo)
    log = AuditLog.query.filter_by(accion='RESTORE').first()
    assert log is not None
    assert log.datos_nuevos['filas'] >= 1


def test_campo_requerido(admin_client):
    resp = admin_client.post('/backup/previsualizar', data={},
                             content_type='multipart/form-data',
                             follow_redirects=True)
    assert 'Seleccione un archivo' in resp.get_data(as_text=True)


def test_preview_no_toca_datos(admin_client, centro):
    respaldo = crear_backup()
    respaldo['datos']['centros'][0]['name'] = 'Centro Nuevo'

    html = _analizar(admin_client, respaldo).get_data(as_text=True)
    assert 'Restaurar' in html
    assert Centro.query.filter_by(name='Centro de Prueba').count() == 1
    assert Centro.query.filter_by(name='Centro Nuevo').count() == 0


def test_preview_muestra_columnas_a_rellenar(admin_client, centro):
    respaldo = crear_backup()
    respaldo['datos']['centros'][0].pop('activo')
    respaldo['meta']['esquema']['centros'].remove('activo')

    html = _analizar(admin_client, respaldo).get_data(as_text=True)
    assert 'activo' in html
    assert _token(html)  # ofrece confirmación: la columna tiene default


def test_preview_ignora_columna_obsoleta(admin_client, centro):
    respaldo = crear_backup()
    respaldo['datos']['centros'][0]['col_obsoleta'] = 'x'
    respaldo['meta']['esquema']['centros'].append('col_obsoleta')

    html = _analizar(admin_client, respaldo).get_data(as_text=True)
    assert 'col_obsoleta' in html
    assert _token(html)


def test_preview_bloquea_columna_sin_default(admin_client, centro):
    respaldo = crear_backup()
    respaldo['datos']['centros'][0].pop('name')
    respaldo['meta']['esquema']['centros'].remove('name')

    html = _analizar(admin_client, respaldo).get_data(as_text=True)
    assert 'centros' in html and 'name' in html
    assert 'name="token"' not in html
    assert Centro.query.count() == 1


def test_preview_bloquea_respaldo_sin_usuarios(admin_client, centro):
    respaldo = crear_backup()
    del respaldo['datos']['usuarios']
    del respaldo['meta']['esquema']['usuarios']

    html = _analizar(admin_client, respaldo).get_data(as_text=True)
    assert 'usuarios' in html
    assert 'name="token"' not in html


def test_preview_señala_tablas_que_quedan_vacias(admin_client, centro):
    respaldo = crear_backup()
    del respaldo['datos']['marca_config']
    del respaldo['meta']['esquema']['marca_config']

    html = _analizar(admin_client, respaldo).get_data(as_text=True)
    assert 'marca_config' in html
    assert _token(html)


def test_restaurar_sin_token_rechazado(admin_client, centro):
    respaldo = crear_backup()
    respaldo['datos']['centros'][0]['name'] = 'Centro Nuevo'

    resp = admin_client.post('/backup/restaurar', data={},
                             follow_redirects=True)
    html = resp.get_data(as_text=True)
    assert 'analizar' in html.lower()
    assert Centro.query.filter_by(name='Centro Nuevo').count() == 0
    assert Centro.query.filter_by(name='Centro de Prueba').count() == 1


def test_token_no_reutilizable(admin_client, centro):
    respaldo = crear_backup()
    preview = _analizar(admin_client, respaldo)
    token = _token(preview.get_data(as_text=True))

    assert admin_client.post('/backup/restaurar',
                             data={'token': token},
                             follow_redirects=True).status_code == 200
    resp = admin_client.post('/backup/restaurar', data={'token': token},
                             follow_redirects=True)
    html = resp.get_data(as_text=True)
    assert 'Respaldo restaurado' not in html
    assert Centro.query.count() == 1


def test_servicio_valida_sin_tocar_db(app, centro):
    from app.services.backup import ErrorRespaldo

    try:
        restaurar_backup({'meta': {'formato': 1}, 'datos': None})
    except ErrorRespaldo as exc:
        assert 'no contiene datos' in str(exc)
    else:
        raise AssertionError('debía lanzar ErrorRespaldo')
    assert Centro.query.count() == 1


def test_backup_serializa_tipos(app):
    make_user('respaldo', 'admin')
    payload = crear_backup()
    recargado = json.loads(json.dumps(payload, ensure_ascii=False, default=_json_default))
    assert recargado['meta']['tablas']['usuarios'] == 1
    assert 'marca_config' in recargado['datos']


# --- Tolerancia al esquema -------------------------------------------------


def test_backup_incluye_esquema(app, centro):
    payload = crear_backup()
    assert set(payload['meta']['esquema']) == set(TABLAS_ORDEN)
    assert payload['meta']['esquema']['centros'] == [
        'id', 'name', 'telefono', 'direccion', 'activo', 'created_at']


def test_analisis_reporta_diferencias(app, admin, centro):
    from app.services.backup import analizar_compatibilidad

    respaldo = crear_backup()
    for fila in respaldo['datos']['centros']:
        fila.pop('activo')
        fila['col_obsoleta'] = 'x'
    respaldo['meta']['esquema']['centros'] = [
        c for c in respaldo['meta']['esquema']['centros'] if c != 'activo']
    respaldo['meta']['esquema']['centros'].append('col_obsoleta')
    del respaldo['datos']['sync_config']
    del respaldo['meta']['esquema']['sync_config']

    diff = analizar_compatibilidad(respaldo['datos'], respaldo['meta']['esquema'])

    assert diff['ok'] is True
    assert diff['tablas']['centros']['filas'] == 1
    assert diff['tablas']['centros']['rellenar'] == ['activo']
    assert diff['tablas']['centros']['ignoradas'] == ['col_obsoleta']
    assert diff['tablas']['centros']['bloqueantes'] == []
    assert diff['vacias'] == ['sync_config']


def test_columna_nueva_con_default_se_rellena(app, admin, centro):
    respaldo = crear_backup()
    for fila in respaldo['datos']['centros']:
        fila.pop('activo')
    respaldo['meta']['esquema']['centros'].remove('activo')

    assert restaurar_backup(respaldo)['centros'] == 1
    assert Centro.query.one().activo is True


def test_columna_nueva_nullable_se_rellena_con_null(app, admin, centro):
    respaldo = crear_backup()
    for fila in respaldo['datos']['centros']:
        fila.pop('telefono')
    respaldo['meta']['esquema']['centros'].remove('telefono')

    restaurar_backup(respaldo)
    assert Centro.query.one().telefono is None


def test_columna_nueva_sin_default_bloquea(app, admin, centro):
    from app.services.backup import ErrorRespaldo

    respaldo = crear_backup()
    for fila in respaldo['datos']['centros']:
        fila.pop('name')
    respaldo['meta']['esquema']['centros'].remove('name')

    with pytest.raises(ErrorRespaldo) as excinfo:
        restaurar_backup(respaldo)
    assert 'centros' in str(excinfo.value)
    assert 'name' in str(excinfo.value)
    assert Centro.query.filter_by(name='Centro de Prueba').count() == 1


def test_columna_obsoleta_se_ignora(app, admin, centro):
    respaldo = crear_backup()
    for fila in respaldo['datos']['centros']:
        fila['col_obsoleta'] = 'x'
    respaldo['meta']['esquema']['centros'].append('col_obsoleta')

    restaurar_backup(respaldo)
    assert Centro.query.count() == 1


def test_alembic_distinto_con_esquema_se_restaura(app, admin, centro):
    respaldo = crear_backup()
    respaldo['meta']['alembic'] = 'version_de_otra_instalacion'

    restaurar_backup(respaldo)
    assert Centro.query.filter_by(name='Centro de Prueba').count() == 1


def test_sin_esquema_y_alembic_distinto_rechazado(app, centro):
    from app.services.backup import ErrorRespaldo

    respaldo = crear_backup()
    del respaldo['meta']['esquema']
    respaldo['meta']['alembic'] = 'version_de_otra_instalacion'

    with pytest.raises(ErrorRespaldo) as excinfo:
        restaurar_backup(respaldo)
    assert 'versión del esquema' in str(excinfo.value)
    assert Centro.query.count() == 1


def test_respaldo_parcial_no_rompe_fk(app, admin):
    """Falta una tabla hija: se vacía también, sin violar la FK de usuarios."""
    db.session.add(PermisoUsuario(user_id=admin.id, permiso='folios.edit'))
    db.session.commit()

    respaldo = crear_backup()
    del respaldo['datos']['permiso_usuarios']
    del respaldo['meta']['esquema']['permiso_usuarios']

    assert restaurar_backup(respaldo)['usuarios'] == 1
    assert PermisoUsuario.query.count() == 0
    assert Usuario.query.count() == 1


def test_respaldo_sin_usuarios_bloqueado(app, admin):
    from app.services.backup import ErrorRespaldo

    respaldo = crear_backup()
    del respaldo['datos']['usuarios']
    del respaldo['meta']['esquema']['usuarios']

    with pytest.raises(ErrorRespaldo) as excinfo:
        restaurar_backup(respaldo)
    assert 'usuarios' in str(excinfo.value)
    assert Usuario.query.count() == 1


def test_respaldo_usuarios_vacios_bloqueado(app, admin):
    from app.services.backup import ErrorRespaldo

    respaldo = crear_backup()
    respaldo['datos']['usuarios'] = []
    respaldo['meta']['esquema']['usuarios'] = []

    with pytest.raises(ErrorRespaldo) as excinfo:
        restaurar_backup(respaldo)
    assert 'usuarios' in str(excinfo.value)
    assert Usuario.query.count() == 1


def test_previsualizar_servicio_no_toca_db(app, admin, centro):
    from app.services.backup import previsualizar

    respaldo = crear_backup()
    respaldo['datos']['centros'][0]['name'] = 'Centro Nuevo'

    analisis = previsualizar(respaldo)
    assert analisis['ok'] is True
    assert analisis['tablas']['centros']['filas'] == 1
    assert Centro.query.filter_by(name='Centro de Prueba').count() == 1
    assert Centro.query.filter_by(name='Centro Nuevo').count() == 0
