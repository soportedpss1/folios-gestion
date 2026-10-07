from flask_wtf import FlaskForm
from wtforms import BooleanField, SelectField, SubmitField
from wtforms.validators import DataRequired

from app.services.permisos import PERMISOS


def campo_permiso(clave):
    """Nombre de campo del checkbox para una clave ('usuarios.gestionar' →
    permiso_usuarios_gestionar)."""
    return 'permiso_' + clave.replace('.', '_')


def _construir_form():
    attrs = {
        'rol': SelectField('Rol',
                           choices=[('operador', 'Operador'),
                                    ('admin', 'Administrador'),
                                    ('lectura', 'Lectura')],
                           validators=[DataRequired(message='Seleccione un rol.')]),
        'activo': BooleanField('Activo'),
        'submit': SubmitField('Guardar'),
    }
    for clave, (label, _kind) in PERMISOS.items():
        attrs[campo_permiso(clave)] = BooleanField(label)
    return type('PermisosUsuarioForm', (FlaskForm,), attrs)


PermisosUsuarioForm = _construir_form()
