"""Fase 2 — constraints a nivel de BD y recuperación ante duplicados concurrentes."""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.devolucion_folio import DevolucionFolio
from app.models.entrega_folio import EntregaFolio
from app.models.folio import Folio
from tests.conftest import make_folio


def test_folio_duplicado_en_mismo_rango_rechazado(app, tipo):
    make_folio(tipo, rangoId=1, numero=10)

    with pytest.raises(IntegrityError):
        make_folio(tipo, rangoId=1, numero=10)
    db.session.rollback()


def test_folio_duplicado_en_otro_rango_mismo_tipo_anio_rechazado(app, tipo):
    make_folio(tipo, rangoId=1, numero=10)

    with pytest.raises(IntegrityError):
        make_folio(tipo, rangoId=2, numero=10)
    db.session.rollback()


def test_segunda_entrega_mismo_folio_rechazada(app, folio_entregado, centro, operador):
    with pytest.raises(IntegrityError):
        db.session.add(EntregaFolio(
            folio_id=folio_entregado.id,
            fechaEntrega=date(2026, 9, 20),
            centroId=centro.id,
            userId=operador.id,
        ))
        db.session.flush()
    db.session.rollback()


def test_segunda_devolucion_mismo_folio_rechazada(app, folio_entregado, centro, operador):
    db.session.add(DevolucionFolio(
        folio_id=folio_entregado.id,
        fechaDevolucion=date(2026, 9, 10),
        centroId=centro.id,
        userId=operador.id,
    ))
    db.session.commit()

    with pytest.raises(IntegrityError):
        db.session.add(DevolucionFolio(
            folio_id=folio_entregado.id,
            fechaDevolucion=date(2026, 9, 20),
            centroId=centro.id,
            userId=operador.id,
        ))
        db.session.flush()
    db.session.rollback()


def test_entrega_duplicada_concurrente_recupera_sin_500(auth_client, app, tipo, centro, operador):
    """Doble submit de la misma entrega: flash de error, no 500."""
    folio = make_folio(tipo)
    db.session.add(EntregaFolio(
        folio_id=folio.id,
        fechaEntrega=date(2026, 9, 1),
        centroId=centro.id,
        userId=operador.id,
    ))
    db.session.commit()

    resp = auth_client.post(
        '/entregas/create',
        data={
            'folio_ids': [folio.id],
            'fechaEntrega': '2026-09-28',
            'centroId': centro.id,
        },
        follow_redirects=True,
    )

    assert resp.status_code == 200, f'esperaba 200 con flash, llegó {resp.status_code}'
    assert EntregaFolio.query.count() == 1, 'creó una segunda entrega duplicada'
    assert 'duplicad' in resp.get_data(as_text=True).lower(), 'sin mensaje de duplicado'


def test_devolucion_duplicada_concurrente_recupera_sin_500(auth_client, app, folio_entregado, centro, operador):
    db.session.add(DevolucionFolio(
        folio_id=folio_entregado.id,
        fechaDevolucion=date(2026, 9, 1),
        centroId=centro.id,
        userId=operador.id,
    ))
    db.session.commit()

    resp = auth_client.post(
        '/devoluciones/create',
        data={
            'centroId': centro.id,
            'folio_ids': [folio_entregado.id],
            'fechaDevolucion': '2026-09-28',
        },
        follow_redirects=True,
    )

    assert resp.status_code == 200, f'esperaba 200 con flash, llegó {resp.status_code}'
    assert DevolucionFolio.query.count() == 1, 'creó una segunda devolución duplicada'
    assert 'duplicad' in resp.get_data(as_text=True).lower(), 'sin mensaje de duplicado'
