"""Componente de paginación: los links deben conservar los demás params."""

from pathlib import Path

PLANTILLA = (Path(__file__).resolve().parent.parent
             / 'app' / 'templates' / 'components' / 'pagination.html')


def test_pagina_url_preserva_los_demas_params(app):
    """Antes se hacía replace('page=N') sobre el query string crudo:
    per_page=10&page=1 → replace('page=1','') → 'per_0' (per_page perdido)."""
    with app.test_request_context('/folios/?per_page=10&page=3'):
        fn = app.jinja_env.globals.get('pagina_url')
        assert fn, 'falta la global pagina_url'
        url = fn(2)
        assert 'page=2' in url
        assert 'per_page=10' in url, 'per_page debe sobrevivir al cambiar de página'


def test_pagination_html_usa_pagina_url():
    tpl = PLANTILLA.read_text(encoding='utf-8')
    assert 'pagina_url' in tpl, 'la paginación debe usar pagina_url'
    assert 'query_string.decode().replace' not in tpl, \
        'el replace sobre el query string crudo rompe otros params'
