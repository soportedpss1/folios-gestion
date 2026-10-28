"""Paneles de corrección: modo JSON en las rutas dueñas."""

from datetime import date

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.centro import Centro
from app.models.devolucion_folio import DevolucionFolio
from app.models.entrega_folio import EntregaFolio
from tests.conftest import make_folio

JSON = {'Accept': 'application/json'}


def _entrega(tipo, centro, operador, numero=8000, rangoId=40):
    folio = make_folio(tipo, anio=2026, numero=numero, rangoId=rangoId,
                       estado='entregado')
    db.session.flush()
    entrega = EntregaFolio(folio_id=folio.id, fechaEntrega=date(2026, 3, 1),
                           centroId=centro.id, userId=operador.id)
    db.session.add(entrega)
    db.session.commit()
    return entrega


def test_entregas_edit_json_get_campos(admin_client, app, tipo, centro,
                                       operador):
    entrega = _entrega(tipo, centro, operador)
    resp = admin_client.get(f'/entregas/{entrega.id}/edit', headers=JSON)
    data = resp.get_json()
    assert data['ok'] is True
    assert 'name="fechaEntrega"' in data['campos_html']
    assert 'csrf_token' not in data['campos_html'], 'el modal pone su csrf'


def test_entregas_edit_json_post_ok(admin_client, app, tipo, centro,
                                    operador):
    entrega = _entrega(tipo, centro, operador, numero=8001, rangoId=41)
    resp = admin_client.post(
        f'/entregas/{entrega.id}/edit', headers=JSON,
        data={'folio_id': entrega.folio_id, 'fechaEntrega': '05/03/2026',
              'centroId': centro.id})
    assert resp.get_json() == {'ok': True}
    assert db.session.get(EntregaFolio, entrega.id).fechaEntrega == date(2026, 3, 5)
    assert AuditLog.query.filter_by(accion='UPDATE', tabla='entrega_folios',
                                    registro_id=entrega.id).count() == 1


def test_entregas_edit_json_post_fecha_futura(admin_client, app, tipo, centro,
                                              operador):
    entrega = _entrega(tipo, centro, operador, numero=8002, rangoId=42)
    resp = admin_client.post(
        f'/entregas/{entrega.id}/edit', headers=JSON,
        data={'folio_id': entrega.folio_id, 'fechaEntrega': '01/01/2030',
              'centroId': centro.id})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['ok'] is False and 'fechaEntrega' in data['errores']
    assert 'posterior a hoy' in data['errores']['fechaEntrega']
    assert db.session.get(EntregaFolio, entrega.id).fechaEntrega == date(2026, 3, 1)
    assert AuditLog.query.filter_by(tabla='entrega_folios',
                                    registro_id=entrega.id).count() == 0


def test_entregas_edit_json_error_negocio(admin_client, app, tipo, centro,
                                          operador):
    entrega = _entrega(tipo, centro, operador, numero=8003, rangoId=43)
    otro = Centro(name='Otro Centro', telefono='555', direccion='Calle 2',
                  activo=True)
    db.session.add(otro)
    db.session.add(DevolucionFolio(
        folio_id=entrega.folio_id, fechaDevolucion=date(2026, 3, 10),
        centroId=centro.id, userId=operador.id))
    db.session.commit()
    # El folio ya fue devuelto: mover su entrega a otro centro lo rechaza.
    resp = admin_client.post(
        f'/entregas/{entrega.id}/edit', headers=JSON,
        data={'folio_id': entrega.folio_id, 'fechaEntrega': '01/03/2026',
              'centroId': otro.id})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['ok'] is False and 'ya fue devuelto' in data['error']
    assert 'errores' not in data
    assert db.session.get(EntregaFolio, entrega.id).centroId == centro.id


def test_entregas_edit_post_normal_no_es_json(admin_client, app, tipo, centro,
                                              operador):
    # Sin Accept: application/json → flujo viejo intacto (redirect al índice).
    entrega = _entrega(tipo, centro, operador, numero=8004, rangoId=44)
    resp = admin_client.post(
        f'/entregas/{entrega.id}/edit',
        data={'folio_id': entrega.folio_id, 'fechaEntrega': '05/03/2026',
              'centroId': centro.id})
    assert resp.status_code == 302
    assert '/entregas' in resp.headers['Location']
    assert resp.mimetype != 'application/json'


def _devolucion(tipo, centro, operador, numero=8100, rangoId=50):
    folio = make_folio(tipo, anio=2026, numero=numero, rangoId=rangoId,
                       estado='devuelto')
    db.session.flush()
    dev = DevolucionFolio(folio_id=folio.id,
                          fechaDevolucion=date(2026, 3, 10),
                          centroId=centro.id, userId=operador.id)
    db.session.add(dev)
    db.session.commit()
    return dev


def test_devoluciones_edit_json_get_campos(admin_client, app, tipo, centro,
                                           operador):
    dev = _devolucion(tipo, centro, operador)
    data = admin_client.get(f'/devoluciones/{dev.id}/edit',
                            headers=JSON).get_json()
    assert data['ok'] is True
    assert 'name="fechaDevolucion"' in data['campos_html']
    assert 'csrf_token' not in data['campos_html']


def test_devoluciones_edit_json_post_ok(admin_client, app, tipo, centro,
                                        operador):
    dev = _devolucion(tipo, centro, operador, numero=8101, rangoId=51)
    resp = admin_client.post(
        f'/devoluciones/{dev.id}/edit', headers=JSON,
        data={'folio_id': dev.folio_id, 'fechaDevolucion': '05/03/2026',
              'centroId': centro.id})
    assert resp.get_json() == {'ok': True}
    assert db.session.get(DevolucionFolio, dev.id).fechaDevolucion == date(2026, 3, 5)
    assert AuditLog.query.filter_by(accion='UPDATE', tabla='devolucion_folios',
                                    registro_id=dev.id).count() == 1


def test_devoluciones_edit_json_post_fecha_futura(admin_client, app, tipo,
                                                  centro, operador):
    dev = _devolucion(tipo, centro, operador, numero=8102, rangoId=52)
    resp = admin_client.post(
        f'/devoluciones/{dev.id}/edit', headers=JSON,
        data={'folio_id': dev.folio_id, 'fechaDevolucion': '01/01/2030',
              'centroId': centro.id})
    assert resp.status_code == 400
    assert 'posterior a hoy' in resp.get_json()['errores']['fechaDevolucion']
    assert db.session.get(DevolucionFolio, dev.id).fechaDevolucion == date(2026, 3, 10)
