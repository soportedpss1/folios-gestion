import importlib
import sys

import pytest


def _load_run(flask_config, monkeypatch):
    sys.modules.pop('run', None)
    if flask_config is None:
        monkeypatch.delenv('FLASK_CONFIG', raising=False)
    else:
        monkeypatch.setenv('FLASK_CONFIG', flask_config)
    return importlib.import_module('run').app


@pytest.fixture(autouse=True)
def _clean_run_module():
    yield
    sys.modules.pop('run', None)


def test_run_por_defecto_es_produccion_sin_debug(monkeypatch):
    """Docker/Gunicorn ejecutan run:app sin FLASK_CONFIG → producción, DEBUG off."""
    app = _load_run(None, monkeypatch)
    assert app.debug is False, 'DEBUG activo en arranque por defecto'
    # HTTP plano (deploy actual): cookie Secure nunca se guardaría y el login
    # no persistiría. Se enciende solo con SESSION_COOKIE_SECURE=true (tras TLS).
    assert app.config['SESSION_COOKIE_SECURE'] is False


def test_run_flask_config_development_activa_debug(monkeypatch):
    app = _load_run('development', monkeypatch)
    assert app.debug is True


def test_run_flask_config_desconocido_cae_en_produccion(monkeypatch):
    app = _load_run('typo', monkeypatch)
    assert app.debug is False
    assert app.config['SESSION_COOKIE_SECURE'] is False


def test_session_cookie_secure_activable_tras_tls(monkeypatch):
    monkeypatch.setenv('SESSION_COOKIE_SECURE', 'true')
    app = _load_run(None, monkeypatch)
    assert app.config['SESSION_COOKIE_SECURE'] is True
