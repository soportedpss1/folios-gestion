"""Entregas/devoluciones: edición segura y lotes sin ids repetidos."""

from datetime import date

from app.extensions import db
from app.models.centro import Centro
from app.models.entrega_folio import EntregaFolio
from app.services.movimientos import crear_movimiento
from tests.conftest import make_folio, make_user


def test_crear_movimiento_ids_duplicados_sin_omitidos_falsos(app, tipo, centro):
    """folio_ids=[7,7]: el segundo encuentro ve el estado ya mutado y contaba
    un '1 folio omitido' inexistente en el flash."""
    folio = make_folio(tipo, anio=2026, numero=9001)
    user = make_user('ope_dup', 'operador')

    creados, omitidos = crear_movimiento(
        modelo=EntregaFolio, fecha_field='fechaEntrega',
        folio_ids=[folio.id, folio.id], fecha=date(2026, 9, 28),
        centro_id=centro.id, user=user,
        estado_origen='disponible', estado_destino='entregado',
        excluir_nulos=True, tabla_audit='entrega_folios',
        log_audit=lambda *a, **k: None,
    )
    assert creados == 1
    assert omitidos == 0, 'el id repetido no debe contar como omitido'


def test_edit_entrega_folio_devuelto_no_cambia_centro(
        auth_client, app, centro, folio_entregado):
    """El folio devuelto quedó en el centro de la devolución: re-apuntar la
    entrega a otro centro divergía Reportes y Devoluciones para siempre."""
    entrega = folio_entregado.entrega
    auth_client.post('/devoluciones/create', data={
        'centroId': centro.id, 'folio_ids': [folio_entregado.id],
        'fechaDevolucion': '2026-09-29',
    }, follow_redirects=True)

    otro = Centro(name='Otro Centro Edit', telefono='2', direccion='x',
                  activo=True)
    db.session.add(otro)
    db.session.commit()

    auth_client.post(f'/entregas/{entrega.id}/edit', data={
        'folio_id': folio_entregado.id, 'fechaEntrega': '2026-09-28',
        'centroId': otro.id,
    }, follow_redirects=True)

    db.session.refresh(entrega)
    assert entrega.centroId == centro.id, \
        'no debe cambiar el centro de una entrega ya devuelta'


def test_edit_entrega_fecha_posterior_a_devolucion_rechazada(
        auth_client, app, centro, folio_entregado):
    """fechaEntrega posterior a fechaDevolucion dejaba la línea de tiempo
    invertida en los reportes."""
    entrega = folio_entregado.entrega
    auth_client.post('/devoluciones/create', data={
        'centroId': centro.id, 'folio_ids': [folio_entregado.id],
        'fechaDevolucion': '2026-09-29',
    }, follow_redirects=True)

    resp = auth_client.post(f'/entregas/{entrega.id}/edit', data={
        'folio_id': folio_entregado.id, 'fechaEntrega': '2026-10-15',
        'centroId': centro.id,
    }, follow_redirects=True)

    db.session.refresh(entrega)
    assert entrega.fechaEntrega < date(2026, 10, 15), \
        'no debe guardar una entrega posterior a la devolución'
