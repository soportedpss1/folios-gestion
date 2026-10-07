"""Fase 2 — recepción: rangos no solapados + rangoId sin carrera."""

from app.models.recepcion_folio import RecepcionFolio
from app.models.folio import Folio


def _post_recepcion(client, tipo_id, inicial, final, anio=2026):
    return client.post(
        '/recepcion/create',
        data={
            'fecha': '2026-09-28',
            'anioCert': anio,
            'tipoCert': tipo_id,
            'folioInicial': inicial,
            'folioFinal': final,
        },
        follow_redirects=True,
    )


def test_rechaza_rango_solapado_mismo_tipo_y_anio(auth_client, app, tipo):
    _post_recepcion(auth_client, tipo.id, 100, 110)
    assert RecepcionFolio.query.count() == 1
    assert Folio.query.count() == 11

    resp = _post_recepcion(auth_client, tipo.id, 105, 120)

    assert RecepcionFolio.query.count() == 1, 'aceptó rango solapado'
    assert Folio.query.count() == 11, 'creó folios duplicados de un rango solapado'
    text = resp.get_data(as_text=True).lower()
    assert 'solap' in text, 'no muestra mensaje de solapamiento'


def test_acepta_rango_contiguo_sin_solape(auth_client, app, tipo):
    _post_recepcion(auth_client, tipo.id, 100, 102)
    resp = _post_recepcion(auth_client, tipo.id, 103, 105)

    assert RecepcionFolio.query.count() == 2
    assert Folio.query.count() == 6
    assert 'solap' not in resp.get_data(as_text=True).lower()


def test_solape_permitido_en_otro_tipo_certificado(auth_client, app, tipo):
    from app.models.tipo_certificado import TipoCertificado
    from app.extensions import db
    otro = TipoCertificado(name='Nacimientos Nacionales', color='#0D6EFD', activo=True)
    db.session.add(otro)
    db.session.commit()

    _post_recepcion(auth_client, tipo.id, 100, 110)
    _post_recepcion(auth_client, otro.id, 100, 110)

    assert RecepcionFolio.query.count() == 2, 'rechazó solape entre tipos distintos'
    assert Folio.query.count() == 22


def test_conflicto_rango_id_no_produce_500(auth_client, app, tipo, monkeypatch):
    """Si dos peticiones calculan el mismo rangoId, debe recuperarse con mensaje."""
    _post_recepcion(auth_client, tipo.id, 100, 102)
    assert RecepcionFolio.query.count() == 1

    import app.recepcion as recepcion_mod
    monkeypatch.setattr(recepcion_mod, '_next_rango_id', lambda: 1, raising=False)

    resp = _post_recepcion(auth_client, tipo.id, 103, 105)

    assert resp.status_code == 200, f'esperaba recuperación con flash, llegó {resp.status_code}'
    assert RecepcionFolio.query.count() == 1, 'creó una segunda recepción con rangoId duplicado'
    assert Folio.query.count() == 3, 'creó folios huérfanos tras el conflicto'
