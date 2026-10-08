"""Mensajes flash como toasts flotantes y tema de diálogos SweetAlert2."""

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PLANTILLAS = RAIZ / 'app' / 'templates'
STATIC = RAIZ / 'app' / 'static'


def leer(relativo: str) -> str:
    return (RAIZ / 'app' / relativo).read_text(encoding='utf-8')


def test_flash_renderiza_toasts_no_alerts():
    """El partial de flash deja de usar .alert de Bootstrap."""
    flash = leer('templates/components/flash.html')
    assert 'app-toast' in flash, 'los mensajes usan la clase de toast'
    assert 'alert alert-' not in flash, 'quedó markup de alert inline'
    assert 'role="alert"' in flash
    assert 'aria-live' in flash, 'los toasts anuncian a lectores de pantalla'
    assert 'flash-toasts' in flash, 'contenedor con id para el auto-dismiss'


def test_flash_danger_duracion_larga():
    """danger usa timeout largo (10s); el resto 4s."""
    flash = leer('templates/components/flash.html')
    assert 'data-duracion' in flash
    assert '10000' in flash, 'danger debe durar 10s'
    assert '4000' in flash, 'success/info/warning duran 4s'


def test_main_js_expone_app_toast():
    """El sistema de toasts es invocable desde plantillas (feedback AJAX)."""
    js = leer('static/js/main.js')
    assert 'AppToast' in js
    assert 'mostrar' in js


def test_confirmar_js_boton_danger():
    """La confirmación destructiva usa el botón rojo del tema."""
    js = leer('static/js/confirmar.js')
    assert 'swal-confirm-danger' in js
    assert 'data-text' in js, 'soporte de descripción de la acción'


def test_css_toasts_y_tema_swal():
    """main.css estiliza toasts y SweetAlert2 con los tokens de la app."""
    css = leer('static/css/main.css')
    assert '.toast-container' in css
    assert '.app-toast-danger' in css
    assert 'swal-confirm-danger' in css
    assert 'prefers-reduced-motion' in css

    tokens = leer('static/css/variables.css')
    assert '--toast-bg' in tokens, 'tokens de toast en light y dark'


def test_feedback_ajax_usa_toasts():
    """folios y dashboard reportan resultados por toast, no por Swal modal."""
    folios = leer('templates/folios/index.html')
    assert 'AppToast.mostrar' in folios
    assert "Swal.fire('Error'" not in folios

    dashboard = leer('templates/dashboard/index.html')
    assert 'AppToast.mostrar' in dashboard
    assert "Swal.fire('Error'" not in dashboard
