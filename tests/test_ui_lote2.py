"""Lote 2 de fixes UI/UX: Cancelar de la vista previa de importar debe volver
al índice del módulo (no al propio import), y hover consistente en la tabla
de la página de copias."""

import re

from tests.test_importar_centros import (
    HEADERS as CENTROS_HEADERS,
    post_importar as post_centros,
)
from tests.test_importar_devoluciones import (
    Y,
    post_importar as post_devoluciones,
)
from tests.test_importar_entregas import (
    post_importar as post_entregas,
)
from tests.test_importar_recepcion import (
    HEADERS as RECEPCION_HEADERS,
    post_importar as post_recepcion,
)
from tests.conftest import make_folio


def _afirma_cancelar(body, indice):
    match = re.search(
        rf'<a href="{re.escape(indice)}"[^>]*>\s*Cancelar\s*</a>', body, re.S)
    assert match, (
        f'la vista previa no tiene un Cancelar hacia {indice}: '
        'Cancelar vuelve al import y deja perdido el trabajo')


def test_centros_preview_cancelar_vuelve_al_indice(admin_client):
    resp = post_centros(admin_client, CENTROS_HEADERS,
                        [['Hospital Norte', '555555', 'Calle 1']])
    assert resp.status_code == 200
    _afirma_cancelar(resp.get_data(as_text=True), '/centros/')


def test_recepcion_preview_cancelar_vuelve_al_indice(admin_client, tipo):
    resp = post_recepcion(admin_client, RECEPCION_HEADERS,
                          [['2026-10-01', 2026, tipo.name, 1, 5, 'adminuser']])
    assert resp.status_code == 200
    _afirma_cancelar(resp.get_data(as_text=True), '/recepcion/')


def test_entregas_preview_cancelar_vuelve_al_indice(admin_client, tipo, centro):
    make_folio(tipo, anio=Y, numero=1000)
    resp = post_entregas(admin_client,
                         [[1000, tipo.name, Y, '01/10/2026', centro.name,
                           'adminuser']])
    assert resp.status_code == 200
    _afirma_cancelar(resp.get_data(as_text=True), '/entregas/')


def test_devoluciones_preview_cancelar_vuelve_al_indice(
        admin_client, folio_entregado, centro, tipo):
    resp = post_devoluciones(admin_client, [
        [folio_entregado.folio, tipo.name, Y, '02/10/2026', centro.name,
         'adminuser']])
    assert resp.status_code == 200
    _afirma_cancelar(resp.get_data(as_text=True), '/devoluciones/')
