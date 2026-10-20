"""Optimizaciones de UI: contraste dark, DataTables condicional, tablas responsive.

1. --text-muted-tone sin override en dark deja .app-toast-close/.swal2-close
   por debajo de 4.5:1 (checklist de contraste).
2. base.html servía DataTables a todas las páginas aunque solo 5 lo usan;
   ahora va en bloques Jinja que cada página que lo necesita incluye.
3. Las tablas de detail (folio/centro) sin .table-responsive desbordan
   en 375px.
"""

import re
from pathlib import Path

from app.extensions import db
from tests.conftest import make_folio

STATIC = Path(__file__).resolve().parents[1] / 'app' / 'static'


# ------------------------------------------------- 1. contraste dark mode


def test_text_muted_tone_se_redefine_en_dark():
    css = (STATIC / 'css' / 'variables.css').read_text(encoding='utf-8')
    m = re.search(
        r'\[data-bs-theme="dark"\]\s*\{[^}]*--text-muted-tone\s*:\s*([^;]+);',
        css)
    assert m, 'falta --text-muted-tone en el bloque dark (contraste en toasts/swal)'
    valor = m.group(1).strip()
    assert valor == '#94A3B8', (
        f'--text-muted-tone en dark = {valor}; se espera #94A3B8 (7:1 sobre #16223A)')


# ----------------------------------------------- 2. DataTables condicional


def test_login_no_carga_datatables(client):
    html = client.get('/auth/login').get_data(as_text=True)
    assert 'datatables.net' not in html, (
        'el login no usa tablas: no debe cargar DataTables')
    assert '.DataTable(' not in html, 'el init de DataTables no debe servirse'


def test_folios_listado_no_carga_datatables(auth_client, app, tipo):
    make_folio(tipo, anio=2026, numero=1700)
    db.session.commit()
    html = auth_client.get('/folios/').get_data(as_text=True)
    assert 'datatables.net' not in html, (
        '/folios/ usa paginación propia, no DataTables')


def test_listado_usuarios_si_carga_datatables(admin_client):
    html = admin_client.get('/usuarios/').get_data(as_text=True)
    assert 'cdn.datatables.net' in html, 'usuarios usa .data-table'
    assert '.DataTable(' in html, 'falta el init de DataTables en usuarios'


def test_centro_detail_si_carga_datatables(auth_client, app, centro, tipo):
    make_folio(tipo, anio=2026, numero=1701)
    db.session.commit()
    html = auth_client.get(f'/centros/{centro.id}/detail').get_data(as_text=True)
    assert 'cdn.datatables.net' in html, 'centros/detail inicializa DataTables'
    assert '.DataTable(' in html


# ----------------------------------------------- 3. tablas mobile-safe


def test_folios_detail_tablas_responsive(auth_client, app, tipo):
    folio = make_folio(tipo, anio=2026, numero=1702)
    db.session.commit()
    html = auth_client.get(f'/folios/{folio.id}').get_data(as_text=True)
    tablas = html.count('<table')
    assert tablas >= 1, 'el detalle debe renderizar al menos la tabla de info'
    assert html.count('table-responsive') == tablas, (
        f'{tablas} tablas en el detalle del folio pero '
        f'{html.count("table-responsive")} envueltas en .table-responsive')


def test_centro_detail_tablas_responsive(auth_client, app, centro, tipo):
    make_folio(tipo, anio=2026, numero=1703)
    db.session.commit()
    html = auth_client.get(f'/centros/{centro.id}/detail').get_data(as_text=True)
    tablas = html.count('<table')
    assert tablas == 4, f'se esperaban 4 tablas, hay {tablas}'
    assert html.count('table-responsive') == tablas, (
        f'{tablas} tablas en el detalle de centro pero '
        f'{html.count("table-responsive")} envueltas en .table-responsive')
