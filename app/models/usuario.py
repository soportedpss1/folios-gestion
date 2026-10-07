from app.extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app.utils import utcnow


class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(20), nullable=False, default='operador')
    activo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    recepciones = db.relationship('RecepcionFolio', backref='usuario', lazy=True)
    entregas = db.relationship('EntregaFolio', backref='usuario', lazy=True)
    devoluciones = db.relationship('DevolucionFolio', backref='usuario', lazy=True)
    audit_logs = db.relationship('AuditLog', backref='usuario', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.rol == 'admin'

    def is_operador(self):
        return self.rol == 'operador'

    def is_lectura(self):
        return self.rol == 'lectura'

    def can_edit(self):
        return self.rol in ('admin', 'operador')

    def __repr__(self):
        return f'<Usuario {self.username}>'
