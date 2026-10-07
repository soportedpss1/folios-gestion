"""Fase 3 — headers de seguridad + logout solo POST."""


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
