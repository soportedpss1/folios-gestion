from app.extensions import db


class PermisoUsuario(db.Model):
    """Grant granular: suma capacidades al rol, nunca las quita."""

    __tablename__ = 'permiso_usuarios'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'permiso', name='uq_permiso_usuario'),
        db.Index('idx_permiso_usuario_user', 'user_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer,
                        db.ForeignKey('usuarios.id', ondelete='CASCADE'),
                        nullable=False)
    permiso = db.Column(db.String(50), nullable=False)

    usuario = db.relationship('Usuario', backref=db.backref(
        'permisos_grants', lazy=True, cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<PermisoUsuario {self.permiso} user={self.user_id}>'

    def to_dict(self):
        return {'user_id': self.user_id, 'permiso': self.permiso}
