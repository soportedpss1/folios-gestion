"""Corrección manual de estado del folio desde su detalle."""

from datetime import date

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.entrega_folio import EntregaFolio
from app.models.folio import Folio
from tests.conftest import make_folio, make_user


def _folio_entregado_sin_registro(tipo):
    folio = make_folio(tipo, numero=7000, rangoId=30, estado='entregado')
    db.session.commit()
    return folio


def test_cambiar_estado_valido_y_audita(auth_client, app, tipo):
    folio = _folio_entregado_sin_registro(tipo)
    resp = auth_client.post(f'/folios/{folio.id}/estado',
                            data={'estado': 'disponible'},
                            follow_redirects=True)
    assert 'Estado actualizado exitosamente.' in resp.get_data(as_text=True)
    assert db.session.get(Folio, folio.id).estado == 'disponible'
    log = AuditLog.query.filter_by(accion='UPDATE', tabla='folios',
                                   registro_id=folio.id).one()
    assert log.datos_anteriores == {'estado': 'entregado'}
    assert log.datos_nuevos == {'estado': 'disponible'}


def test_cambiar_estado_invalido_rechazado(auth_client, app, tipo):
    folio = _folio_entregado_sin_registro(tipo)
    for malo in ('perdido', 'digitado', 'escaneado', 'nulo', '', 'basura'):
        auth_client.post(f'/folios/{folio.id}/estado', data={'estado': malo})
    assert db.session.get(Folio, folio.id).estado == 'entregado'
    assert AuditLog.query.filter_by(accion='UPDATE', tabla='folios',
                                    registro_id=folio.id).count() == 0


def test_cambiar_estado_igual_no_audita(auth_client, app, tipo):
    folio = _folio_entregado_sin_registro(tipo)
    resp = auth_client.post(f'/folios/{folio.id}/estado',
                            data={'estado': 'entregado'},
                            follow_redirects=True)
    assert 'Ese ya es el estado del folio.' in resp.get_data(as_text=True)
    assert AuditLog.query.filter_by(accion='UPDATE', tabla='folios',
                                    registro_id=folio.id).count() == 0


def test_cambiar_estado_sin_permiso_no_cambia(app, client, tipo):
    folio = _folio_entregado_sin_registro(tipo)
    lectura = make_user('lectura_estado', 'lectura')
    client.post('/auth/login', data={'username': lectura.username,
                                     'password': 'pass12345'})
    resp = client.post(f'/folios/{folio.id}/estado',
                       data={'estado': 'disponible'})
    assert resp.status_code == 302
    assert '/folios' in resp.headers['Location']
    assert db.session.get(Folio, folio.id).estado == 'entregado'


def test_details_muestra_form_de_estado(auth_client, app, tipo):
    folio = _folio_entregado_sin_registro(tipo)
    html = auth_client.get(f'/folios/{folio.id}').get_data(as_text=True)
    assert 'name="estado"' in html
    assert '<option value="disponible"' in html
    assert '<option value="devuelto"' in html
    assert '<option value="perdido"' not in html, 'perdido es flujo propio'


def test_details_oculta_form_a_lectura(app, client, tipo):
    folio = _folio_entregado_sin_registro(tipo)
    lectura = make_user('lectura_estado2', 'lectura')
    client.post('/auth/login', data={'username': lectura.username,
                                     'password': 'pass12345'})
    html = client.get(f'/folios/{folio.id}').get_data(as_text=True)
    assert 'name="estado"' not in html


def test_details_oculta_form_coherente(auth_client, app, tipo, centro,
                                       operador):
    """Sin incoherencia no hay form: el estado no necesita corrección."""
    folio_ok = make_folio(tipo, numero=7100, rangoId=31, estado='disponible')
    db.session.commit()
    folio_ent = make_folio(tipo, numero=7101, rangoId=32, estado='entregado')
    db.session.flush()
    db.session.add(EntregaFolio(folio_id=folio_ent.id,
                                fechaEntrega=date(2026, 3, 1),
                                centroId=centro.id, userId=operador.id))
    db.session.commit()
    for f in (folio_ok, folio_ent):
        html = auth_client.get(f'/folios/{f.id}').get_data(as_text=True)
        assert 'name="estado"' not in html, \
            f'form visible con estado coherente ({f.estado})'


def test_details_muestra_form_por_incoherencia(auth_client, app, tipo,
                                               centro, operador):
    """Las otras 2 ramas del chequeo siguen mostrando el form: la condición
    de ocultación no puede exagerar (regression guard del cambio)."""
    folio_dev = make_folio(tipo, numero=7200, rangoId=33, estado='devuelto')
    db.session.commit()
    folio_disp = make_folio(tipo, numero=7201, rangoId=34,
                            estado='disponible')
    db.session.flush()
    db.session.add(EntregaFolio(folio_id=folio_disp.id,
                                fechaEntrega=date(2026, 3, 1),
                                centroId=centro.id, userId=operador.id))
    db.session.commit()
    for f in (folio_dev, folio_disp):
        html = auth_client.get(f'/folios/{f.id}').get_data(as_text=True)
        assert 'name="estado"' in html, \
            f'sin form pese a incoherencia ({f.estado})'
