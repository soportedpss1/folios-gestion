"""Reglas de negocio de usuarios compartidas entre blueprints."""

from app.models.usuario import Usuario


def ultimo_admin_excluido(user):
    """True si `user` es el único admin activo del sistema.

    La cuenta se hace con lectura de bloqueo (FOR UPDATE): dos admins
    desactivándose mutuamente en transacciones concurrentes pasarían ambos
    la lectura normal (snapshot previo) y dejarían el sistema sin admin.
    Solo aporta en MariaDB; SQLite (tests) ignora FOR UPDATE.
    """
    if user.rol != 'admin' or not user.activo:
        return False
    restantes = len(Usuario.query.filter(
        Usuario.rol == 'admin',
        Usuario.activo == True,
        Usuario.id != user.id,
    ).with_for_update().all())
    return restantes == 0
