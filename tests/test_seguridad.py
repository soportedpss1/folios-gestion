"""Fase 3 — headers de seguridad + logout solo POST."""

from app.extensions import db


def test_headers_de_seguridad_en_respuestas(client):
    resp = client.get('/auth/login')
    assert resp.headers.get('X-Content-Type-Options') == 'nosniff', 'falta X-Content-Type-Options'
    assert resp.headers.get('X-Frame-Options') == 'SAMEORIGIN', 'falta X-Frame-Options'
    assert resp.headers.get('Referrer-Policy'), 'falta Referrer-Policy'
    assert resp.headers.get('Strict-Transport-Security'), 'falta Strict-Transport-Security'


def test_error_page_404_con_sri_en_cdn(client):
    resp = client.get('/ruta-que-no-existe-xyz')
    assert resp.status_code == 404
    html = resp.get_data(as_text=True)
    assert 'integrity="sha384-' in html, 'CDN sin SRI en la página de error'


def test_logout_get_rechazado(client, app, operador):
    client.post('/auth/login', data={'username': operador.username, 'password': 'pass12345'})
    resp = client.get('/auth/logout')
    assert resp.status_code == 405, f'GET /logout debe ser 405, llegó {resp.status_code}'


def test_logout_post_cierra_sesion(client, app, operador):
    client.post('/auth/login', data={'username': operador.username, 'password': 'pass12345'})
    assert client.get('/dashboard/').status_code == 200

    resp = client.post('/auth/logout')
    assert resp.status_code == 302, f'POST /logout debe redirigir, llegó {resp.status_code}'

    # sesión cerrada: /dashboard/ rebota a login
    dash = client.get('/dashboard/')
    assert dash.status_code == 302
    assert '/auth/login' in dash.headers['Location']


def test_error_page_no_compila_marcas_jinja(admin_client, client):
    """SSTI: la marca (DB) debe renderizarse literal en las páginas de error.

    `render_error` interpolaba la marca al FUENTE del template con f-string
    y lo compilaba con render_template_string → `{{ ... }}` en la marca
    ejecutaba Jinja (RCE). Regresión: el payload debe aparecer literal.
    """
    resp = admin_client.post('/marca/', data={
        'nombre': '{{ 7*7 }}', 'titulo_sufijo': '', 'subtitulo': '',
    })
    assert resp.status_code == 302, 'guardar marca falló'
    text = client.get('/ruta-que-no-existe-xyz').get_data(as_text=True)
    assert '{{ 7*7 }}' in text, 'la marca debe verse literal, no evaluarse'


def test_reports_js_escapa_datos_del_servidor():
    """Reportes arma filas con innerHTML: todo dato del servidor debe escaparse
    (nombre de tipo/centro/usuarios controlados por formularios solo con Length)."""
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent
          / 'app' / 'static' / 'js' / 'reports.js').read_text(encoding='utf-8')
    assert 'function escapeHtml' in js, 'falta el helper de escape'
    for campo in ('f.tipo_nombre', 'f.tipo_color', 'f.centro',
                  'f.entregado_por', 'f.recibido_por'):
        assert f'escapeHtml({campo})' in js, f'{campo} se inserta sin escapar'


def test_admin_no_se_desactiva_a_si_mismo_via_edit(app, client):
    """delete() prohíbe la auto-desactivación; edit() no la replicaba: con
    otro admin activo, el último guard no aplica y el admin se borraba a sí
    mismo sin querer (auto-logout silencioso)."""
    from tests.conftest import make_user
    admin_a = make_user('admin_a', 'admin')
    make_user('admin_b', 'admin')
    client.post('/auth/login', data={'username': 'admin_a', 'password': 'pass12345'})

    resp = client.post(f'/usuarios/{admin_a.id}/edit', follow_redirects=True, data={
        'name': admin_a.name, 'username': admin_a.username,
        'email': 'admin_a@example.com', 'rol': 'admin',  # sin 'activo'
    })
    assert resp.status_code == 200
    db.session.refresh(admin_a)
    assert admin_a.activo, 'edit no debe permitir desactivarse a uno mismo'


def test_413_indica_el_limite_real(app):
    """El mensaje decía '5 MB' hardcodeado; el límite real es configurable."""
    app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024
    resp = app.test_client().post('/auth/login', data=b'x' * (3 * 1024 * 1024))
    assert resp.status_code == 413
    assert '2 MB' in resp.get_data(as_text=True), \
        'el 413 debe decir el límite configurado, no un valor fijo'


def test_edit_usuario_registra_cambio_de_password(admin_client, app):
    """Un reset desde la UI quedaba indistinguible en /auditoria."""
    from app.models.audit_log import AuditLog
    from tests.conftest import make_user
    objetivo = make_user('target_pwd', 'operador')

    admin_client.post(f'/usuarios/{objetivo.id}/edit', data={
        'name': objetivo.name, 'username': objetivo.username,
        'email': 'target_pwd@example.com', 'password': 'nuevapass1',
        'rol': 'operador', 'activo': 'y',
    }, follow_redirects=True)

    db.session.refresh(objetivo)
    assert objetivo.check_password('nuevapass1')
    log = AuditLog.query.filter_by(tabla='usuarios', accion='UPDATE') \
        .order_by(AuditLog.id.desc()).first()
    assert log is not None
    assert log.datos_nuevos.get('password_changed') is True, \
        'el audit debe marcar el cambio de contraseña'


def test_auditoria_filtros_cubren_eventos_sensibles(admin_client):
    """BACKUP/RESTORE y permiso_usuarios/marca_config existían en la tabla
    pero no en los <select>: los eventos más sensibles no se podían filtrar."""
    text = admin_client.get('/auditoria/').get_data(as_text=True)
    for valor in ('BACKUP', 'RESTORE', 'permiso_usuarios', 'marca_config'):
        assert f'value="{valor}"' in text, f'falta {valor} en los filtros'
