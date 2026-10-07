"""Fase 5 — centrado de mensajes de tabla vacía en detalle de centros.

El mensaje debe ir en un <td colspan="N"> (todo el ancho, como el resto de
templates); con un <td> normal solo ocupa la columna 1 y se ve a la izquierda.
"""

import re


def _get_detalle(auth_client, centro):
    resp = auth_client.get(f'/centros/{centro.id}/detail')
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def test_pendientes_vacio_a_todo_el_ancho(auth_client, app, centro):
    html = _get_detalle(auth_client, centro)
    assert re.search(
        r'<td[^>]*colspan="5"[^>]*>\s*<i class="fas fa-check-circle.*?'
        r'No hay folios pendientes de devolución',
        html, re.S,
    ), 'mensaje de pendientes sin colspan a todo el ancho'


def test_todos_entregados_vacio_a_todo_el_ancho(auth_client, app, centro):
    html = _get_detalle(auth_client, centro)
    assert re.search(
        r'<td[^>]*colspan="7"[^>]*>\s*<i class="fas fa-inbox.*?'
        r'No hay entregas registradas para este centro',
        html, re.S,
    ), 'mensaje de entregas sin colspan a todo el ancho'


def test_devueltos_vacio_a_todo_el_ancho(auth_client, app, centro):
    html = _get_detalle(auth_client, centro)
    assert re.search(
        r'<td[^>]*colspan="6"[^>]*>\s*<i class="fas fa-undo.*?'
        r'No hay devoluciones registradas para este centro',
        html, re.S,
    ), 'mensaje de devoluciones sin colspan a todo el ancho'


def test_sin_celdas_relleno_vacias(auth_client, app, centro):
    html = _get_detalle(auth_client, centro)
    assert '<td></td>' not in html, 'quedaron celdas relleno vacías tras el mensaje'


# --- DataTables no soporta colspan en tbody (tn/18): init debe saltarse tablas vacías ---

def test_init_tablas_salta_colspan_en_detalle(auth_client, app, centro):
    html = _get_detalle(auth_client, centro)
    assert 'tbody td[colspan]' in html, \
        'initTable de detail no salta DT en tablas vacías (DataTables tn/18)'


def test_init_data_table_global_salta_colspan(auth_client, app):
    resp = auth_client.get('/entregas/')
    assert resp.status_code == 200
    assert 'tbody td[colspan]' in resp.get_data(as_text=True), \
        'init global de base.html no salta DT en tablas vacías (DataTables tn/18)'
