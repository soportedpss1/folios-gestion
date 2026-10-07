"""Fase 3 — los PDF deben escapar HTML inyectado en nombres (centros, usuarios, tipos)."""

import pytest

try:
    import weasyprint
except OSError as exc:
    pytest.skip(f'weasyprint sin libpango (solo Docker): {exc}', allow_module_level=True)


class _FakeHTML:
    captured = []

    def __init__(self, string=None, **kwargs):
        _FakeHTML.captured.append(string)

    def write_pdf(self):
        return b'%PDF-1.4 fake'


def _seed_nombres_con_html(app, tipo, centro):
    from app.extensions import db
    from app.models.usuario import Usuario

    tipo.name = 'Defunciones<script>alert(1)</script>'
    centro.name = '<img src=x onerror=alert(2)>'
    operador = Usuario.query.filter_by(username='operador').one()
    operador.username = '<b>usuario</b>'
    db.session.commit()


def test_reportes_pdf_escapa_html_inyectado(auth_client, app, tipo, centro, folio_entregado, monkeypatch):
    _seed_nombres_con_html(app, tipo, centro)
    _FakeHTML.captured = []
    monkeypatch.setattr(weasyprint, 'HTML', _FakeHTML)

    resp = auth_client.get('/reportes/export/pdf')

    assert resp.status_code == 200
    assert resp.headers['Content-Type'] == 'application/pdf'
    assert len(_FakeHTML.captured) == 1, 'el PDF no se generó'
    html = _FakeHTML.captured[0]
    assert '<script>alert(1)</script>' not in html, 'HTML sin escapar en PDF de reportes'
    assert '<img src=x onerror=alert(2)>' not in html, 'HTML sin escapar en PDF de reportes'
    assert '&lt;script&gt;' in html, 'el HTML no contiene el texto escapado'


def test_centros_pdf_escapa_html_inyectado(auth_client, app, tipo, centro, folio_entregado, monkeypatch):
    _seed_nombres_con_html(app, tipo, centro)
    _FakeHTML.captured = []
    monkeypatch.setattr(weasyprint, 'HTML', _FakeHTML)

    resp = auth_client.get(f'/centros/{centro.id}/export/pdf')

    assert resp.status_code == 200
    assert len(_FakeHTML.captured) == 1, 'el PDF no se generó'
    html = _FakeHTML.captured[0]
    assert '<img src=x onerror=alert(2)>' not in html, 'HTML sin escapar en PDF de centros'
    assert '<b>usuario</b>' not in html, 'HTML sin escapar en PDF de centros'
    assert '&lt;img src=x' in html, 'el HTML no contiene el texto escapado'
