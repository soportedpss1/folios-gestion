from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length


class LoginForm(FlaskForm):
    username = StringField('Usuario', validators=[
        DataRequired(message='Ingrese su usuario.'),
        Length(min=3, max=50, message='Debe tener entre 3 y 50 caracteres.'),
    ])
    password = PasswordField('Contraseña', validators=[
        DataRequired(message='Ingrese su contraseña.'),
    ])
    submit = SubmitField('Iniciar Sesión')
