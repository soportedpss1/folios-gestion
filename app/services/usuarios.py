"""Reglas de negocio de usuarios compartidas entre blueprints."""

from app.models.usuario import Usuario


def ultimo_admin_excluido(user):
    """True si `user` es el único admin activo del sistema."""
    if user.rol != 'admin' or not user.activo:
        return False
    restantes = Usuario.query.filter(
        Usuario.rol == 'admin',
        Usuario.activo == True,
        Usuario.id != user.id,
    ).count()
    return restantes == 0
