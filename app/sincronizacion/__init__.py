import hmac
import logging

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, url_for, flash
from flask_login import login_required, current_user

from app.decorators import permiso_requerido
from app.extensions import csrf, db, limiter
from app.models.sync_config import get_config, proximo_intento, registrar_intento
from app.services.audit import log_audit
from app.services.gsheets import ErrorSincronizacion, sincronizar
from app.sincronizacion.forms import SyncConfigForm
from app.utils import utcnow

logger = logging.getLogger(__name__)

sincronizacion_bp = Blueprint('sincronizacion', __name__, url_prefix='/sincronizacion')


def _config_ok(app_config=None):
    """Credencial y hoja presentes (la existencia del archivo la valida el servicio)."""
    if app_config is None:
        app_config = current_app.config
    return bool(app_config.get('GOOGLE_SERVICE_ACCOUNT_JSON')) and bool(
        app_config.get('GOOGLE_SHEET_ID'))


def _hoja_url():
    sheet_id = current_app.config.get('GOOGLE_SHEET_ID', '')
    return f'https://docs.google.com/spreadsheets/d/{sheet_id}/edit' if sheet_id else None


def _ejecutar_sync(cfg):
    """Corre sincronizar(), persiste estado y audita. Lanza ErrorSincronizacion."""
    try:
        counts = sincronizar()
    except ErrorSincronizacion as exc:
        registrar_intento(cfg, error=str(exc))
        raise
    except Exception:
        logger.exception('Fallo inesperado del sync a Google Sheets')
        registrar_intento(cfg, error='Error inesperado al sincronizar (revise los logs).')
        raise ErrorSincronizacion('Error inesperado al sincronizar. Revise los logs del servidor.') from None
    registrar_intento(cfg, counts=counts)
    # audit_logs.user_id es NOT NULL con FK: sin sesión (worker/API) el estado
    # queda en sync_config; solo el sync manual deja auditoría de usuario.
    if current_user.is_authenticated:
        log_audit(current_user.id, 'SYNC', 'google_sheets', 0, None, counts)
    return counts


def _vista_index(form):
    cfg = get_config()
    ahora = utcnow()
    proximo = proximo_intento(cfg, ahora)
    return render_template(
        'sincronizacion/index.html',
        form=form,
        cfg=cfg,
        config_ok=_config_ok(),
        hoja_url=_hoja_url(),
        proximo=proximo,
        atrasado=bool(proximo and proximo <= ahora),
    )


@sincronizacion_bp.route('/')
@login_required
@permiso_requerido('sincronizacion.usar')
def index():
    return _vista_index(SyncConfigForm(obj=get_config()))


@sincronizacion_bp.route('/config', methods=['POST'])
@login_required
@permiso_requerido('sincronizacion.usar')
def guardar_config():
    form = SyncConfigForm()
    if form.validate_on_submit():
        cfg = get_config()
        cfg.activo = bool(form.activo.data)
        cfg.frecuencia_minutos = form.frecuencia_minutos.data
        db.session.commit()
        flash('Configuración de sincronización guardada.', 'success')
        return redirect(url_for('sincronizacion.index'))

    # Re-render con los errores del form (patrón del resto de módulos)
    return _vista_index(form)


@sincronizacion_bp.route('/sincronizar', methods=['POST'])
@login_required
@permiso_requerido('sincronizacion.usar')
def sincronizar_ahora():
    cfg = get_config()
    try:
        counts = _ejecutar_sync(cfg)
        flash(
            f"Sincronización completada: {counts['agregadas']} agregadas, "
            f"{counts['actualizadas']} actualizadas, {counts['eliminadas']} eliminadas "
            f"(total {counts['total']}).",
            'success',
        )
    except ErrorSincronizacion as exc:
        flash(str(exc), 'danger')
    return redirect(url_for('sincronizacion.index'))


@sincronizacion_bp.route('/api/proxima')
@login_required
@limiter.exempt
def api_proxima():
    """Cuenta atrás del navbar: próximo sync automático (UTC ISO 8601)."""
    cfg = get_config()
    proximo = proximo_intento(cfg, utcnow())
    return jsonify(
        activo=cfg.activo,
        frecuencia_minutos=cfg.frecuencia_minutos,
        proximo=proximo.strftime('%Y-%m-%dT%H:%M:%SZ') if proximo else None,
        atrasado=bool(proximo and proximo <= utcnow()),
    )


@sincronizacion_bp.route('/api/sincronizar', methods=['POST'])
@limiter.exempt
@csrf.exempt
def api_sincronizar():
    """Trigger externo (worker/ops): token en X-Sync-Token, sin sesión."""
    token_configurado = current_app.config.get('SHEET_SYNC_TOKEN', '')
    if not token_configurado:
        return jsonify(error='Token no configurado en el servidor.'), 403
    enviado = request.headers.get('X-Sync-Token', '')
    if not enviado or not hmac.compare_digest(token_configurado, enviado):
        return jsonify(error='Token inválido.'), 403

    cfg = get_config()
    try:
        counts = _ejecutar_sync(cfg)
    except ErrorSincronizacion as exc:
        return jsonify(error=str(exc)), 502
    return jsonify(counts), 200
