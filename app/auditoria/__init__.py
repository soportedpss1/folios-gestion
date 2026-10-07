from flask import Blueprint, render_template, request
from flask_login import login_required
from app.models.audit_log import AuditLog
from app.models.usuario import Usuario
from app.decorators import permiso_requerido

auditoria_bp = Blueprint('auditoria', __name__, url_prefix='/auditoria')


@auditoria_bp.route('/')
@login_required
@permiso_requerido('auditoria.ver')
def index():
    user_id = request.args.get('user_id', type=int)
    accion = request.args.get('accion')
    tabla = request.args.get('tabla')

    query = AuditLog.query

    if user_id:
        query = query.filter_by(user_id=user_id)
    if accion:
        query = query.filter_by(accion=accion)
    if tabla:
        query = query.filter_by(tabla=tabla)

    page = request.args.get('page', 1, type=int)
    pagination = query.order_by(AuditLog.fecha.desc()).paginate(page=page, per_page=50, error_out=False)

    usuarios = Usuario.query.order_by(Usuario.username).all()

    return render_template('auditoria/index.html',
        logs=pagination.items,
        pagination=pagination,
        usuarios=usuarios,
        current_user_id=user_id,
        current_accion=accion,
        current_tabla=tabla
    )
