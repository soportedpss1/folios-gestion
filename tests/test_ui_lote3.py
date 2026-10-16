"""Lote 3 de la auditoría UI/UX: botón Importar con grant solo-importar,
sidebar de Centros para rol lectura, doble paginación (DataTables +
paginación del servidor), Volver de Escaneos, auto-carga de reportes,
PDFs con tildes/ñ y páginas de error inline con tema oscuro."""

import re
from pathlib import Path

import pytest

from app.extensions import db
from app.models.permiso_usuario import PermisoUsuario
from tests.conftest import make_user

RAIZ = Path(__file__).resolve().parents[1]


def _login(app, username):
    client = app.test_client()
    client.post('/auth/login', data={'username': username, 'password': 'pass12345'})
    return client


# --- 1. Importar visible con grant solo-importar (sin gestión/crear) ---

@pytest.mark.parametrize('grant, ruta, esperada', [
    ('entregas.importar', '/entregas/', '/entregas/importar'),
    ('devoluciones.importar', '/devoluciones/', '/devoluciones/importar'),
    ('recepcion.ver', '/recepcion/', '/recepcion/importar'),  # permiso base p/ la ruta
])
def test_importar_visible_con_grant_solo_importar(app, grant, ruta, esperada):
    user = make_user('lector_imp', rol='lectura')
    db.session.add(PermisoUsuario(user_id=user.id, permiso=grant))
    if grant != 'recepcion.importar':
        db.session.add(PermisoUsuario(user_id=user.id, permiso='recepcion.importar'))
    db.session.commit()

    body = _login(app, 'lector_imp').get(ruta).get_data(as_text=True)
    assert esperada in body, \
        'el botón Importar queda oculto si el usuario no tiene también gestionar/crear'


def test_recepcion_importar_visible_con_grant(app):
    user = make_user('lector_rec', rol='lectura')
    db.session.add(PermisoUsuario(user_id=user.id, permiso='recepcion.ver'))
    db.session.add(PermisoUsuario(user_id=user.id, permiso='recepcion.importar'))
    db.session.commit()

    body = _login(app, 'lector_rec').get('/recepcion/').get_data(as_text=True)
    assert '/recepcion/importar' in body, \
        'el botón Importar de recepción exige además recepcion.crear'


# --- 2. Sidebar muestra Centros a rol lectura (la ruta es solo login) ---

def test_sidebar_centros_visible_para_lectura(app):
    make_user('lectura', rol='lectura')
    body = _login(app, 'lectura').get('/dashboard/').get_data(as_text=True)
    assert 'href="/centros/"' in body, \
        'el sidebar esconde Centros aunque /centros/ es accesible con login'


# --- 3. Sin doble paginación: DataTables + paginación del servidor ---

@pytest.mark.parametrize('ruta, tabla_vieja', [
    ('/entregas/', '<table class="table table-hover align-middle mb-0 data-table">'),
    ('/devoluciones/', '<table class="table table-hover align-middle mb-0 data-table">'),
    ('/recepcion/', '<table class="table table-hover align-middle mb-0 data-table">'),
    ('/dashboard/', '<table class="table table-hover mb-0 data-table">'),
])
def test_indices_sin_datatables_y_paginacion_server(admin_client, ruta, tabla_vieja):
    body = admin_client.get(ruta).get_data(as_text=True)
    assert tabla_vieja not in body, \
        f'{ruta}: DataTables y paginación del servidor compiten (doble control de página)'
    assert 'render_pagination' not in body  # la paginación server sigue declarada


# --- 4. Volver de Escaneos regresa a Folios, no al Dashboard ---

def test_escaneos_volver_apunta_a_folios(admin_client):
    body = admin_client.get('/escaneos/subir').get_data(as_text=True)
    match = re.search(r'<a href="([^"]+)"[^>]*>\s*<i class="fas fa-arrow-left',
                      body, re.S)
    assert match, 'falta el botón Volver en escaneos'
    assert match.group(1) == '/folios/', \
        'Volver de Escaneos apunta al Dashboard en vez de al módulo de origen'


# --- 5. Reportes: F5 con filtros en la URL debe recargar la tabla ---

def test_reports_js_autocarga_si_hay_filtros_en_url():
    src = (RAIZ / 'app' / 'static' / 'js' / 'reports.js').read_text(encoding='utf-8')
    assert 'location.search' in src, \
        'reports.js no consulta la URL al iniciar: F5 deja la tabla vacía'


# --- 6. PDFs con tildes y ñ (WeasyPrint soporta UTF-8) ---

def _capturar_pdf(monkeypatch):
    try:
        import weasyprint
    except OSError as exc:
        pytest.skip(f'weasyprint sin libpango (solo Docker): {exc}')

    class _FakeHTML:
        captured = []

        def __init__(self, string=None, **kwargs):
            _FakeHTML.captured.append(string)

        def write_pdf(self):
            return b'%PDF-1.4 fake'

    _FakeHTML.captured = []
    monkeypatch.setattr(weasyprint, 'HTML', _FakeHTML)
    return _FakeHTML


def test_pdf_reportes_con_tildes(admin_client, monkeypatch):
    fake = _capturar_pdf(monkeypatch)
    resp = admin_client.get('/reportes/export/pdf')
    assert resp.status_code == 200
    html = fake.captured[0]
    assert 'Dirección Provincial' in html, 'encabezado del PDF sin tilde'
    assert 'Año' in html, 'PDF de reportes sin "Año" acentuado'


def test_pdf_recepcion_con_tildes(admin_client, monkeypatch):
    fake = _capturar_pdf(monkeypatch)
    resp = admin_client.get('/recepcion/export/pdf')
    assert resp.status_code == 200
    html = fake.captured[0]
    assert 'Recepción de Folios' in html, 'título del PDF sin tilde'
    assert 'Año Cert.' in html, 'columna del PDF sin tilde'


def test_pdf_centros_con_tildes(admin_client, monkeypatch):
    fake = _capturar_pdf(monkeypatch)
    resp = admin_client.get('/centros/export/pdf')
    assert resp.status_code == 200
    html = fake.captured[0]
    assert 'Gestión de Centros' in html, 'título del PDF sin tilde'
    assert 'Teléfono' in html and 'Dirección' in html, \
        'columnas del PDF sin tilde'


# --- 7. Páginas de error inline: tema oscuro y sin bg-light ---

def test_error_404_respetando_tema(admin_client):
    resp = admin_client.get('/ruta-inexistente-xyz')
    assert resp.status_code == 404
    body = resp.get_data(as_text=True)
    assert 'bg-light' not in body, 'la página de error fuerza fondo claro'
    assert 'folios-tema' in body, 'la página de error ignora el tema guardado'
