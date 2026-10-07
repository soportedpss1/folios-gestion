from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import HiddenField, SubmitField
from wtforms.validators import DataRequired


class PrevisualizarForm(FlaskForm):
    """Paso 1: subir el archivo y analizarlo sin tocar la base."""

    archivo = FileField('Archivo de respaldo (.json)', validators=[
        FileRequired(message='Seleccione un archivo de respaldo.'),
        FileAllowed(['json'], message='El archivo debe ser un JSON (.json).'),
    ])
    submit = SubmitField('Analizar archivo')


class ConfirmarForm(FlaskForm):
    """Paso 2: confirmar con el token del análisis previo."""

    token = HiddenField('Token', validators=[
        DataRequired(message='Vuelva a analizar el archivo antes de restaurar.'),
    ])
    submit = SubmitField('Restaurar')
