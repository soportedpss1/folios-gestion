from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileRequired, MultipleFileField
from wtforms import SelectField, SubmitField
from wtforms.validators import DataRequired


class EscaneoForm(FlaskForm):
    anio = SelectField('Año', coerce=int, validators=[
        DataRequired(message='Seleccione un año.'),
    ])
    archivos = MultipleFileField('Archivos JPG', validators=[
        FileRequired(message='Seleccione al menos un archivo.'),
        FileAllowed(['jpg', 'jpeg'],
                    message='Solo se permiten archivos .jpg o .jpeg.'),
    ])
    submit = SubmitField('Subir escaneos')
