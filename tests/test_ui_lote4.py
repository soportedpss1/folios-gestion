"""Lote 4 de la auditoría UI/UX: accesibilidad y ARIA — labels con for,
asociación label-control, aria-live en actualizaciones dinámicas, contraste
de badges, roles ARIA en tabs y alerts, tipos de input, accept en file
inputs y aria en paginación/buscadores."""

import re
from pathlib import Path

import pytest

from tests.test_importar_centros import post_importar as post_centros
from tests.test_importar_centros import HEADERS as CENTROS_HEADERS
from tests.test_importar_nulos import post_importar_nulos

RAIZ = Path(__file__).resolve().parents[1]
PLANTILLAS = RAIZ / 'app' / 'templates'


def _tag_attr(body, patrón):
    """Extrae el tag HTML completo que cumple patrón (attrs en cualquier orden)."""
    match = re.search(patrón, body, re.S)
    return match.group(0) if match else None


# --- 1. Barrido: ningún <label> sin for en ninguna plantilla ---

def test_barrido_labels_con_for_en_plantillas():
    culpables = []
    for plantilla in PLANTILLAS.rglob('*.html'):
        for num, linea in enumerate(plantilla.read_text(encoding='utf-8').splitlines(), 1):
            for etiqueta in re.findall(r'<label\b[^>]*>', linea):
                if 'for=' not in etiqueta:
                    rel = plantilla.relative_to(PLANTILLAS)
                    culpables.append(f'{rel}:{num}')
    assert not culpables, f'labels sin for (campo inaccesible): {culpables}'


# --- 2. Render: cada for apunta a un id que existe en la página ---

@pytest.mark.parametrize('ruta', [
    '/centros/create',
    '/usuarios/create',
    '/certificados/create',
    '/recepcion/create',
    '/reportes/',
    '/auditoria/',
    '/folios/',
    '/folios/transferencias',
    '/sincronizacion/',
    '/escaneos/subir',
    '/marca/',
    '/backup/',
])
def test_for_apunta_a_id_existente(admin_client, ruta):
    body = admin_client.get(ruta).get_data(as_text=True)
    ids = set(re.findall(r'\bid="([^"]+)"', body))
    pendientes = [f for f in re.findall(r'<label\b[^>]*for="([^"]+)"', body)
                  if f not in ids]
    assert not pendientes, f'{ruta}: for sin id correspondiente: {pendientes}'


# --- 3. Campos concretos con nombre accesible ---

def test_sincronizacion_frecuencia_tiene_label(admin_client):
    body = admin_client.get('/sincronizacion/').get_data(as_text=True)
    assert 'for="frecuencia_minutos"' in body, \
        'el campo de frecuencia se renderiza sin label'


def test_detalle_transferencia_y_comentario_con_label(admin_client, folio_entregado):
    body = admin_client.get(f'/folios/{folio_entregado.id}').get_data(as_text=True)
    assert 'for="motivo"' in body, 'el motivo de transferencia sin label'
    assert 'for="texto"' in body, 'el textarea de comentario sin label'


def test_usuarios_email_password_autocomplete(admin_client):
    body = admin_client.get('/usuarios/create').get_data(as_text=True)
    assert 'type="email"' in body, 'email como texto plano: teclado y validación nativos'
    assert 'autocomplete="email"' in body
    assert 'autocomplete="new-password"' in body, 'passwords sin autocomplete'


def test_centros_telefono_tipo_tel(admin_client):
    body = admin_client.get('/centros/create').get_data(as_text=True)
    tag = _tag_attr(body, r'<input[^>]*name="telefono"[^>]*>')
    assert tag and 'type="tel"' in tag, 'teléfono sin type="tel" (teclado móvil)'


# --- 4. aria-live en contadores y hints que cambian por JS ---

@pytest.mark.parametrize('ruta', ['/entregas/create', '/devoluciones/create'])
def test_create_contadores_con_aria_live(admin_client, ruta):
    body = admin_client.get(ruta).get_data(as_text=True)
    for ident in ('selected-count', 'folio-hint'):
        tag = _tag_attr(body, rf'<[^>]*id="{ident}"[^>]*>')
        assert tag, f'{ruta}: falta #{ident}'
        assert 'aria-live' in tag, f'{ruta}: #{ident} cambia por JS sin aria-live'


def test_reportes_stats_con_aria_live(admin_client):
    body = admin_client.get('/reportes/').get_data(as_text=True)
    assert '<div class="row g-3 mb-4" aria-live="polite">' in body, \
        'los KPIs de reportes cambian sin anuncio a lectores de pantalla'


# --- 5. Contraste de badges ---

@pytest.mark.parametrize('ruta', ['/entregas/create', '/devoluciones/create'])
def test_badge_info_con_texto_oscuro(admin_client, ruta):
    body = admin_client.get(ruta).get_data(as_text=True)
    assert 'badge bg-info text-dark' in body, \
        f'{ruta}: badge bg-info con texto blanco (contraste 1.96:1)'


