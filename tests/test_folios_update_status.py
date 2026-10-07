def test_update_status_body_null_devuelve_400(auth_client, app, folio):
    """Body JSON `null` no debe tumbar la ruta con 500."""
    resp = auth_client.post(
        '/folios/update-status',
        data='null',
        content_type='application/json',
    )
    assert resp.status_code == 400, f'esperaba 400, llegó {resp.status_code}'
    assert resp.get_json()['success'] is False


def test_update_status_sin_flags_devuelve_400(auth_client, app, folio):
    """Falta digitado/escaneado/nulo → 400, no sobrescribir con None."""
    resp = auth_client.post(
        '/folios/update-status',
        json={'folio_ids': [folio.id]},
    )
    assert resp.status_code == 400, f'esperaba 400, llegó {resp.status_code}'


def test_update_status_tipos_invalidos_devuelve_400(auth_client, app, folio):
    resp = auth_client.post(
        '/folios/update-status',
        json={'folio_ids': 'no-es-lista', 'digitado': 'yes', 'escaneado': 1, 'nulo': {}},
    )
    assert resp.status_code == 400, f'esperaba 400, llegó {resp.status_code}'


def test_update_status_valido_actualiza_y_responde_200(auth_client, app, folio):
    resp = auth_client.post(
        '/folios/update-status',
        json={'folio_ids': [folio.id], 'digitado': True, 'escaneado': False, 'nulo': False},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True

    from app.extensions import db
    from app.models.folio import Folio
    updated = db.session.get(Folio, folio.id)
    assert updated.digitado is True
    assert updated.escaneado is False
    assert updated.nulo is False


def test_update_status_sin_permisos_devuelve_403(client, app, folio):
    """Rol 'lectura' no puede editar (403), no 200."""
    from tests.conftest import make_user
    make_user('lectura', 'lectura')
    client.post('/auth/login', data={'username': 'lectura', 'password': 'pass12345'})

    resp = client.post(
        '/folios/update-status',
        json={'folio_ids': [folio.id], 'digitado': True, 'escaneado': False, 'nulo': False},
    )
    assert resp.status_code == 403
