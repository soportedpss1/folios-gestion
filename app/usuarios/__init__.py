from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models.usuario import Usuario
from app.usuarios.forms import UsuarioForm, UsuarioEditForm
from app.services.audit import log_audit
from app.services.mensajes import DUP_USUARIO
from app.services.queries import get_or_404
from app.services.usuarios import ultimo_admin_excluido as _ultimo_admin_excluido
from app.decorators import permiso_requerido

usuarios_bp = Blueprint('usuarios', __name__, url_prefix='/usuarios')


@usuarios_bp.route('/')
@login_required
@permiso_requerido('usuarios.gestionar')
def index():
    usuarios = Usuario.query.order_by(Usuario.username).all()
    return render_template('usuarios/index.html', usuarios=usuarios)


@usuarios_bp.route('/create', methods=['GET', 'POST'])
@login_required
@permiso_requerido('usuarios.gestionar')
def create():
    form = UsuarioForm()
    if form.validate_on_submit():
        # El grant `usuarios.gestionar` habilita la gestión, pero solo un
        # admin puede crear otros admins (los grants suman capacidad de
        # gestión, no de escalada).
        if not current_user.is_admin() and form.rol.data == 'admin':
            flash('Solo un administrador puede crear usuarios administradores.',
                  'danger')
            return render_template('usuarios/create.html', form=form)
        if Usuario.query.filter(
            (Usuario.username == form.username.data) | (Usuario.email == form.email.data)
        ).first():
            flash(DUP_USUARIO, 'danger')
            return render_template('usuarios/create.html', form=form)

        user = Usuario(
            name=form.name.data,
            username=form.username.data,
            email=form.email.data,
            rol=form.rol.data
        )
        user.set_password(form.password.data)
        db.session.add(user)
        try:
            db.session.flush()  # dup concurrente → IntegrityError dentro del try
            log_audit(current_user.id, 'INSERT', 'usuarios', user.id, None,
                      {'username': user.username, 'email': user.email, 'rol': user.rol})
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(DUP_USUARIO, 'danger')
            return render_template('usuarios/create.html', form=form)
        flash('Usuario creado exitosamente.', 'success')
        return redirect(url_for('usuarios.index'))
    return render_template('usuarios/create.html', form=form)


@usuarios_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@permiso_requerido('usuarios.gestionar')
def edit(id):
    user = get_or_404(Usuario, id)
    datos_anteriores = {'username': user.username, 'email': user.email,
                        'rol': user.rol, 'activo': user.activo}
    form = UsuarioEditForm(obj=user)

    if form.validate_on_submit():
        # Sin rol admin: no tocar administradores (resetear su contraseña
        # sería takeover), no autoeditarse (autodesactivación/autorascenso)
        # y no asignar el rol admin.
        if not current_user.is_admin():
            if user.is_admin():
                flash('Solo un administrador puede modificar usuarios '
                      'administradores.', 'danger')
                return redirect(url_for('usuarios.index'))
            if user.id == current_user.id:
                flash('No puede modificar su propio usuario con este '
                      'permiso.', 'danger')
                return redirect(url_for('usuarios.index'))
            if form.rol.data == 'admin':
                flash('Solo un administrador puede asignar el rol '
                      'administrador.', 'danger')
                return render_template('usuarios/edit.html', form=form, user=user)
        if Usuario.query.filter(
            ((Usuario.username == form.username.data) | (Usuario.email == form.email.data)) &
            (Usuario.id != user.id)
        ).first():
            flash(DUP_USUARIO, 'danger')
            return render_template('usuarios/edit.html', form=form, user=user)

        pierde_admin = (user.rol == 'admin' and user.activo) and (
            form.rol.data != 'admin' or not form.activo.data
        )
        if pierde_admin and _ultimo_admin_excluido(user):
            flash('No se puede desactivar ni degradar al último administrador activo.', 'danger')
            return render_template('usuarios/edit.html', form=form, user=user)

        # Refleja el guard de delete: edit no debe permitir desactivarse
        # ni cambiarse de rol a uno mismo (auto-logout/auto-escalada).
        if user.id == current_user.id and (
                form.rol.data != user.rol or not form.activo.data):
            flash('No puede cambiar su propio rol ni desactivarse desde '
                  'la edición.', 'danger')
            return redirect(url_for('usuarios.index'))

        user.name = form.name.data
        user.username = form.username.data
        user.email = form.email.data
        user.rol = form.rol.data
        user.activo = form.activo.data

        if form.password.data:
            user.set_password(form.password.data)

        try:
            log_audit(current_user.id, 'UPDATE', 'usuarios', user.id, datos_anteriores,
                      {'username': user.username, 'email': user.email, 'rol': user.rol,
                       'activo': user.activo,
                       # Un reset desde la UI quedaba indistinguible en /auditoria.
                       'password_changed': bool(form.password.data)})
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(DUP_USUARIO, 'danger')
            return render_template('usuarios/edit.html', form=form, user=user)
        flash('Usuario actualizado exitosamente.', 'success')
        return redirect(url_for('usuarios.index'))
    return render_template('usuarios/edit.html', form=form, user=user)


@usuarios_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@permiso_requerido('usuarios.gestionar')
def delete(id):
    user = get_or_404(Usuario, id)
    if user.id == current_user.id:
        flash('No puede desactivar su propio usuario.', 'danger')
        return redirect(url_for('usuarios.index'))

    if not current_user.is_admin() and user.is_admin():
        flash('Solo un administrador puede desactivar usuarios administradores.',
              'danger')
        return redirect(url_for('usuarios.index'))

    if _ultimo_admin_excluido(user):
        flash('No se puede desactivar al último administrador activo.', 'danger')
        return redirect(url_for('usuarios.index'))

    datos_anteriores = {'username': user.username, 'activo': user.activo}
    user.activo = False
    log_audit(current_user.id, 'DELETE', 'usuarios', user.id, datos_anteriores, None)
    db.session.commit()
    flash('Usuario desactivado exitosamente.', 'success')
    return redirect(url_for('usuarios.index'))
