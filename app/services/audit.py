"""Registro de auditoría (antes vivía en app/centros/__init__.py)."""

from app.extensions import db
from app.models.audit_log import AuditLog


def log_audit(user_id, accion, tabla, registro_id, datos_anteriores=None, datos_nuevos=None):
    from flask import request
    log = AuditLog(
        user_id=user_id,
        accion=accion,
        tabla=tabla,
        registro_id=registro_id,
        datos_anteriores=datos_anteriores,
        datos_nuevos=datos_nuevos,
        ip_address=request.remote_addr
    )
    db.session.add(log)
