"""Resumen de selección de folios (inicial/final/cantidad) en crear entrega y devolución."""


def get(client, ruta):
    resp = client.get(ruta)
    assert resp.status_code == 200, f'{ruta} devolvió {resp.status_code}'
    return resp.get_data(as_text=True)


def test_entregas_create_muestra_resumen(auth_client):
    html = get(auth_client, '/entregas/create')
    assert 'id="folio-resumen"' in html, 'falta el panel de resumen'
    assert 'id="resumen-inicial"' in html
    assert 'id="resumen-final"' in html
    assert 'id="resumen-cantidad"' in html
    assert 'updateResumen' in html, 'la lógica JS del resumen no está'


def test_devoluciones_create_muestra_resumen(auth_client, centro):
    html = get(auth_client, '/devoluciones/create')
    assert 'id="folio-resumen"' in html, 'falta el panel de resumen'
    assert 'id="resumen-inicial"' in html
    assert 'id="resumen-final"' in html
    assert 'id="resumen-cantidad"' in html
    assert 'updateResumen' in html, 'la lógica JS del resumen no está'
