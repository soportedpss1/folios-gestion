from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app.decorators import admin_required
from app.extensions import db
from app.models.permiso_usuario import PermisoUsuario
from app.models.usuario import Usuario
from app.permisos.forms import PermisosUsuarioForm, campo_permiso
from app.services.audit import log_audit
from app.services.permisos import PERMISOS, grants_de
from app.services.queries import get_or_404
from app.services.usuarios import ultimo_admin_excluido

permisos_bp = Blueprint('permisos', __name__, url_prefix='/permisos')


@permisos_bp.route('/')
@login_required
@admin_required
def index():
    usuarios = Usuario.query.order_by(Usuario.username).all()
    return render_template('permisos/index.html', usuarios=usuarios)


@permisos_bp.route('/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def gestionar(id):
    user = get_or_404(Usuario, id)
    grants_actuales = grants_de(user)
    form = PermisosUsuarioForm()

    if request.method == 'GET':
        form.rol.data = user.rol
        form.activo.data = user.activo
        for clave in PERMISOS:
            getattr(form, campo_permiso(clave)).data = clave in grants_actuales

    permisos_form = [(clave, etiqueta) for clave, (etiqueta, _k) in PERMISOS.items()]

    if form.validate_on_submit():
        pierde_admin = (user.rol == 'admin' and user.activo) and (
            form.rol.data != 'admin' or not form.activo.data
        )
        if pierde_admin and ultimo_admin_excluido(user):
            flash('No se puede desactivar ni degradar al último administrador activo.', 'danger')
            return render_template('permisos/edit.html', form=form, user=user,
                                   permisos_form=permisos_form,
                                   campo=campo_permiso)

        nuevos = {clave for clave in PERMISOS
                  if getattr(form, campo_permiso(clave)).data}
        datos_anteriores = {'rol': user.rol, 'activo': user.activo,
                            'grants': sorted(grants_actuales)}

        user.rol = form.rol.data
        user.activo = form.activo.data
        for clave in nuevos - grants_actuales:
            db.session.add(PermisoUsuario(user_id=user.id, permiso=clave))
        for clave in grants_actuales - nuevos:
            PermisoUsuario.query.filter_by(user_id=user.id, permiso=clave).delete()

        log_audit(current_user.id, 'UPDATE', 'permiso_usuarios', user.id,
                  datos_anteriores,
                  {'rol': user.rol, 'activo': user.activo,
                   'grants': sorted(nuevos)})
        db.session.commit()
        flash(f'Permisos de {user.username} actualizados.', 'success')
        return redirect(url_for('permisos.index'))

    return render_template('permisos/edit.html', form=form, user=user,
                           permisos_form=permisos_form, campo=campo_permiso)
