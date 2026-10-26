from urllib.parse import urljoin, urlparse

from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy.exc import IntegrityError

from app.extensions import db, limiter
from app.models.usuario import Usuario
from app.auth.forms import LoginForm, RegistroForm
from app.services.audit import log_audit
from app.services.mensajes import DUP_USUARIO

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
        if user and user.check_password(form.password.data):
            if user.activo:
                login_user(user)
                session.permanent = True  # aplica PERMANENT_SESSION_LIFETIME (timeout de sesión)
                flash('Sesión iniciada exitosamente.', 'success')
                next_page = request.args.get('next')
                if not _is_safe_next(next_page):
                    next_page = url_for('dashboard.index')
                return redirect(next_page)
            # Contraseña correcta pero cuenta sin aprobar/desactivada: mensaje
            # combinado (con activo solo no se distingue pendiente de baja).
            flash('Su cuenta no está activa. Si acaba de registrarse, un '
                  'administrador debe aprobarla. Contacte al administrador '
                  'del sistema.', 'warning')
        else:
            flash('Usuario o contraseña incorrectos.', 'danger')

    return render_template('auth/login.html', form=form)


@auth_bp.route('/registro', methods=['GET', 'POST'])
# Solo el POST consume cuota: abrir el formulario no debe quemar el límite.
@limiter.limit("5/minute", methods=["POST"])
def registro():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    form = RegistroForm()
    if form.validate_on_submit():
        if Usuario.query.filter(
            (Usuario.username == form.username.data) | (Usuario.email == form.email.data)
        ).first():
            flash(DUP_USUARIO, 'danger')
            return render_template('auth/registro.html', form=form)

        # Cuenta sin aprobar: nace desactivada y un admin la activa desde
        # /usuarios. Rol fijo operador — el registro público no elige rol.
        user = Usuario(
            name=form.name.data,
            username=form.username.data,
            email=form.email.data,
            rol='operador',
            activo=False,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        try:
            db.session.flush()  # dup concurrente → IntegrityError dentro del try
            log_audit(user.id, 'INSERT', 'usuarios', user.id, None,
                      {'username': user.username, 'email': user.email,
                       'rol': 'operador', 'activo': False})
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(DUP_USUARIO, 'danger')
            return render_template('auth/registro.html', form=form)

        flash('Cuenta creada correctamente. Un administrador debe aprobarla '
              'antes de que pueda iniciar sesión.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/registro.html', form=form)


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash('Sesión cerrada exitosamente.', 'info')
    return redirect(url_for('auth.login'))
