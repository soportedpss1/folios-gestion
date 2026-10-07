"""Módulo de escaneos: subir JPG de folios y marcarlos como escaneados."""

import os

from app.config import Config
from app.services.permisos import PERMISOS, puede
from tests.conftest import make_user


def test_permiso_escaneos_existe_y_es_edit():
    assert 'escaneos.subir' in PERMISOS
    assert PERMISOS['escaneos.subir'] == ('Subir escaneos', 'edit')


def test_permiso_escaneos_por_rol(app):
    operador = make_user('operador', 'operador')
    lectura = make_user('lector', 'lectura')
    assert puede('escaneos.subir', operador) is True
    assert puede('escaneos.subir', lectura) is False


def test_config_scans_folder():
    assert Config.SCANS_FOLDER.endswith('scans')
    assert os.path.isabs(Config.SCANS_FOLDER)
