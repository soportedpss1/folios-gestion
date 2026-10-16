from app.extensions import db
from app.utils import utcnow


class TransferenciaFolio(db.Model):
    """Transferencia de un folio entregado de un centro a otro.

    Inmutable: registra el centro de origen (el de la entrega al momento del
    movimiento), el destino, el motivo obligatorio y el usuario que la ejecutó.
    """
    __tablename__ = 'transferencia_folios'
    __table_args__ = (
        db.Index('idx_transferencia_origen', 'centroOrigenId'),
        db.Index('idx_transferencia_destino', 'centroDestinoId'),
        db.Index('idx_transferencia_userId', 'userId'),
    )

    id = db.Column(db.Integer, primary_key=True)
    folio_id = db.Column(db.Integer, db.ForeignKey('folios.id'), nullable=False, index=True)
    centroOrigenId = db.Column(db.Integer, db.ForeignKey('centros.id'), nullable=False)
    centroDestinoId = db.Column(db.Integer, db.ForeignKey('centros.id'), nullable=False)
    userId = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    motivo = db.Column(db.String(500), nullable=False)
    fecha = db.Column(db.Date, nullable=False, default=lambda: utcnow().date())
    created_at = db.Column(db.DateTime, default=utcnow)

    folio = db.relationship('Folio')
    centro_origen = db.relationship('Centro', foreign_keys=[centroOrigenId])
    centro_destino = db.relationship('Centro', foreign_keys=[centroDestinoId])
    usuario = db.relationship('Usuario')

    def __repr__(self):
        return (f'<TransferenciaFolio {self.id} folio={self.folio_id} '
                f'{self.centroOrigenId}->{self.centroDestinoId}>')

    def to_dict(self):
        return {
            'id': self.id,
            'folio_id': self.folio_id,
            'folio_numero': self.folio.folio if self.folio else None,
            'centroOrigenId': self.centroOrigenId,
            'centro_origen_nombre': self.centro_origen.name if self.centro_origen else None,
            'centroDestinoId': self.centroDestinoId,
            'centro_destino_nombre': self.centro_destino.name if self.centro_destino else None,
            'userId': self.userId,
            'usuario_nombre': self.usuario.username if self.usuario else None,
            'motivo': self.motivo,
            'fecha': self.fecha.isoformat() if self.fecha else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
