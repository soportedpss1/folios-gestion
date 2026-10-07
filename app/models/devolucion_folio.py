from app.extensions import db
from app.utils import utcnow


class DevolucionFolio(db.Model):
    __tablename__ = 'devolucion_folios'
    __table_args__ = (
        db.Index('idx_devolucion_folio_id', 'folio_id'),
        db.Index('idx_devolucion_centroId', 'centroId'),
        db.Index('idx_devolucion_userId', 'userId'),
        db.UniqueConstraint('folio_id', name='uq_devolucion_folios_folio_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    folio_id = db.Column(db.Integer, db.ForeignKey('folios.id'), nullable=False)
    fechaDevolucion = db.Column(db.Date, nullable=False)
    centroId = db.Column(db.Integer, db.ForeignKey('centros.id'), nullable=False)
    userId = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    def __repr__(self):
        return f'<DevolucionFolio folio_id={self.folio_id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'folio_id': self.folio_id,
            'folio_numero': self.folio.folio if self.folio else None,
            'fechaDevolucion': self.fechaDevolucion.isoformat() if self.fechaDevolucion else None,
            'centroId': self.centroId,
            'centro_nombre': self.centro.name if self.centro else None,
            'userId': self.userId,
            'usuario_nombre': self.usuario.username if self.usuario else None,
        }
