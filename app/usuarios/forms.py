from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo, Optional


class UsuarioForm(FlaskForm):
    name = StringField('Nombre completo', validators=[
        DataRequired(message='Este campo es obligatorio.'),
        Length(min=3, max=255, message='Debe tener entre 3 y 255 caracteres.'),
    ])
    username = StringField('Usuario', validators=[
        DataRequired(message='Este campo es obligatorio.'),
        Length(min=3, max=50, message='Debe tener entre 3 y 50 caracteres.'),
    ])
    email = StringField('Email', validators=[
        DataRequired(message='Este campo es obligatorio.'),
        Email(message='Introduzca un correo electrónico válido.'),
        Length(max=100, message='No puede superar 100 caracteres.'),
    ])
    password = PasswordField('Contraseña', validators=[
        DataRequired(message='Este campo es obligatorio.'),
        Length(min=6, message='Debe tener al menos 6 caracteres.'),
    ])
    confirm_password = PasswordField('Confirmar contraseña', validators=[
        DataRequired(message='Este campo es obligatorio.'),
        EqualTo('password', message='Las contraseñas no coinciden.'),
    ])
    rol = SelectField('Rol', choices=[('operador', 'Operador'), ('admin', 'Administrador'), ('lectura', 'Lectura')],
                      validators=[DataRequired(message='Seleccione un rol.')])
    submit = SubmitField('Guardar')


class UsuarioEditForm(FlaskForm):
    name = StringField('Nombre completo', validators=[
        DataRequired(message='Este campo es obligatorio.'),
        Length(min=3, max=255, message='Debe tener entre 3 y 255 caracteres.'),
    ])
    username = StringField('Usuario', validators=[
        DataRequired(message='Este campo es obligatorio.'),
        Length(min=3, max=50, message='Debe tener entre 3 y 50 caracteres.'),
    ])
    email = StringField('Email', validators=[
        DataRequired(message='Este campo es obligatorio.'),
        Email(message='Introduzca un correo electrónico válido.'),
        Length(max=100, message='No puede superar 100 caracteres.'),
    ])
    password = PasswordField('Nueva contraseña (dejar vacío para mantener)', validators=[
        Optional(),
        Length(min=6, message='Debe tener al menos 6 caracteres.'),
    ])
    rol = SelectField('Rol', choices=[('operador', 'Operador'), ('admin', 'Administrador'), ('lectura', 'Lectura')],
                      validators=[DataRequired(message='Seleccione un rol.')])
    activo = BooleanField('Activo')
    submit = SubmitField('Guardar')
