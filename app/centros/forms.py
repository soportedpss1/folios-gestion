from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Length


class CentroForm(FlaskForm):
    name = StringField('Nombre', validators=[
        DataRequired(message='Este campo es obligatorio.'),
        Length(min=3, max=255, message='Debe tener entre 3 y 255 caracteres.'),
    ])
    telefono = StringField('Teléfono', validators=[
        Length(max=50, message='No puede superar 50 caracteres.'),
    ])
    direccion = StringField('Dirección', validators=[
        Length(max=255, message='No puede superar 255 caracteres.'),
    ])
    submit = SubmitField('Guardar')


class ImportarCentroForm(FlaskForm):
    archivo = FileField('Archivo Excel (.xlsx)', validators=[
        FileRequired(message='Seleccione un archivo.'),
        FileAllowed(['xlsx'], message='El archivo debe ser un Excel (.xlsx).'),
    ])
    submit = SubmitField('Validar archivo')
