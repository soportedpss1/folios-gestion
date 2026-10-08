from app.extensions import db
from app.utils import utcnow


class FolioComentario(db.Model):
    """Anotación de trabajo sobre un folio (historial con autor y fecha)."""
    __tablename__ = 'folio_comentarios'

    id = db.Column(db.Integer, primary_key=True)
    folio_id = db.Column(db.Integer, db.ForeignKey('folios.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False, index=True)
    texto = db.Column(db.String(1000), nullable=False)
    createAt = db.Column(db.DateTime, default=utcnow)
    # Cambia solo al editar el comentario: el detalle lo usa para marcar "Editado".
    updateAt = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    usuario = db.relationship('Usuario', backref=db.backref('comentarios', lazy='dynamic'))

    def __repr__(self):
        return f'<FolioComentario {self.id} folio={self.folio_id}>'
