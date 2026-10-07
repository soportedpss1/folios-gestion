from app.extensions import db
from app.utils import utcnow


class Folio(db.Model):
    __tablename__ = 'folios'
    __table_args__ = (
        # Compuestos para las consultas del dashboard/reportes:
        # WHERE anioCert=? [AND estado=? [AND nulo=?]] y WHERE tipoCert_id=? [AND anioCert=?]
        db.Index('idx_folios_anio_estado', 'anioCert', 'estado', 'nulo'),
        db.Index('idx_folios_tipo_anio', 'tipoCert_id', 'anioCert'),
        db.Index('idx_folio_estado', 'estado'),
        db.UniqueConstraint('rangoId', 'folio', name='uq_folios_rangoId_folio'),
        db.UniqueConstraint('anioCert', 'tipoCert_id', 'folio',
                            name='uq_folios_anio_tipo_folio'),
    )

    id = db.Column(db.Integer, primary_key=True)
    rangoId = db.Column(db.Integer, nullable=False)
    anioCert = db.Column(db.Integer, nullable=False)
    tipoCert_id = db.Column(db.Integer, db.ForeignKey('tipo_certificados.id'), nullable=False)
    folio = db.Column(db.Integer, nullable=False)
    digitado = db.Column(db.Boolean, default=False)
    escaneado = db.Column(db.Boolean, default=False)
    nulo = db.Column(db.Boolean, default=False)
    estado = db.Column(db.String(20), default='disponible')
    createAt = db.Column(db.DateTime, default=utcnow)
    updateAt = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    entrega = db.relationship('EntregaFolio', backref='folio', uselist=False, lazy=True)
    devolucion = db.relationship('DevolucionFolio', backref='folio', uselist=False, lazy=True)

    def __repr__(self):
        return f'<Folio {self.folio}>'

    def to_dict(self):
        return {
            'id': self.id,
            'rangoId': self.rangoId,
            'anioCert': self.anioCert,
            'tipoCert_id': self.tipoCert_id,
            'tipoCert_nombre': self.tipo_cert.name if self.tipo_cert else None,
            'folio': self.folio,
            'digitado': self.digitado,
            'escaneado': self.escaneado,
            'nulo': self.nulo,
            'estado': self.estado,
            'createAt': self.createAt.isoformat() if self.createAt else None,
            'updateAt': self.updateAt.isoformat() if self.updateAt else None,
        }
