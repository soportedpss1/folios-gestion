"""Detalle en /auditoria/: etiqueta legible del registro + resumen de campos.

audit_logs ya guardaba datos_anteriores/datos_nuevos y la tabla nunca los
mostraba. Ahora cada fila dice qué registro afectó (etiqueta) y qué cambió
(diff de campos), resuelto desde el JSON guardado con fallback a DB en lote.
"""

from datetime import date, datetime

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.centro import Centro
from tests.conftest import make_folio


def _log(admin, accion, tabla, registro_id, antes=None, nuevos=None):
    log = AuditLog(
        user_id=admin.id, accion=accion, tabla=tabla, registro_id=registro_id,
        datos_anteriores=antes, datos_nuevos=nuevos,
        fecha=datetime(2026, 10, 1, 12, 0), ip_address='127.0.0.1',
    )
    db.session.add(log)
    db.session.commit()
    return log


def _html(admin_client):
    return admin_client.get('/auditoria/').get_data(as_text=True)


# ------------------------------------------------------------- etiqueta


def test_etiqueta_desde_json_insert_centro(admin_client, app, admin):
    """INSERT de centro: el JSON trae name → la etiqueta sale sin tocar DB."""
    _log(admin, 'INSERT', 'centros', 999, None, {'name': 'Centro Norte'})

    html = _html(admin_client)

    assert 'Centro Norte' in html, 'falta la etiqueta legible del registro'


def test_etiqueta_desde_json_elimina_centro(admin_client, app, admin):
    """DELETE: la fila ya no existe en DB, la etiqueta viene del JSON viejo."""
    _log(admin, 'DELETE', 'centros', 42, {'name': 'Centro Viejo'}, None)

    html = _html(admin_client)

    assert 'Centro Viejo' in html, 'sin la fila en DB debe usar el JSON'


def test_etiqueta_folio_desde_db_cuando_json_no_lo_trae(admin_client, app, tipo, admin):
    """UPDATE de folio que solo guarda flags (escaneo): el JSON no trae el
    número de folio → fallback a DB en lote debe resolver 'Folio <n>'."""
    folio = make_folio(tipo, anio=2026, numero=4321)
    db.session.commit()
    _log(admin, 'UPDATE', 'folios', folio.id,
         {'escaneado': False}, {'escaneado': True})

    html = _html(admin_client)

    assert 'Folio 4321' in html, 'la etiqueta del folio debe venir de la DB'


def test_etiqueta_backup_sin_registro(admin_client, app, admin):
    """registro_id=0 (backup/sync) no es un registro real: etiqueta propia."""
    _log(admin, 'BACKUP', 'backup', 0, None, {'tablas': 12, 'filas': 500})

    html = _html(admin_client)

    assert 'Respaldo' in html, 'backup debe etiquetarse, no mostrar #0 crudo'


def test_etiqueta_fallback_id_cuando_no_hay_nada(admin_client, app, admin):
    """Sin datos ni fila en DB: se muestra el id crudo, sin 500."""
    _log(admin, 'UPDATE', 'google_sheets', 77, {'x': 1}, {'x': 2})

    html = _html(admin_client)

    assert '#77' in html or '>77<' in html, 'fallback al id crudo'


# ------------------------------------------------------------- detalle


def test_detalle_update_muestra_solo_campos_cambiados(admin_client, app, admin):
    """UPDATE: diff de los campos que cambiados, con antes → después."""
    _log(admin, 'UPDATE', 'centros', 5,
         {'name': 'Viejo', 'telefono': '111', 'activo': True},
         {'name': 'Viejo', 'telefono': '222', 'activo': True})

    html = _html(admin_client)

    assert 'telefono' in html, 'falta el campo cambiado'
    assert '111' in html and '222' in html, 'falta el diff antes → después'
    # name NO cambió: no debe aparecer en el diff del detalle
    fila = html.split('<tbody>')[1].split('</tbody>')[0]
    assert 'name' not in fila, 'el detalle no debe listar campos sin cambios'


def test_detalle_insert_muestra_valores_nuevos(admin_client, app, admin):
    _log(admin, 'INSERT', 'tipo_certificados', 3, None,
         {'name': 'Nacimientos', 'activo': True})

    html = _html(admin_client)

    assert 'Nacimientos' in html
    assert 'name' in html


def test_detalle_delete_muestra_valores_viejos(admin_client, app, admin):
    _log(admin, 'DELETE', 'centros', 8,
         {'name': 'Centro Borrado', 'activo': False}, None)

    html = _html(admin_client)

    assert 'Centro Borrado' in html


def test_detalle_formato_bool_fecha_y_truncado(admin_client, app, admin):
    """bool → Sí/No, fecha ISO → dd/mm/aaaa, string largo truncado."""
    _log(admin, 'UPDATE', 'centros', 5,
         {'activo': False, 'fecha': '2026-01-02', 'direccion': 'x'},
         {'activo': True, 'fecha': '2026-03-04',
          'direccion': 'A' * 200})

    html = _html(admin_client)

    assert 'Sí' in html, 'bool debe mostrarse como Sí/No'
    assert '04/03/2026' in html, 'fecha ISO debe ir en dd/mm/aaaa'
    assert 'A' * 80 in html, 'string largo debe truncarse a 80'
    assert 'A' * 200 not in html, 'el string completo no debe caber'


def test_detalle_sin_datos_no_rompe(admin_client, app, admin):
    """SYNC sin JSON y sin fila en DB: la página sigue respondiendo 200."""
    _log(admin, 'SYNC', 'google_sheets', 0, None, None)

    resp = admin_client.get('/auditoria/')

    assert resp.status_code == 200, 'sin datos no debe romper la página'


def test_detalle_update_sin_cambios_muestra_guion(admin_client, app, admin):
    """Mismos valores antes/después → no hay diff, muestra '—'."""
    _log(admin, 'UPDATE', 'centros', 5,
         {'name': 'Igual'}, {'name': 'Igual'})

    resp = admin_client.get('/auditoria/')

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert '—' in html


# ------------------------------------------------------------- estructura


def test_columna_registro_y_detalle_existen(admin_client, app, admin):
    """La tabla gana 'Registro' (etiqueta + id) y 'Detalle'; colspan vacío 7."""
    html = _html(admin_client)

    assert '<th>Registro</th>' in html, 'falta la columna Registro'
    assert '<th>Detalle</th>' in html, 'falta la columna Detalle'
    assert 'ID Registro' not in html, 'la columna de id crudo debe desaparecer'
    assert 'colspan="7"' in html, 'el colspan vacío debe cubrir 7 columnas'


def test_etiqueta_y_id_juntos(admin_client, app, admin, tipo):
    folio = make_folio(tipo, anio=2026, numero=1500)
    db.session.commit()
    _log(admin, 'UPDATE', 'folios', folio.id, {'nulo': False}, {'nulo': True})

    html = _html(admin_client)

    assert 'Folio 1500' in html
    assert f'#{folio.id}' in html, 'el id crudo queda como referencia'
