from app.extensions import db
from app.utils import utcnow


class RecepcionFolio(db.Model):
    __tablename__ = 'recepcion_folios'
    __table_args__ = (
        db.Index('idx_recepcion_anioCert', 'anioCert'),
        db.Index('idx_recepcion_tipoCert_id', 'tipoCert_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False)
    anioCert = db.Column(db.Integer, nullable=False)
    tipoCert_id = db.Column(db.Integer, db.ForeignKey('tipo_certificados.id'), nullable=False)
    folioInicial = db.Column(db.Integer, nullable=False)
    folioFinal = db.Column(db.Integer, nullable=False)
    rangoId = db.Column(db.Integer, unique=True, nullable=False)
    userId = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    def __repr__(self):
        return f'<RecepcionFolio rango {self.folioInicial}-{self.folioFinal}>'

    def to_dict(self):
        return {
            'id': self.id,
            'fecha': self.fecha.isoformat() if self.fecha else None,
            'anioCert': self.anioCert,
            'tipoCert_id': self.tipoCert_id,
            'tipoCert_nombre': self.tipo_cert.name if self.tipo_cert else None,
            'folioInicial': self.folioInicial,
            'folioFinal': self.folioFinal,
            'rangoId': self.rangoId,
            'userId': self.userId,
            'usuario_nombre': self.usuario.username if self.usuario else None,
            'total_folios': self.folioFinal - self.folioInicial + 1,
        }
