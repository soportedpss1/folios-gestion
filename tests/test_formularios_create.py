"""Placeholder de centro y filtro por tipo en los formularios de creación."""

import re
from datetime import date

from app.extensions import db
from app.models.devolucion_folio import DevolucionFolio
from app.models.entrega_folio import EntregaFolio
from app.models.tipo_certificado import TipoCertificado
from tests.conftest import make_folio

Y = 2026
PLACEHOLDER = 'Seleccione el centro de salud'
OPCION_PLACEHOLDER = re.compile(
    r'<option[^>]*value=""[^>]*>Seleccione el centro de salud</option>')


def _segundo_tipo():
    tipo = TipoCertificado(name='Nacimientos', color='#198754', activo=True)
    db.session.add(tipo)
    db.session.flush()
    return tipo


# ------------------------------------------------------------- placeholders


def test_create_entrega_muestra_placeholder_y_filtro_tipo(auth_client, app, tipo):
    html = auth_client.get('/entregas/create').get_data(as_text=True)

    assert OPCION_PLACEHOLDER.search(html), (
        'el select de centro no arranca en el placeholder')
    assert 'id="tipo-select"' in html, 'falta el dropdown de tipo de certificado'
    assert '<option value="">Seleccione un tipo de certificado</option>' in html, (
        'el filtro de tipo debe arrancar en el placeholder')
    assert f'<option value="{tipo.id}">' in html, 'el tipo activo no se lista'


def test_create_devolucion_muestra_placeholder_y_filtro_tipo(auth_client, app, tipo):
    html = auth_client.get('/devoluciones/create').get_data(as_text=True)

    assert OPCION_PLACEHOLDER.search(html), (
        'el select de centro no arranca en el placeholder')
    assert 'id="tipo-select"' in html, 'falta el dropdown de tipo de certificado'
    assert '<option value="">Seleccione un tipo de certificado</option>' in html


