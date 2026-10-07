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
