"""Versión de la app.

El archivo VERSION de la raíz del repo es la única fuente: viaja en la
imagen Docker (`.dockerignore` excluye `.git`, así que no hay git describe
posible) y se publica como el tag de Docker Hub. Se lee una vez al arrancar
y se inyecta como `app_version` en todos los templates (footer del sidebar).
"""

from pathlib import Path

RUTA_VERSION = Path(__file__).resolve().parent.parent / 'VERSION'


def leer_version(fallback='dev'):
    """Contenido del archivo VERSION, o `fallback` si falta o está vacío."""
    try:
        return RUTA_VERSION.read_text(encoding='utf-8').strip() or fallback
    except OSError:
        return fallback
