"""Consultas con ORM moderno (Query.get() es legacy y emite LegacyAPIWarning)."""

from flask import abort

from app.extensions import db


def get_or_404(Model, ident, description=None):
    """db.session.get + 404 — equivalente a Model.query.get_or_404 sin warnings."""
    obj = db.session.get(Model, ident)
    if obj is None:
        abort(404, description=description)
    return obj


def usuario_activo(raw, fallback):
    """Valor crudo de un form (usuarioId) → Usuario activo; si falta o no
    califica, devuelve `fallback` para que la operación nunca se rompa."""
    from app.models.usuario import Usuario
    try:
        uid = int(raw)
    except (TypeError, ValueError):
        return fallback
    usuario = db.session.get(Usuario, uid)
    if usuario is None or not usuario.activo:
        return fallback
    return usuario


def resolver_usuario_nombre(nombre, fallback):
    """Username de una celda Excel → (usuario, error).

    Vacío → (fallback, None): la fila la reclama quien importa. Con valor se
    busca por username sin distinguir mayúsculas; si no existe o está inactivo
    → (None, 'Usuario desconocido: X.' / 'Usuario inactivo: X.') para que la
    vista previa marque la fila inválida.
    """
    from sqlalchemy import func

    from app.models.usuario import Usuario
    texto = str(nombre or '').strip()
    if not texto:
        return fallback, None
    usuario = Usuario.query.filter(
        func.lower(Usuario.username) == texto.lower()
    ).first()
    if usuario is None:
        return None, f'Usuario desconocido: {texto}.'
    if not usuario.activo:
        return None, f'Usuario inactivo: {texto}.'
    return usuario, None
