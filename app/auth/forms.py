from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length


class LoginForm(FlaskForm):
    username = StringField('Usuario', validators=[
        DataRequired(message='Ingrese su usuario.'),
        Length(min=3, max=50, message='Debe tener entre 3 y 50 caracteres.'),
    ])
    password = PasswordField('Contraseña', validators=[
        DataRequired(message='Ingrese su contraseña.'),
    ])
    submit = SubmitField('Iniciar Sesión')


class RegistroForm(FlaskForm):
    """Espejo de UsuarioForm de gestión de usuarios, sin rol: el registro
    público siempre crea operadores y la aprobación es del admin."""
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
    submit = SubmitField('Crear Cuenta')