def test_create_entrega_sin_centro_no_crea_registro(auth_client, app, tipo, operador):
    folio = make_folio(tipo, anio=Y, numero=9101)

    resp = auth_client.post('/entregas/create', data={
        'folio_ids': [folio.id], 'fechaEntrega': '2026-09-28', 'centroId': '',
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert PLACEHOLDER in resp.get_data(as_text=True), 'sin mensaje de validación'
    assert EntregaFolio.query.count() == 0, 'registró la entrega con centro vacío'
    db.session.refresh(folio)
    assert folio.estado == 'disponible', 'el folio cambió de estado sin entrega'


def test_create_devolucion_sin_centro_no_crea_registro(
    auth_client, app, folio_entregado, centro, operador
):
    resp = auth_client.post('/devoluciones/create', data={
        'centroId': '', 'folio_ids': [folio_entregado.id],
        'fechaDevolucion': '2026-09-28',
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert PLACEHOLDER in resp.get_data(as_text=True), 'sin mensaje de validación'
    assert DevolucionFolio.query.count() == 0, 'registró la devolución con centro vacío'
    db.session.refresh(folio_entregado)
    assert folio_entregado.estado == 'entregado', 'el folio cambió de estado sin devolución'


# --------------------------------------------------------- filtro por tipo


def test_api_disponibles_filtra_por_tipo(auth_client, app, tipo):
    otro = _segundo_tipo()
    primero = make_folio(tipo, anio=Y, numero=9201)
    segundo = make_folio(otro, anio=Y, numero=9202)
    db.session.commit()

    sin_filtro = auth_client.get('/entregas/api/folios-disponibles').get_json()
    assert sorted(i['id'] for i in sin_filtro) == sorted([primero.id, segundo.id])

    con_filtro = auth_client.get(
        f'/entregas/api/folios-disponibles?tipo={otro.id}').get_json()
    assert [i['id'] for i in con_filtro] == [segundo.id], (
        'el filtro de tipo no acota la lista de folios disponibles')


def test_api_devoluciones_filtra_por_tipo(auth_client, app, tipo, centro, operador):
    otro = _segundo_tipo()
    primero = make_folio(tipo, anio=Y, numero=9301, estado='entregado')
    segundo = make_folio(otro, anio=Y, numero=9302, estado='entregado')
    for folio in (primero, segundo):
        db.session.add(EntregaFolio(folio_id=folio.id, fechaEntrega=date(Y, 1, 1),
                                    centroId=centro.id, userId=operador.id))
    db.session.commit()

    sin_filtro = auth_client.get(
        f'/devoluciones/api/folios/{centro.id}').get_json()
    assert sorted(i['id'] for i in sin_filtro) == sorted([primero.id, segundo.id])

    con_filtro = auth_client.get(
        f'/devoluciones/api/folios/{centro.id}?tipo={otro.id}').get_json()
    assert [i['id'] for i in con_filtro] == [segundo.id], (
        'el filtro de tipo no acota los folios entregados del centro')


# --------------------------------------- el tipo es prerequisito de la lista


def _opciones_de(html, select_id):
    m = re.search(rf'<select[^>]*id="{select_id}"[^>]*>(.*?)</select>', html, re.S)
    return m.group(1) if m else None


def test_create_entrega_no_carga_folios_sin_tipo(auth_client, app, tipo):
    html = auth_client.get('/entregas/create').get_data(as_text=True)

    opciones = _opciones_de(html, 'folio-select')
    assert opciones is not None, 'select de folios ausente'
    assert '<option' not in opciones, (
        'el select de folios ya viene poblado sin elegir tipo de certificado')
    assert 'id="folio-hint">Seleccione un tipo de certificado para ver los folios' in html, (
        'sin hint que explique por qué no hay folios')


def test_create_devolucion_no_carga_folios_sin_tipo(auth_client, app, tipo):
    html = auth_client.get('/devoluciones/create').get_data(as_text=True)

    opciones = _opciones_de(html, 'folio-select')
    assert opciones is not None, 'select de folios ausente'
    assert '<option' not in opciones, (
        'el select de folios ya viene poblado sin elegir tipo de certificado')
    assert '<small class="text-muted" id="folio-hint">Seleccione un tipo de certificado</small>' in html, (
        'el hint inicial no pide el tipo de certificado')


def test_tipo_se_conserva_tras_error_de_validacion(auth_client, app, tipo, centro):
    resp = auth_client.post('/entregas/create', data={
        'folio_ids': [], 'fechaEntrega': '2026-09-28', 'centroId': '',
        'tipoFilter': tipo.id,
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert f'<option value="{tipo.id}" selected>' in resp.get_data(as_text=True), (
        'el tipo elegido se pierde al revalidar el form')


def test_tipo_se_conserva_tras_error_de_validacion_devolucion(
    auth_client, app, tipo, centro, folio_entregado
):
    resp = auth_client.post('/devoluciones/create', data={
        'centroId': '', 'folio_ids': [folio_entregado.id],
        'fechaDevolucion': '2026-09-28', 'tipoFilter': tipo.id,
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert f'<option value="{tipo.id}" selected>' in resp.get_data(as_text=True), (
        'el tipo elegido se pierde al revalidar el form')


# ------------------------------------- sin búsqueda en la nueva entrega


def test_create_entrega_no_tiene_campo_de_busqueda(auth_client, app, tipo):
    """El tipo de certificado reemplaza a la búsqueda por número."""
    html = auth_client.get('/entregas/create').get_data(as_text=True)
    assert 'id="folio-search"' not in html, 'sigue el campo de búsqueda de folios'
    assert 'id="tipo-select"' in html, 'sin el filtro de tipo que lo reemplaza'


def test_api_disponibles_respeta_limit(auth_client, app, tipo):
    """Sin limit queda el tope de 100 (editar entrega); con limit carga el total."""
    from app.services.movimientos import MAX_FOLIOS_SELECT

    for n in range(7000, 7150):  # 150 folios disponibles
        make_folio(tipo, anio=Y, numero=n)
    db.session.commit()

    assert len(auth_client.get('/entregas/api/folios-disponibles').get_json()) == 100

    con_limit = auth_client.get('/entregas/api/folios-disponibles?limit=500').get_json()
    assert len(con_limit) == 150, 'limit no se aplica'

    tope = auth_client.get(
        f'/entregas/api/folios-disponibles?limit={MAX_FOLIOS_SELECT + 5000}').get_json()
    assert len(tope) == 150, 'el tope no deja pedir menos de lo que hay'


def test_api_disponibles_limit_negativo_o_invalido(auth_client, app, tipo):
    make_folio(tipo, anio=Y, numero=7201)
    db.session.commit()

    assert auth_client.get('/entregas/api/folios-disponibles?limit=-5').get_json(), (
        'limit negativo vacía la lista')
    assert auth_client.get('/entregas/api/folios-disponibles?limit=abc').get_json(), (
        'limit no numérico vacía la lista')
