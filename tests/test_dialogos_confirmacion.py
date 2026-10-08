"""Diálogos de confirmación: SweetAlert2 vía data-confirm, sin confirm() nativo."""

from pathlib import Path

from tests.test_recepcion_gestionar import crear_recepcion

PLANTILLAS = Path(__file__).resolve().parents[1] / 'app' / 'templates'


def get(client, ruta):
    resp = client.get(ruta)
    assert resp.status_code == 200, f'{ruta} devolvió {resp.status_code}'
    return resp.get_data(as_text=True)


def test_ninguna_plantilla_usa_confirm_nativo():
    """Barrido de las plantillas: el confirm() del navegador no debe volver."""
    sucias = sorted(
        str(p.relative_to(PLANTILLAS))
        for p in PLANTILLAS.rglob('*.html')
        if 'onsubmit="return confirm(' in p.read_text(encoding='utf-8')
    )
    assert not sucias, f'confirm() nativo en: {sucias}'


def test_base_carga_confirmar_js(admin_client):
    text = get(admin_client, '/dashboard/')
    assert 'js/confirmar.js' in text, 'el helper de confirmación no se carga'


def test_recepcion_data_confirm_danger(admin_client, tipo):
    crear_recepcion(admin_client, tipo.id)
    text = get(admin_client, '/recepcion/')
    assert 'data-confirm' in text
    assert 'data-icon="danger"' in text
    assert '¿Eliminar la recepción #1' in text, 'el texto original cambió'


def test_centros_data_confirm(admin_client, centro):
    text = get(admin_client, '/centros/')
    assert 'data-confirm' in text
    assert '¿Desactivar este centro?' in text
    assert 'data-icon="danger"' not in text, 'acciones reversibles usan warning default'


def test_certificados_data_confirm(admin_client, tipo):
    text = get(admin_client, '/certificados/')
    assert 'data-confirm' in text
    assert '¿Desactivar este tipo de certificado?' in text


def test_usuarios_data_confirm(admin_client, operador):
    # El form de delete no se renderiza para el propio usuario logueado.
    text = get(admin_client, '/usuarios/')
    assert 'data-confirm' in text
    assert '¿Desactivar este usuario?' in text


def test_marca_data_confirm(admin_client):
    text = get(admin_client, '/marca/')
    assert text.count('data-confirm') == 2, 'logo y favicon'
    assert '¿Eliminar el logo actual?' in text
    assert '¿Eliminar el favicon actual?' in text


def test_sincronizacion_data_confirm(admin_client):
    text = get(admin_client, '/sincronizacion/')
    assert 'data-confirm' in text
    assert '¿Sincronizar ahora con Google Sheets?' in text


def test_backup_data_confirm_danger():
    # El form de restaurar solo se renderiza tras previsualizar un respaldo
    # (flujo en 2 pasos con token): se verifica la plantilla directamente.
    plantilla = (PLANTILLAS / 'backup' / 'index.html').read_text(encoding='utf-8')
    assert 'data-confirm' in plantilla
    assert 'data-icon="danger"' in plantilla
    assert '¿Restaurar el respaldo?' in plantilla
