from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length


class ImportarFolioForm(FlaskForm):
    archivo = FileField('Archivo Excel (.xlsx)', validators=[
        FileRequired(message='Seleccione un archivo.'),
        FileAllowed(['xlsx'], message='El archivo debe ser un Excel (.xlsx).'),
    ])
    submit = SubmitField('Validar archivo')


class ComentarioFolioForm(FlaskForm):
    texto = TextAreaField('Comentario', validators=[
        DataRequired(message='Escriba un comentario.'),
        Length(max=1000, message='Máximo 1000 caracteres.'),
    ])
    submit = SubmitField('Añadir comentario')
