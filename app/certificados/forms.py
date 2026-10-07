from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Length, Regexp


class TipoCertificadoForm(FlaskForm):
    name = StringField('Nombre', validators=[
        DataRequired(message='Este campo es obligatorio.'),
        Length(min=3, max=255, message='Debe tener entre 3 y 255 caracteres.'),
    ])
    descripcion = TextAreaField('Descripción')
    color = StringField('Color de Etiqueta', default='#0D6EFD',
        validators=[Regexp(r'^#[0-9A-Fa-f]{6}$', message='Formato de color inválido. Use #RRGGBB.')])
    submit = SubmitField('Guardar')
