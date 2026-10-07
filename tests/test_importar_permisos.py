"""Importar es solo de administradores: botón oculto y rutas bloqueadas.

El botón "Importar" no se muestra a no-admins y las 8 rutas (importar,
confirmar, plantilla ×4 módulos) exigen @admin_required: un operador que llegue
por URL recibe el flash de permisos y cae en el dashboard.
"""

MODULOS = ['recepcion', 'entregas', 'devoluciones', 'centros']


# --- visibilidad del botón en los índices ---


def test_boton_importar_oculto_para_operador(auth_client):
    for m in MODULOS:
        text = auth_client.get(f'/{m}/').get_data(as_text=True)
        assert f'/{m}/importar' not in text, f'operador no ve Importar en {m}'


def test_boton_importar_oculto_para_lectura(client, app):
    from tests.conftest import make_user
    make_user('lectura', 'lectura')
    client.post('/auth/login', data={'username': 'lectura', 'password': 'pass12345'})
    for m in MODULOS:
        text = client.get(f'/{m}/').get_data(as_text=True)
        assert f'/{m}/importar' not in text


def test_boton_importar_visible_para_admin(admin_client):
    for m in MODULOS:
        text = admin_client.get(f'/{m}/').get_data(as_text=True)
        assert f'/{m}/importar' in text, f'admin sí ve Importar en {m}'


# --- rutas bloqueadas para no-admins ---


def test_importar_bloqueado_para_operador(auth_client):
    resp = auth_client.get('/recepcion/importar', follow_redirects=True)
    assert resp.status_code == 200
    assert 'No tiene permisos' in resp.get_data(as_text=True)
    assert '/dashboard' in resp.request.path, 'admin_required redirige al dashboard'


def test_plantilla_bloqueada_para_operador(auth_client):
    for m in MODULOS:
        resp = auth_client.get(f'/{m}/plantilla', follow_redirects=True)
        assert 'No tiene permisos' in resp.get_data(as_text=True), m
        assert 'spreadsheetml' not in resp.content_type, m


def test_confirmar_bloqueado_para_operador(auth_client):
    resp = auth_client.post('/recepcion/importar/confirmar',
                            data={'payload': '[]'}, follow_redirects=True)
    assert 'No tiene permisos' in resp.get_data(as_text=True)


def test_importar_con_rol_lectura_bloqueado(client, app):
    from tests.conftest import make_user
    make_user('lectura', 'lectura')
    client.post('/auth/login', data={'username': 'lectura', 'password': 'pass12345'})
    resp = client.get('/entregas/importar', follow_redirects=True)
    assert 'No tiene permisos' in resp.get_data(as_text=True)


def test_importar_sin_sesion_redirige_a_login(client):
    assert client.get('/recepcion/importar').status_code == 302
    assert client.post('/recepcion/importar/confirmar').status_code == 302
    assert client.get('/devoluciones/plantilla').status_code == 302
