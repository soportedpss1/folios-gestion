"""Estado 'perdido': marcaje reversible SOLO desde el detalle del folio.

Un folio disponible o entregado puede marcarse como perdido desde su página
de detalle (audit UPDATE); recuperarlo lo devuelve a su estado previo
DERIVADO del registro de entrega: con EntregaFolio → 'entregado', sin
registro → 'disponible'. Un devuelto no se marca (ya volvió al almacén).
No hay bulk en el índice. En índice y reportes el filtro de estado gana la
opción 'perdido'; KPIs y dashboard no cambian.
"""

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.folio import Folio
from tests.conftest import make_folio, make_user


def perder(client, folio):
    return client.post(f'/folios/{folio.id}/perder', follow_redirects=True)


def recuperar(client, folio):
    return client.post(f'/folios/{folio.id}/recuperar', follow_redirects=True)


def cliente_lectura(client):
    make_user('lectura', 'lectura')
    client.post('/auth/login', data={'username': 'lectura', 'password': 'pass12345'})
    return client


def estado(folio):
    return db.session.get(Folio, folio.id).estado


# --- transiciones desde el detalle ---


def test_perder_folio_disponible(admin_client, folio):
    resp = perder(admin_client, folio)

    assert estado(folio) == 'perdido'
    assert 'marcado como perdido' in resp.get_data(as_text=True)
    log = AuditLog.query.filter_by(tabla='folios', accion='UPDATE').one()
    assert log.datos_anteriores['estado'] == 'disponible'
    assert log.datos_nuevos['estado'] == 'perdido'


def test_recuperar_folio_vuelve_a_disponible(admin_client, folio):
    perder(admin_client, folio)
    recuperar(admin_client, folio)

    assert estado(folio) == 'disponible'


def test_perder_folio_entregado_y_recuperar_vuelve_a_entregado(
        admin_client, folio_entregado):
    perder(admin_client, folio_entregado)
    assert estado(folio_entregado) == 'perdido'
    assert folio_entregado.entrega is not None, 'el registro de entrega queda'

    recuperar(admin_client, folio_entregado)
    assert estado(folio_entregado) == 'entregado'


def test_no_se_puede_perder_un_devuelto(admin_client, tipo):
    folio = make_folio(tipo, anio=2026, numero=3000, estado='devuelto')
    db.session.commit()

    resp = perder(admin_client, folio)

    assert estado(folio) == 'devuelto'
    assert 'disponibles o entregados' in resp.get_data(as_text=True)
    assert AuditLog.query.filter_by(tabla='folios').count() == 0


def test_recuperar_un_no_perdido_no_hace_nada(admin_client, folio):
    resp = recuperar(admin_client, folio)

    assert estado(folio) == 'disponible'
    assert 'Solo los folios perdidos' in resp.get_data(as_text=True)


def test_operador_con_permiso_puede_perder(auth_client, folio):
    perder(auth_client, folio)
    assert estado(folio) == 'perdido'


def test_rol_lectura_no_puede_perder_ni_recuperar(client, folio):
    cliente_lectura(client)

    perder(client, folio)
    assert estado(folio) == 'disponible', 'la acción fue bloqueada'

    folio.estado = 'perdido'
    db.session.commit()
    recuperar(client, folio)
    assert estado(folio) == 'perdido', 'la acción fue bloqueada'


# --- el marcado vive SOLO en el detalle: el bulk del índice no existe ---


def test_endpoints_bulk_no_existen(admin_client, folio):
    for url in ('/folios/perdidos/marcar', '/folios/perdidos/recuperar'):
        resp = admin_client.post(url, json={'folio_ids': [folio.id]})
        assert resp.status_code == 404, f'{url} debió desaparecer'
    assert estado(folio) == 'disponible'


def test_indice_sin_bulk(admin_client, folio):
    text = admin_client.get('/folios/').get_data(as_text=True)

    assert '<input type="checkbox" class="form-check-input check-folio"' not in text
    assert 'Marcar como perdidos' not in text
    assert 'Recuperar seleccionados' not in text
    assert 'barra-perdidos' not in text


# --- UI: filtros, badges, botones ---


def test_indice_filtro_estado_perdido(admin_client, tipo):
    perdido = make_folio(tipo, anio=2026, numero=1000)
    disponible = make_folio(tipo, anio=2026, numero=9999)
    db.session.commit()
    perdido.estado = 'perdido'
    db.session.commit()

    text = admin_client.get('/folios/?estado=perdido').get_data(as_text=True)

    assert '1000' in text
    assert '9999' not in text, 'el filtro no muestra folios de otros estados'


def test_reportes_filtro_estado_perdido(admin_client, tipo):
    perdido = make_folio(tipo, anio=2026, numero=1000)
    disponible = make_folio(tipo, anio=2026, numero=9999)
    db.session.commit()
    perdido.estado = 'perdido'
    db.session.commit()

    # las filas del reporte se sirven desde /reportes/api/data (JSON)
    resp = admin_client.get('/reportes/api/data?estado=perdido')

    assert resp.status_code == 200
    assert [f['folio'] for f in resp.get_json()['folios']] == [1000], \
        'el filtro no muestra folios de otros estados'
    text = admin_client.get('/reportes/').get_data(as_text=True)
    assert 'value="perdido"' in text, 'el select de estado ofrece Perdido'


def test_indice_muestra_badge_perdido(admin_client, folio):
    perder(admin_client, folio)
    text = admin_client.get('/folios/').get_data(as_text=True)

    assert 'badge bg-warning text-dark">Perdido' in text


def test_detalle_muestra_boton_perder(admin_client, folio):
    text = admin_client.get(f'/folios/{folio.id}').get_data(as_text=True)
    assert 'Marcar como perdido' in text


def test_detalle_muestra_boton_recuperar(admin_client, tipo):
    folio = make_folio(tipo, anio=2026, numero=1000)
    db.session.commit()
    perder(admin_client, folio)

    text = admin_client.get(f'/folios/{folio.id}').get_data(as_text=True)
    assert 'Recuperar folio' in text


def test_detalle_sin_permiso_no_muestra_boton(client, folio):
    text = cliente_lectura(client).get(f'/folios/{folio.id}').get_data(as_text=True)
    assert 'Marcar como perdido' not in text
