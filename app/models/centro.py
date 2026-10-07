from app.extensions import db
from app.utils import utcnow


class Centro(db.Model):
    __tablename__ = 'centros'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    telefono = db.Column(db.String(50))
    direccion = db.Column(db.String(255))
    activo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    entregas = db.relationship('EntregaFolio', backref='centro', lazy=True)
    devoluciones = db.relationship('DevolucionFolio', backref='centro', lazy=True)

    def __repr__(self):
        return f'<Centro {self.name}>'

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'telefono': self.telefono,
            'direccion': self.direccion,
            'activo': self.activo,
        }
