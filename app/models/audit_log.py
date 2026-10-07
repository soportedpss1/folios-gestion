from app.extensions import db
from app.utils import utcnow


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    __table_args__ = (
        db.Index('idx_audit_fecha', 'fecha'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    accion = db.Column(db.String(20), nullable=False)
    tabla = db.Column(db.String(50), nullable=False)
    registro_id = db.Column(db.Integer, nullable=False)
    datos_anteriores = db.Column(db.JSON)
    datos_nuevos = db.Column(db.JSON)
    fecha = db.Column(db.DateTime, default=utcnow)
    ip_address = db.Column(db.String(45))

    def __repr__(self):
        return f'<AuditLog {self.accion} on {self.tabla}>'

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'usuario_nombre': self.usuario.username if self.usuario else None,
            'accion': self.accion,
            'tabla': self.tabla,
            'registro_id': self.registro_id,
            'datos_anteriores': self.datos_anteriores,
            'datos_nuevos': self.datos_nuevos,
            'fecha': self.fecha.isoformat() if self.fecha else None,
            'ip_address': self.ip_address,
        }
