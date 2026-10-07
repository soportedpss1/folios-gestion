from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import SelectMultipleField, DateField, SelectField, SubmitField
from wtforms.validators import DataRequired
from datetime import date

from app.utils import coerce_id_opcional


class DevolucionForm(FlaskForm):
    folio_ids = SelectMultipleField('Folios', coerce=int, validators=[
        DataRequired(message='Seleccione al menos un folio.'),
    ])
    fechaDevolucion = DateField('Fecha de Devolución', validators=[
        DataRequired(message='Seleccione una fecha.'),
    ], default=date.today)
    centroId = SelectField('Centro de Salud', coerce=coerce_id_opcional,
                           validators=[DataRequired(message='Seleccione el centro de salud.')])
    submit = SubmitField('Registrar Devolución')


class DevolucionEditForm(FlaskForm):
    folio_id = SelectField('Folio', coerce=int, validators=[
        DataRequired(message='Seleccione un folio.'),
    ])
    fechaDevolucion = DateField('Fecha de Devolución', validators=[
        DataRequired(message='Seleccione una fecha.'),
    ])
    centroId = SelectField('Centro de Salud', coerce=int,
                           validators=[DataRequired(message='Seleccione el centro de salud.')])
    submit = SubmitField('Guardar')


class ImportarDevolucionForm(FlaskForm):
    archivo = FileField('Archivo Excel (.xlsx)', validators=[
        FileRequired(message='Seleccione un archivo.'),
        FileAllowed(['xlsx'], message='El archivo debe ser un Excel (.xlsx).'),
    ])
    fechaDevolucion = DateField('Fecha de Devolución', validators=[
        DataRequired(message='Seleccione una fecha.'),
    ], default=date.today)
    centroId = SelectField('Centro de Salud', coerce=coerce_id_opcional,
                           validators=[DataRequired(message='Seleccione el centro de salud.')])
    submit = SubmitField('Validar archivo')
