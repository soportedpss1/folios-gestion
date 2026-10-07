"""Marca de la aplicación: textos, logo, favicon y encabezado de PDF."""

import base64
import io

from app.extensions import db
from app.models.marca import get_marca
from app.services.pdf import encabezado_pdf, logo_pdf

# PNG 1x1 mínimo válido.
PNG_1X1 = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
)


def _post_marca(client, **extra):
    data = {'nombre': 'Gestión de Folios', 'titulo_sufijo': '', 'subtitulo': ''}
    data.update(extra)
    return client.post('/marca/', data=data, content_type='multipart/form-data')


def test_operador_no_accede(auth_client):
    resp = auth_client.get('/marca/')
    assert resp.status_code == 302


def test_admin_abre(admin_client):
    resp = admin_client.get('/marca/')
    text = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert 'Marca de la aplicación' in text
    assert 'Quitar logo' in text


def test_guardar_textos_cambia_ui(admin_client):
    resp = admin_client.post('/marca/', data={
        'nombre': 'Mi Marca',
        'titulo_sufijo': 'ZZ',
        'subtitulo': 'Sub nueva',
    })
    assert resp.status_code == 302

    dash = admin_client.get('/dashboard/').get_data(as_text=True)
    assert 'Mi Marca' in dash          # sidebar
    assert 'Sub nueva' in dash         # subtítulo del sidebar
    assert 'Dashboard - ZZ' in dash    # sufijo del <title>

    cfg = get_marca()
    assert cfg.nombre == 'Mi Marca'
    assert cfg.titulo_sufijo == 'ZZ'


def test_logo_upload_y_ruta_publica(admin_client):
    resp = _post_marca(admin_client, logo=(io.BytesIO(PNG_1X1), 'logo.png'))
    assert resp.status_code == 302

    img = admin_client.get('/marca/logo')
    assert img.status_code == 200
    assert img.content_type == 'image/png'
    assert img.data == PNG_1X1

    dash = admin_client.get('/dashboard/').get_data(as_text=True)
    assert '<img' in dash and '/marca/logo' in dash


def test_logo_tipo_invalido_no_guarda(admin_client):
    resp = _post_marca(admin_client, logo=(io.BytesIO(b'nope'), 'logo.txt'))
    assert resp.status_code == 200  # re-render con error
    assert get_marca().logo is None
    assert admin_client.get('/marca/logo').status_code == 404


def test_logo_grande_rechazado(admin_client):
    grande = b'0' * (512 * 1024 + 1)
    resp = _post_marca(admin_client, logo=(io.BytesIO(grande), 'logo.png'))
    assert resp.status_code == 200
    assert 'máximo 512 KB' in resp.get_data(as_text=True)
    assert get_marca().logo is None


def test_quitar_logo(admin_client):
    _post_marca(admin_client, logo=(io.BytesIO(PNG_1X1), 'logo.png'))
    assert get_marca().logo is not None

    resp = admin_client.post('/marca/quitar-logo')
    assert resp.status_code == 302
    assert get_marca().logo is None
    assert admin_client.get('/marca/logo').status_code == 404


def test_favicon_upload(admin_client):
    resp = _post_marca(admin_client, favicon=(io.BytesIO(PNG_1X1), 'favicon.png'))
    assert resp.status_code == 302

    fav = admin_client.get('/marca/favicon')
    assert fav.status_code == 200
    assert fav.content_type == 'image/png'

    dash = admin_client.get('/dashboard/').get_data(as_text=True)
    assert 'rel="icon"' in dash


def test_rutas_imagen_publicas_sin_sesion(client):
    # Login sin sesión necesita favicon/logo: no redirigen, responden 404 sin datos.
    assert client.get('/marca/logo').status_code == 404
    assert client.get('/marca/favicon').status_code == 404


def test_encabezado_pdf_con_logo(app):
    cfg = get_marca()
    cfg.logo = PNG_1X1
    cfg.logo_mime = 'image/png'
    db.session.commit()

    html = encabezado_pdf('Titulo Prueba')
    assert 'data:image/png;base64' in html
    assert '<h3>Titulo Prueba</h3>' in html
    assert 'Direccion Provincial de Salud Santiago 1' in html


def test_encabezado_pdf_sin_logo(app):
    assert logo_pdf() == ''
    assert 'data:' not in encabezado_pdf('Titulo Prueba')


def test_encabezado_pdf_tolera_fallo_db(app):
    from sqlalchemy.exc import SQLAlchemyError

    cfg = get_marca()
    cfg.logo = PNG_1X1
    cfg.logo_mime = 'image/png'
    db.session.commit()

    original = get_marca

    def roto():
        raise SQLAlchemyError('db caida')

    import app.services.pdf as pdf_mod
    pdf_mod.get_marca = roto
    try:
        assert logo_pdf() == ''
    finally:
        pdf_mod.get_marca = original
