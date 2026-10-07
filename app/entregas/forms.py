from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import SelectField, SelectMultipleField, DateField, SubmitField
from wtforms.validators import DataRequired

from app.utils import coerce_id_opcional


class EntregaCreateForm(FlaskForm):
    folio_ids = SelectMultipleField('Folios', coerce=int, validators=[
        DataRequired(message='Seleccione al menos un folio.'),
    ])
    fechaEntrega = DateField('Fecha de Entrega', validators=[
        DataRequired(message='Seleccione una fecha.'),
    ])
    centroId = SelectField('Centro de Salud', coerce=coerce_id_opcional,
                           validators=[DataRequired(message='Seleccione el centro de salud.')])
    submit = SubmitField('Registrar Entrega')


class EntregaEditForm(FlaskForm):
    folio_id = SelectField('Folio', coerce=int, validators=[
        DataRequired(message='Seleccione un folio.'),
    ])
    fechaEntrega = DateField('Fecha de Entrega', validators=[
        DataRequired(message='Seleccione una fecha.'),
    ])
    centroId = SelectField('Centro de Salud', coerce=int,
                           validators=[DataRequired(message='Seleccione el centro de salud.')])
    submit = SubmitField('Guardar')


class ImportarEntregaForm(FlaskForm):
    archivo = FileField('Archivo Excel (.xlsx)', validators=[
        FileRequired(message='Seleccione un archivo.'),
        FileAllowed(['xlsx'], message='El archivo debe ser un Excel (.xlsx).'),
    ])
    fechaEntrega = DateField('Fecha de Entrega', validators=[
        DataRequired(message='Seleccione una fecha.'),
    ])
    centroId = SelectField('Centro de Salud', coerce=coerce_id_opcional,
                           validators=[DataRequired(message='Seleccione el centro de salud.')])
    submit = SubmitField('Validar archivo')
