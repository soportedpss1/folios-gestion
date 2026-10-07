from urllib.parse import urljoin, urlparse

from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import limiter
from app.models.usuario import Usuario
from app.auth.forms import LoginForm

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


def _is_safe_next(target):
    """Solo permite redirecciones relativas al mismo host (anti open-redirect)."""
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return (
        test_url.scheme in ('http', 'https')
        and ref_url.netloc == test_url.netloc
    )


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10/minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    form = LoginForm()
    if form.validate_on_submit():
        user = Usuario.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data) and user.activo:
            login_user(user)
            session.permanent = True  # aplica PERMANENT_SESSION_LIFETIME (timeout de sesión)
            flash('Sesión iniciada correctamente.', 'success')
            next_page = request.args.get('next')
            if not _is_safe_next(next_page):
                next_page = url_for('dashboard.index')
            return redirect(next_page)
        else:
            flash('Usuario o contraseña incorrectos.', 'danger')

    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash('Sesión cerrada correctamente.', 'info')
    return redirect(url_for('auth.login'))
