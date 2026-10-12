"""Almacenamiento temporal del respaldo pendiente de confirmación."""

import os
import time

from app.backup import staging


def test_guardar_y_consumir():
    token = staging.guardar(b'{"meta": {}}')
    assert staging.consumir(token) == b'{"meta": {}}'
    # El token es de un solo uso.
    assert staging.consumir(token) is None


def test_token_invalido_no_abre_archivos():
    for token in ('../../etc/passwd', '', 'a' * 500, 'con espacios', None):
        assert staging.consumir(token) is None


def test_archivo_vencido_no_se_recupera():
    token = staging.guardar(b'{}')
    viejo = time.time() - staging.VIGENCIA_SEG - 60
    os.utime(staging._ruta(token), (viejo, viejo))
    assert staging.consumir(token) is None


def test_archivo_con_permisos_restringidos():
    """El respaldo staging tiene hashes de contraseña: 0644 lo dejaba
    legible para cualquier usuario del host."""
    import stat as stat_mod
    token = staging.guardar(b'{"meta": {}}')
    ruta = staging._ruta(token)
    assert stat_mod.S_IMODE(ruta.stat().st_mode) == 0o600


def test_directorio_preexistente_laxo_se_reajusta():
    """mkdir(mode=...) solo aplica al crear: si otro proceso dejó el dir en
    0777, los respaldos siguientes quedaban world-readable."""
    import stat as stat_mod
    d = staging._directorio()
    d.chmod(0o777)
    staging._directorio()
    assert stat_mod.S_IMODE(d.stat().st_mode) == 0o700
