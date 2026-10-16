"""Transferencia de folio entre centros de salud: motivo obligatorio y seguimiento."""

import pytest

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.centro import Centro
from app.models.entrega_folio import EntregaFolio
from app.services.permisos import puede
from tests.conftest import make_user


@pytest.fixture()
def centro_destino(app):
    centro = Centro(name='Centro Destino', telefono='5555556',
                    direccion='Avenida Sur 456', activo=True)
    db.session.add(centro)
    db.session.commit()
    return centro


def _post_transfer(auth_client, folio, centro_destino, motivo='Solicitud de reasignación'):
    return auth_client.post(
        f'/folios/{folio.id}/transferir',
        data={'centroDestino': centro_destino.id, 'motivo': motivo},
        follow_redirects=True,
    )


# --- transferencia ---


def test_transferir_cambia_centro_y_registra(
    auth_client, app, centro, centro_destino, folio_entregado, operador
):
    resp = _post_transfer(auth_client, folio_entregado, centro_destino)
    assert resp.status_code == 200

    entrega = EntregaFolio.query.filter_by(folio_id=folio_entregado.id).one()
    assert entrega.centroId == centro_destino.id, 'la entrega no apunta al centro destino'

    from app.models.transferencia_folio import TransferenciaFolio
    tr = TransferenciaFolio.query.filter_by(folio_id=folio_entregado.id).one()
    assert tr.centroOrigenId == centro.id
    assert tr.centroDestinoId == centro_destino.id
    assert tr.motivo == 'Solicitud de reasignación'
    assert tr.userId == operador.id
    assert tr.fecha is not None

    db.session.refresh(folio_entregado)
    assert folio_entregado.estado == 'entregado', 'la transferencia no cambia el estado'


def test_transferir_escribe_auditoria(
    auth_client, app, centro, centro_destino, folio_entregado
):
    _post_transfer(auth_client, folio_entregado, centro_destino)

    ins = AuditLog.query.filter_by(
        accion='INSERT', tabla='transferencia_folios').all()
    assert len(ins) == 1, 'falta audit INSERT de transferencia_folios'
    upd = AuditLog.query.filter_by(
        accion='UPDATE', tabla='entrega_folios',
        registro_id=folio_entregado.entrega.id).all()
    assert len(upd) == 1, 'falta audit UPDATE de entrega_folios'
    assert upd[0].datos_nuevos.get('centroId') == centro_destino.id


def test_transferir_exige_motivo(
    auth_client, app, centro, centro_destino, folio_entregado
):
    resp = _post_transfer(auth_client, folio_entregado, centro_destino, motivo='   ')
    assert resp.status_code == 200
    assert 'Indique el motivo' in resp.get_data(as_text=True)

    from app.models.transferencia_folio import TransferenciaFolio
    assert TransferenciaFolio.query.count() == 0, 'no debe registrar sin motivo'
    entrega = EntregaFolio.query.filter_by(folio_id=folio_entregado.id).one()
    assert entrega.centroId == centro.id, 'el centro no debe cambiar sin motivo'


def test_transferir_solo_folios_entregados(auth_client, app, tipo, centro_destino):
    from app.models.folio import Folio
    from app.models.transferencia_folio import TransferenciaFolio
    folio = Folio(rangoId=1, anioCert=2026, tipoCert_id=tipo.id, folio=1000,
                  estado='disponible')
    db.session.add(folio)
    db.session.commit()

    resp = _post_transfer(auth_client, folio, centro_destino)
    assert resp.status_code == 200

    assert TransferenciaFolio.query.count() == 0
    db.session.refresh(folio)
    assert folio.estado == 'disponible'


def test_transferir_destino_no_puede_ser_el_origen(
    auth_client, app, centro, folio_entregado
):
    from app.models.transferencia_folio import TransferenciaFolio
    resp = auth_client.post(
        f'/folios/{folio_entregado.id}/transferir',
        data={'centroDestino': centro.id, 'motivo': 'Motivo válido'},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert TransferenciaFolio.query.count() == 0, 'no debe transferir al mismo centro'
    entrega = EntregaFolio.query.filter_by(folio_id=folio_entregado.id).one()
    assert entrega.centroId == centro.id


def test_transferir_destino_inactivo_rechazado(
    auth_client, app, folio_entregado
):
    from app.models.transferencia_folio import TransferenciaFolio
    inactivo = Centro(name='Centro Cerrado', activo=False)
    db.session.add(inactivo)
    db.session.commit()

    resp = auth_client.post(
        f'/folios/{folio_entregado.id}/transferir',
        data={'centroDestino': inactivo.id, 'motivo': 'Motivo válido'},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert TransferenciaFolio.query.count() == 0, 'centro inactivo no debe aceptarse'
    entrega = EntregaFolio.query.filter_by(folio_id=folio_entregado.id).one()
    assert entrega.centroId != inactivo.id


def test_lectura_no_puede_transferir(app, centro_destino, folio_entregado):
    from app.models.transferencia_folio import TransferenciaFolio
    make_user('lectura', 'lectura')
    client = app.test_client()
    client.post('/auth/login', data={'username': 'lectura', 'password': 'pass12345'})

    resp = client.post(
        f'/folios/{folio_entregado.id}/transferir',
        data={'centroDestino': centro_destino.id, 'motivo': 'Motivo válido'},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert 'No tiene permisos' in resp.get_data(as_text=True)
    assert TransferenciaFolio.query.count() == 0


def test_permiso_transferir_es_edit(app):
    assert puede('folios.transferir', make_user('operador', 'operador'))
    assert not puede('folios.transferir', make_user('lectura', 'lectura'))


# --- seguimiento ---


def test_seguimiento_lista_transferencia(
    auth_client, app, centro, centro_destino, folio_entregado
):
    _post_transfer(auth_client, folio_entregado, centro_destino)

    resp = auth_client.get('/folios/transferencias')
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'Solicitud de reasignación' in body
    assert centro.name in body
    assert centro_destino.name in body


def test_seguimiento_filtra_por_centro_destino(
    auth_client, app, centro, centro_destino, folio_entregado
):
    _post_transfer(auth_client, folio_entregado, centro_destino)

    resp = auth_client.get(f'/folios/transferencias?destino={centro_destino.id}')
    assert resp.status_code == 200
    assert 'Solicitud de reasignación' in resp.get_data(as_text=True)

    resp = auth_client.get(f'/folios/transferencias?destino={centro.id}')
    assert 'Solicitud de reasignación' not in resp.get_data(as_text=True)


def test_seguimiento_requiere_login(client):
    assert client.get('/folios/transferencias').status_code == 302


def test_seguimiento_visible_para_lectura(app):
    make_user('lectura', 'lectura')
    client = app.test_client()
    client.post('/auth/login', data={'username': 'lectura', 'password': 'pass12345'})
    assert client.get('/folios/transferencias').status_code == 200


def test_detalle_muestra_transferencias(
    auth_client, app, centro, centro_destino, folio_entregado
):
    _post_transfer(auth_client, folio_entregado, centro_destino)

    resp = auth_client.get(f'/folios/{folio_entregado.id}')
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'Transferencias' in body
    assert 'Solicitud de reasignación' in body
    assert centro_destino.name in body


def test_indice_muestra_boton_seguimiento(auth_client):
    resp = auth_client.get('/folios/')
    assert resp.status_code == 200
    assert '/folios/transferencias' in resp.get_data(as_text=True)
