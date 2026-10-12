"""Versión de la app: el archivo VERSION es la única fuente.

`app/version.py` lee el archivo VERSION de la raíz del repo (viaja en la
imagen Docker) y `create_app` lo expone como `app.config['APP_VERSION']` y
como `app_version` en todos los templates. El footer del sidebar lo muestra;
no hay números de versión hardcodeados.
"""

import re
from pathlib import Path

from app.version import leer_version


def test_leer_version_lee_el_archivo_del_repo():
    esperada = Path(__file__).resolve().parent.parent \
        .joinpath('VERSION').read_text(encoding='utf-8').strip()
    assert esperada, 'el repo debe mantener el archivo VERSION'
    assert leer_version() == esperada


def test_leer_version_fallback_dev(monkeypatch):
    monkeypatch.setattr('app.version.RUTA_VERSION',
                        Path('/no/existe/VERSION'))
    assert leer_version() == 'dev'


def test_sidebar_muestra_la_version(admin_client):
    text = admin_client.get('/dashboard/',
                            follow_redirects=True).get_data(as_text=True)
    bloque = re.search(r'<div class="sidebar-footer">.*?</div>', text, re.S)
    assert bloque, 'el sidebar tiene footer con versión'
    assert f'v{leer_version()}' in bloque.group(0)
    assert 'v1.0.0' not in text, 'sin versión hardcodeada'
