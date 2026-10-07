from app.extensions import db
from app.utils import utcnow


class TipoCertificado(db.Model):
    __tablename__ = 'tipo_certificados'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    descripcion = db.Column(db.Text)
    color = db.Column(db.String(7), default='info')
    activo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    recepciones = db.relationship('RecepcionFolio', backref='tipo_cert', lazy=True)
    folios = db.relationship('Folio', backref='tipo_cert', lazy=True)

    def __repr__(self):
        return f'<TipoCertificado {self.name}>'

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'descripcion': self.descripcion,
            'color': self.color,
            'activo': self.activo,
        }
