from datetime import date

from app.extensions import db
from app.models.devolucion_folio import DevolucionFolio


def test_create_devolucion_registra_folio_y_cambia_estado(
    auth_client, app, centro, folio_entregado
):
    """POST /devoluciones/create debe crear la devolución y marcar folio 'devuelto'."""
    resp = auth_client.post(
        '/devoluciones/create',
        data={
            'centroId': centro.id,
            'folio_ids': [folio_entregado.id],
            'fechaDevolucion': '2026-09-28',
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    devolucion = DevolucionFolio.query.filter_by(folio_id=folio_entregado.id).one_or_none()
    assert devolucion is not None, 'la devolución no se registró'
    assert devolucion.centroId == centro.id
    assert devolucion.fechaDevolucion == date(2026, 9, 28)

    db.session.refresh(folio_entregado)
    assert folio_entregado.estado == 'devuelto'


def test_create_devolucion_sin_folio_no_crea_registro(auth_client, app, centro):
    resp = auth_client.post(
        '/devoluciones/create',
        data={
            'centroId': centro.id,
            'fechaDevolucion': '2026-09-28',
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert DevolucionFolio.query.count() == 0
