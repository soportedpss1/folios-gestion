"""Devolución de folios en blanco: se libera la entrega y el folio vuelve al pool.

Sin registro de devolución (la auditoría guarda el rastro); el folio queda
'disponible' y puede reasignarse a otro centro — algo imposible antes porque
uq_entrega_folios_folio_id bloqueaba la segunda entrega.
"""

from datetime import date

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.devolucion_folio import DevolucionFolio
from app.models.entrega_folio import EntregaFolio
from app.models.centro import Centro
from tests.conftest import make_folio


def _post_en_blanco(client, folio, centro, fecha='2026-09-28'):
    return client.post('/devoluciones/create', data={
        'centroId': centro.id,
        'folio_ids': [folio.id],
        'fechaDevolucion': fecha,
        'en_blanco': 'y',
    }, follow_redirects=True)


# ------------------------------------------------------------------- form UI


def test_create_devolucion_muestra_checkbox_en_blanco(auth_client):
    html = auth_client.get('/devoluciones/create').get_data(as_text=True)

    assert 'en_blanco' in html, 'falta el checkbox de folios en blanco'
    assert 'en blanco' in html.lower()


# --------------------------------------------------------------- liberación


def test_devolucion_en_blanco_libera_folio_sin_registro(
    auth_client, app, folio_entregado, centro
):
    resp = _post_en_blanco(auth_client, folio_entregado, centro)

    assert resp.status_code == 200
    db.session.refresh(folio_entregado)
    assert folio_entregado.estado == 'disponible', (
        'el folio en blanco debe volver al pool')
    assert EntregaFolio.query.filter_by(folio_id=folio_entregado.id).count() == 0, (
        'la entrega del ciclo anterior debe borrarse (bloquea la re-entrega)')
    assert DevolucionFolio.query.filter_by(folio_id=folio_entregado.id).count() == 0, (
        'una devolución en blanco no crea registro de devolución')


def test_devolucion_en_blanco_auditoria_borra_entrega_y_cambia_estado(
    auth_client, app, folio_entregado, centro
):
    _post_en_blanco(auth_client, folio_entregado, centro)

    borrados = AuditLog.query.filter_by(
        accion='DELETE', tabla='entrega_folios').all()
    assert len(borrados) == 1, 'falta audit DELETE de la entrega'
    assert folio_entregado.entrega is None

    estados = AuditLog.query.filter_by(accion='UPDATE', tabla='folios').all()
    assert len(estados) == 1, 'falta audit UPDATE del estado del folio'
    assert estados[0].registro_id == folio_entregado.id


def test_devolucion_en_blanco_omite_folio_no_entregado(
    auth_client, app, tipo, centro
):
    folio = make_folio(tipo, anio=2026, numero=7777, estado='disponible')

    resp = _post_en_blanco(auth_client, folio, centro)

    assert resp.status_code == 200
    db.session.refresh(folio)
    assert folio.estado == 'disponible', 'el folio no debía tocarse'
    assert AuditLog.query.filter_by(tabla='entrega_folios').count() == 0


def test_devolucion_en_blanco_muestra_flash_de_liberacion(
    auth_client, app, folio_entregado, centro
):
    resp = _post_en_blanco(auth_client, folio_entregado, centro)
    html = resp.get_data(as_text=True)

    assert 'liberado' in html.lower(), 'sin mensaje de folio liberado'


# ------------------------------------------------------ ciclo completo


def test_folio_liberado_puede_reasignarse_a_otro_centro(
    auth_client, app, folio_entregado, centro, operador
):
    """Regresión clave: sin liberar, la segunda entrega revienta IntegrityError."""
    _post_en_blanco(auth_client, folio_entregado, centro)

    otro = Centro(name='Centro Dos', telefono='5555556',
                  direccion='Otra Calle 456', activo=True)
    db.session.add(otro)
    db.session.commit()

    resp = auth_client.post('/entregas/create', data={
        'centroId': otro.id,
        'folio_ids': [folio_entregado.id],
        'fechaEntrega': '2026-09-30',
    }, follow_redirects=True)

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Registro duplicado' not in html, (
        'la re-entrega falló por la entrega vieja sin borrar')
    db.session.refresh(folio_entregado)
    assert folio_entregado.estado == 'entregado'
    entrega = EntregaFolio.query.filter_by(folio_id=folio_entregado.id).one()
    assert entrega.centroId == otro.id


def test_folio_liberado_reasignado_se_puede_devolver_normal(
    auth_client, app, folio_entregado, centro, operador
):
    """Tras liberar + re-entregar, la devolución normal crea su registro
    (uq_devolucion_folios_folio_id no debe chocar)."""
    _post_en_blanco(auth_client, folio_entregado, centro)

    otro = Centro(name='Centro Dos', telefono='5555556',
                  direccion='Otra Calle 456', activo=True)
    db.session.add(otro)
    db.session.commit()
    auth_client.post('/entregas/create', data={
        'centroId': otro.id,
        'folio_ids': [folio_entregado.id],
        'fechaEntrega': '2026-09-30',
    }, follow_redirects=True)

    resp = auth_client.post('/devoluciones/create', data={
        'centroId': otro.id,
        'folio_ids': [folio_entregado.id],
        'fechaDevolucion': '2026-10-01',
    }, follow_redirects=True)

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Registro duplicado' not in html
    db.session.refresh(folio_entregado)
    assert folio_entregado.estado == 'devuelto'
    dev = DevolucionFolio.query.filter_by(folio_id=folio_entregado.id).one()
    assert dev.centroId == otro.id


# ------------------------------------------------------ sin checkbox (normal)


def test_devolucion_sin_en_blanco_registra_normal(
    auth_client, app, folio_entregado, centro
):
    resp = auth_client.post('/devoluciones/create', data={
        'centroId': centro.id,
        'folio_ids': [folio_entregado.id],
        'fechaDevolucion': '2026-09-28',
    }, follow_redirects=True)

    assert resp.status_code == 200
    db.session.refresh(folio_entregado)
    assert folio_entregado.estado == 'devuelto'
    assert EntregaFolio.query.filter_by(folio_id=folio_entregado.id).count() == 1, (
        'sin en_blanco la entrega no se borra')
    assert DevolucionFolio.query.filter_by(folio_id=folio_entregado.id).count() == 1
    dev = DevolucionFolio.query.filter_by(folio_id=folio_entregado.id).one()
    assert dev.fechaDevolucion == date(2026, 9, 28)