def test_centros_detail_badge_info_contraste():
    src = (PLANTILLAS / 'centros' / 'detail.html').read_text(encoding='utf-8')
    assert 'badge bg-info text-dark' in src, \
        'badge de días con texto blanco (contraste 1.96:1)'


def test_sincronizacion_atrasado_sin_text_warning(admin_client, app):
    from datetime import timedelta

    from app.extensions import db as _db
    from app.models.sync_config import get_config
    from app.utils import utcnow

    cfg = get_config()
    cfg.activo = True
    # Último intento hace 8 días: el próximo ya pasó → estado "atrasado".
    cfg.ultimo_intento_at = utcnow() - timedelta(days=8)
    _db.session.commit()

    body = admin_client.get('/sincronizacion/').get_data(as_text=True)
    assert 'Pendiente (atrasado)' in body
    assert '<span class="text-warning">' not in body, \
        'text-warning amarillo sobre blanco (contraste 1.6:1)'


# --- 6. Alerts de resultado con role=status ---

def test_preview_importar_alert_role_status(admin_client, tipo, folio):
    resp = post_importar_nulos(admin_client, [[1000]])
    tag = _tag_attr(resp.get_data(as_text=True),
                    r'<div class="alert alert-(?:info|danger)[^>]*>')
    assert tag, 'la vista previa no muestra su alert de resultado'
    assert 'role="status"' in tag, 'el resultado del POST sin role=status'


def test_preview_centros_alert_role_status(admin_client):
    resp = post_centros(admin_client, CENTROS_HEADERS,
                        [['Hospital Norte', '555555', 'Calle 1']])
    tag = _tag_attr(resp.get_data(as_text=True),
                    r'<div class="alert alert-(?:info|danger)[^>]*>')
    assert tag and 'role="status"' in tag, \
        'el resultado de importar centros sin role=status'


# --- 7. Tabs del detalle de centro con ARIA completa ---

def test_centros_detail_tabs_aria(admin_client, centro):
    body = admin_client.get(f'/centros/{centro.id}/detail').get_data(as_text=True)
    assert 'role="tab"' in body, 'tabs sin role="tab"'
    assert 'aria-selected' in body, 'tabs sin aria-selected'
    assert 'role="tabpanel"' in body, 'paneles sin role="tabpanel"'


# --- 8. Buscadores con aria-label ---

@pytest.mark.parametrize('ruta', ['/reportes/', '/auditoria/'])
def test_table_search_con_aria_label(admin_client, ruta):
    body = admin_client.get(ruta).get_data(as_text=True)
    tag = _tag_attr(body, r'<input[^>]*id="tableSearch"[^>]*>')
    assert tag, f'{ruta}: falta #tableSearch'
    assert 'aria-label' in tag, f'{ruta}: buscador con solo placeholder'


def test_auditoria_buscador_indica_que_es_desta_pagina(admin_client):
    body = admin_client.get('/auditoria/').get_data(as_text=True)
    assert 'Buscar en esta página' in body, \
        'el buscador de auditoría filtra solo la página sin decirlo'


# --- 9. File inputs con accept ---

@pytest.mark.parametrize('ruta, esperado', [
    ('/folios/importar', '.xlsx'),
    ('/centros/importar', '.xlsx'),
    ('/recepcion/importar', '.xlsx'),
    ('/entregas/importar', '.xlsx'),
    ('/devoluciones/importar', '.xlsx'),
    ('/escaneos/subir', 'image/jpeg'),
    ('/marca/', 'image/'),
    ('/backup/', '.json'),
])
def test_file_input_con_accept(admin_client, ruta, esperado):
    body = admin_client.get(ruta).get_data(as_text=True)
    tag = _tag_attr(body, r'<input[^>]*type="file"[^>]*>')
    assert tag, f'{ruta}: sin input file'
    assert 'accept=' in tag, f'{ruta}: file input sin accept (error recién en el server)'
    assert esperado in tag, f'{ruta}: accept no incluye {esperado}'


# --- 10. Paginación con aria (fuente del macro y de reports.js) ---

def test_macro_paginacion_con_aria():
    src = (PLANTILLAS / 'components' / 'pagination.html').read_text(encoding='utf-8')
    assert 'aria-label="Paginación"' in src, '<nav> de paginación sin aria-label'
    assert 'Página anterior' in src and 'Página siguiente' in src, \
        'prev/next solo con icono: sin nombre accesible'


def test_reports_js_paginacion_e_iconos_aria():
    src = (RAIZ / 'app' / 'static' / 'js' / 'reports.js').read_text(encoding='utf-8')
    assert 'aria-label="Página' in src, 'paginación de reportes sin aria-label'
    assert 'visually-hidden' in src, \
        'iconos Sí/No de reportes sin texto oculto para lectores de pantalla'
    assert "setAttribute('role', 'alert')" in src, \
        'el error de carga de reportes no se anuncia como alerta'
