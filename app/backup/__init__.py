"""Copias de respaldo y restauración (solo admin), en dos pasos.

1. `POST /backup/previsualizar`: sube y analiza el archivo — diff de esquema,
   filas por tabla, tablas que quedarían vacías — sin tocar la base. El JSON
   queda guardado en `staging` con un token que viaja en la sesión.
2. `POST /backup/restaurar`: confirma con el token y aplica el reemplazo
   total en una sola transacción. El token es de un solo uso.

La tolerancia al esquema (columnas nuevas rellenadas, obsoletas ignoradas)
vive en `app.services.backup`; aquí solo se orquesta.
"""

import json

from flask import Blueprint, Response, redirect, render_template, request, session, url_for, flash
from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError

from app.backup import staging
from app.backup.forms import ConfirmarForm, PrevisualizarForm
from app.decorators import admin_required
from app.extensions import db
from app.services.audit import log_audit
from app.services.backup import (
    ErrorRespaldo,
    TABLAS_ORDEN,
    _json_default,
    crear_backup,
    estadisticas,
    previsualizar,
    restaurar_backup,
    version_alembic,
)

backup_bp = Blueprint('backup', __name__, url_prefix='/backup')


def _indice(**contexto):
    return render_template(
        'backup/index.html',
        form=PrevisualizarForm(),
        confirm=ConfirmarForm(),
        stats=estadisticas(),
        tablas=TABLAS_ORDEN,
        alembic=version_alembic(),
        **contexto,
    )


@backup_bp.route('/')
@admin_required
def index():
    return _indice()


@backup_bp.route('/descargar')
@admin_required
def descargar():
    payload = crear_backup()
    blob = json.dumps(payload, ensure_ascii=False, default=_json_default).encode('utf-8')
    total = sum(payload['meta']['tablas'].values())
    log_audit(current_user.id, 'BACKUP', 'backup', 0, None,
              {'tablas': len(payload['meta']['tablas']), 'filas': total})
    db.session.commit()
    nombre = f"respaldo_{payload['meta']['creado'].replace(':', '').replace('T', '_')}.json"
    return Response(blob, headers={
        'Content-Type': 'application/json; charset=utf-8',
        'Content-Disposition': f'attachment; filename="{nombre}"',
        'X-Content-Type-Options': 'nosniff',
    })


@backup_bp.route('/previsualizar', methods=['POST'])
@admin_required
def analizar():
    form = PrevisualizarForm()
    if not form.validate_on_submit():
        for error in form.archivo.errors:
            flash(error, 'danger')
        return redirect(url_for('backup.index'))

    crudo = form.archivo.data.read()
    try:
        payload = json.loads(crudo.decode('utf-8-sig'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        flash('El archivo no es JSON válido.', 'danger')
        return redirect(url_for('backup.index'))

    try:
        analisis = previsualizar(payload)
    except ErrorRespaldo as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('backup.index'))

    token = staging.guardar(crudo)
    session['respaldo'] = token
    return _indice(analisis=analisis, token=token,
                   nombre_archivo=form.archivo.data.filename)


@backup_bp.route('/restaurar', methods=['POST'])
@admin_required
def restaurar():
    form = ConfirmarForm()
    if not form.validate_on_submit():
        for error in form.token.errors:
            flash(error, 'danger')
        return redirect(url_for('backup.index'))

    token = session.pop('respaldo', None)
    if token is None or token != form.token.data:
        flash('El análisis expiró: vuelva a subir el archivo.', 'danger')
        return redirect(url_for('backup.index'))

    crudo = staging.consumir(token)
    if crudo is None:
        flash('El archivo analizado ya no está disponible: vuelva a subirlo.',
              'danger')
        return redirect(url_for('backup.index'))

    try:
        payload = json.loads(crudo.decode('utf-8-sig'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        flash('El archivo no es JSON válido.', 'danger')
        return redirect(url_for('backup.index'))

    try:
        insertadas = restaurar_backup(payload)
    except ErrorRespaldo as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('backup.index'))
    except SQLAlchemyError:
        flash('Error al restaurar: no se aplicó ningún cambio.', 'danger')
        return redirect(url_for('backup.index'))

    total = sum(insertadas.values())
    # Auditoría DESPUÉS del commit de la restauración: sobrevive aunque el
    # respaldo haya reemplazado audit_logs con filas viejas.
    log_audit(current_user.id, 'RESTORE', 'backup', 0, None,
              {'tablas': len(insertadas), 'filas': total})
    db.session.commit()
    flash(f'Respaldo restaurado: {len(insertadas)} tablas, {total} filas.', 'success')
    return redirect(url_for('backup.index'))
