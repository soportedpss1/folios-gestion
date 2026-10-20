"""Rediseño del login: layout split (panel de marca + panel de formulario).

El login viejo era una card centrada genérica (card-footer con el pie
institucional). El nuevo separa identidad (panel con degradado de marca)
del formulario, con encabezado compacto para móvil.
"""


def _html(client):
    resp = client.get('/auth/login')
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def test_login_layout_split(client):
    html = _html(client)
    assert 'login-split' in html, 'falta el contenedor split'
    assert 'login-brand' in html, 'falta el panel de marca'
    assert 'login-form-panel' in html, 'falta el panel del formulario'
    assert 'login-brand-compact' in html, 'falta el encabezado compacto móvil'


def test_login_identidad_en_pagina(client):
    html = _html(client)
    assert 'Dirección Provincial de Salud Santiago 1' in html
    assert 'Departamento de Bioestadística' in html, (
        'el pie institucional debe seguir visible')
    assert 'Gestión de folios' in html, (
        'el panel de marca debe comunicar qué hace el sistema')


def test_login_sin_estructura_vieja(client):
    html = _html(client)
    assert 'login-container' not in html, 'el contenedor viejo debe irse'
    assert 'card-footer' not in html, (
        'el pie debe vivir en el panel de marca, no en un card-footer')


def test_login_form_conserva_campos_y_feedback(client):
    html = _html(client)
    for fragmento in (
        'name="username"',
        'name="password"',
        'id="toggle-password"',
        'autocomplete="current-password"',
        'autocomplete="username"',
        'data-loading',
    ):
        assert fragmento in html, f'falta {fragmento} en el login'


def test_login_error_de_credenciales_anuncia_role_alert(client, app, operador):
    """El flash de error vive en un elemento con role="alert" (a11y)."""
    resp = client.post('/auth/login', data={
        'username': operador.username, 'password': 'clave-mala',
    })
    assert resp.status_code == 200
    assert 'role="alert"' in resp.get_data(as_text=True), (
        'el mensaje de credenciales incorrectas debe ser role="alert"')
