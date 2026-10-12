"""Respaldo pendiente de confirmación: archivo subido, aún no restaurado.

El JSON no cabe en la sesión (es una cookie), así que se guarda aquí, en un
directorio privado, y solo se conoce el token — que viaja en la sesión del
quien lo subió. Se borra al confirmar, o a los VIGENCIA_SEG si nadie confirma.
"""

import os
import re
import secrets
import tempfile
import time
from pathlib import Path

VIGENCIA_SEG = 30 * 60

# token_urlsafe usa [A-Za-z0-9_-]; cualquier otra cosa se descarta antes de
# tocar el sistema de archivos.
_TOKEN_RE = re.compile(r'^[A-Za-z0-9_-]{16,128}$')


def _directorio():
    ruta = Path(tempfile.gettempdir()) / 'folios_respaldo'
    ruta.mkdir(mode=0o700, exist_ok=True)
    # mkdir(mode=...) solo aplica al crear: si el dir ya existía con permisos
    # laxos (p. ej. creado por otro proceso), aquí se re-fuerza.
    ruta.chmod(0o700)
    return ruta


def _ruta(token):
    return _directorio() / f'{token}.json'


def _valido(token):
    return isinstance(token, str) and _TOKEN_RE.match(token) is not None


def limpiar_vencidos():
    """Borra los archivos que nadie confirmó a tiempo."""
    limite = time.time() - VIGENCIA_SEG
    for ruta in _directorio().glob('*.json'):
        try:
            if ruta.stat().st_mtime < limite:
                ruta.unlink()
        except OSError:
            continue


def guardar(crudo):
    """Guarda el respaldo y devuelve su token (un solo uso).

    El archivo se crea con 0600 (contiene hashes de contraseña y datos
    personales): write_bytes dejaría el umask por defecto (0644).
    """
    limpiar_vencidos()
    token = secrets.token_urlsafe(24)
    fd = os.open(_ruta(token), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as archivo:
        archivo.write(crudo)
    return token


def consumir(token):
    """Lee y borra el respaldo. None si el token es inválido o venció."""
    if not _valido(token):
        return None
    ruta = _ruta(token)
    try:
        if ruta.stat().st_mtime < time.time() - VIGENCIA_SEG:
            ruta.unlink()
            return None
        crudo = ruta.read_bytes()
    except OSError:
        return None
    ruta.unlink(missing_ok=True)
    return crudo
