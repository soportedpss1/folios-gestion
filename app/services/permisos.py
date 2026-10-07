"""Permisos granulares por usuario.

Semántica grant-only: un permiso concedido SUMA capacidades al rol, nunca las
quita. El rol decide el default (admin = todo; operador = acciones de edición;
lectura = solo lectura) y los grants habilitan excepciones p. ej. un lectura
que sí puede importar.

Catálogo: clave -> ('etiqueta', default) donde default es 'admin' o 'edit'.
"""

from flask import g, has_request_context
from flask_login import current_user

from app.models.permiso_usuario import PermisoUsuario

PERMISOS = {
    'usuarios.gestionar': ('Gestionar usuarios', 'admin'),
    'centros.gestionar': ('Crear/editar/desactivar centros', 'admin'),
    'centros.importar': ('Importar centros desde Excel', 'admin'),
    'recepcion.ver': ('Ver recepción y exports', 'admin'),
    'recepcion.importar': ('Importar rangos de recepción', 'admin'),
    'entregas.importar': ('Importar entregas', 'admin'),
    'devoluciones.importar': ('Importar devoluciones', 'admin'),
    'folios.importar': ('Importar folios desde Excel', 'admin'),
    'certificados.gestionar': ('Gestionar tipos de certificado', 'admin'),
    'auditoria.ver': ('Ver auditoría', 'admin'),
    'sincronizacion.usar': ('Usar sincronización con Google Sheets', 'admin'),
    'recepcion.crear': ('Crear recepciones', 'admin'),
    'entregas.gestionar': ('Crear/editar entregas', 'edit'),
    'devoluciones.gestionar': ('Crear/editar devoluciones', 'edit'),
    'folios.actualizar': ('Actualizar estado de folios', 'edit'),
    'escaneos.subir': ('Subir escaneos', 'admin'),
}


def grants_de(user):
    """Claves concedidas al usuario.

    Cache por request en flask.g (la plantilla llama `puede` muchas veces);
    fuera de un request no se cachea para que los tests vean el estado real.
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return frozenset()
    if has_request_context():
        cache = getattr(g, 'perm_grants_cache', None)
        if cache is not None and cache[0] == user.id:
            return cache[1]
    permisos = frozenset(
        p.permiso for p in PermisoUsuario.query.filter_by(user_id=user.id).all())
    if has_request_context():
        g.perm_grants_cache = (user.id, permisos)
    return permisos


def puede(clave, user=None):
    """True si el rol default o un grant habilita la clave.

    Clave desconocida → False (un typo nunca abre una ruta por accidente;
    los tests del catálogo lo atrapan).
    """
    if user is None:
        user = current_user
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    entry = PERMISOS.get(clave)
    if entry is None:
        return False
    _, kind = entry
    if kind == 'admin' and user.is_admin():
        return True
    if kind == 'edit' and user.can_edit():
        return True
    return clave in grants_de(user)


def permisos_de(user):
    """Catálogo completo con el estado efectivo de cada clave para el usuario."""
    grants = grants_de(user)
    return {
        clave: (etiqueta, puede(clave, user))
        for clave, (etiqueta, _kind) in PERMISOS.items()
    }
