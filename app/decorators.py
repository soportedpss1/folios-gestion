"""Decorators de permisos compartidos entre blueprints."""

from functools import wraps

from flask import flash, redirect, request, url_for
from flask_login import current_user, login_required

from app.services.permisos import puede


def edit_required(f):
    """Bloquea rutas que requieren rol editor y redirige al índice del blueprint.

    Incluye login_required: la ruta queda protegida aunque no se apile
    @login_required aparte.
    """
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.can_edit():
            flash('No tiene permisos para esta acción.', 'danger')
            blueprint = request.endpoint.rsplit('.', 1)[0]
            return redirect(url_for(f'{blueprint}.index'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Bloquea rutas de administración: exige sesión iniciada y rol admin."""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin():
            flash('No tiene permisos para acceder a esta sección.', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated_function


def permiso_requerido(clave, hacia='dashboard'):
    """Bloquea la ruta si ni el rol default ni un grant habilitan `clave`.

    hacia='dashboard' → redirect a dashboard.index (rutas de sección admin);
    hacia='blueprint' → redirect al índice del blueprint actual (acciones de
    edición). Incluye login_required.
    """
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if not puede(clave):
                if hacia == 'blueprint':
                    flash('No tiene permisos para esta acción.', 'danger')
                    bp = request.endpoint.rsplit('.', 1)[0]
                    return redirect(url_for(f'{bp}.index'))
                flash('No tiene permisos para acceder a esta sección.', 'danger')
                return redirect(url_for('dashboard.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator
