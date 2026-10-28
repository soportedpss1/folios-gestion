"""Paneles de corrección: modo JSON en las rutas dueñas."""

from datetime import date

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.centro import Centro
from app.models.devolucion_folio import DevolucionFolio
from app.models.entrega_folio import EntregaFolio
from app.models.folio import Folio
from app.models.recepcion_folio import RecepcionFolio
from app.services.inspecciones import (rangos_corruptos,
                                       formatear_rangos_corruptos)
from tests.conftest import make_folio
from tests.test_inspecciones import make_rango, hallazgos

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


def test_recepcion_edit_json_get_campos(admin_client, app, tipo, operador):
    r = make_rango(tipo, operador, ini=1, fin=100, rangoId=60)
    data = admin_client.get(f'/recepcion/{r.id}/edit',
                            headers=JSON).get_json()
    assert data['ok'] is True
    assert 'name="folioInicial"' in data['campos_html']
    assert 'csrf_token' not in data['campos_html']


def test_recepcion_edit_json_corrige_solape(admin_client, app, tipo, operador):
    a = make_rango(tipo, operador, ini=1, fin=100, rangoId=61)
    b = make_rango(tipo, operador, ini=50, fin=150, rangoId=62)  # solapa
    # Precondición: el solape es hallazgo del chequeo rangos-corruptos.
    assert hallazgos(rangos_corruptos(), formatear_rangos_corruptos)
    resp = admin_client.post(
        f'/recepcion/{b.id}/edit', headers=JSON,
        data={'fecha': '01/03/2026', 'anioCert': 2026, 'tipoCert': tipo.id,
              'folioInicial': 101, 'folioFinal': 150, 'usuario': operador.id})
    assert resp.get_json() == {'ok': True}
    assert hallazgos(rangos_corruptos(), formatear_rangos_corruptos) == []
    assert AuditLog.query.filter_by(accion='UPDATE',
                                    tabla='recepcion_folios',
                                    registro_id=b.id).count() == 1


def test_recepcion_edit_json_post_crea_solape(admin_client, app, tipo,
                                              operador):
    a = make_rango(tipo, operador, ini=1, fin=100, rangoId=63)
    b = make_rango(tipo, operador, ini=101, fin=200, rangoId=64)
    resp = admin_client.post(
        f'/recepcion/{b.id}/edit', headers=JSON,
        data={'fecha': '01/03/2026', 'anioCert': 2026, 'tipoCert': tipo.id,
              'folioInicial': 50, 'folioFinal': 200, 'usuario': operador.id})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['ok'] is False and data.get('errores')
    assert db.session.get(RecepcionFolio, b.id).folioInicial == 101


def _folio_incoherente(tipo):
    folio = make_folio(tipo, anio=2026, numero=8200, rangoId=70,
                       estado='entregado')
    db.session.commit()
    return folio


def test_cambiar_estado_json_get_campos(admin_client, app, tipo):
    folio = _folio_incoherente(tipo)
    data = admin_client.get(f'/folios/{folio.id}/estado',
                            headers=JSON).get_json()
    assert data['ok'] is True
    assert 'name="estado"' in data['campos_html']
    assert 'csrf_token' not in data['campos_html']
    assert 'perdido' not in data['campos_html'], 'perdido es flujo propio'


def test_cambiar_estado_json_post_ok(admin_client, app, tipo):
    folio = _folio_incoherente(tipo)
    resp = admin_client.post(f'/folios/{folio.id}/estado', headers=JSON,
                             data={'estado': 'disponible'})
    assert resp.get_json() == {'ok': True}
    assert db.session.get(Folio, folio.id).estado == 'disponible'
    assert AuditLog.query.filter_by(accion='UPDATE', tabla='folios',
                                    registro_id=folio.id).count() == 1


def test_cambiar_estado_json_post_invalido(admin_client, app, tipo):
    folio = _folio_incoherente(tipo)
    resp = admin_client.post(f'/folios/{folio.id}/estado', headers=JSON,
                             data={'estado': 'perdido'})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['ok'] is False and 'inválido' in data['error']
    assert db.session.get(Folio, folio.id).estado == 'entregado'
    assert AuditLog.query.filter_by(tabla='folios',
                                    registro_id=folio.id).count() == 0


def test_cambiar_estado_get_normal_no_es_json(admin_client, app, tipo):
    # GET sin header JSON: no filtra el form, redirige al detalle.
    folio = _folio_incoherente(tipo)
    resp = admin_client.get(f'/folios/{folio.id}/estado')
    assert resp.status_code == 302
    assert f'/folios/{folio.id}' in resp.headers['Location']
