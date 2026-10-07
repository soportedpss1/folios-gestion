from flask_wtf import FlaskForm
from wtforms import BooleanField, IntegerField, SubmitField
from wtforms.validators import DataRequired, NumberRange

from app.models.sync_config import FRECUENCIA_MAX_MINUTOS, FRECUENCIA_MIN_MINUTOS


class SyncConfigForm(FlaskForm):
    activo = BooleanField('Sincronización automática activa')
    frecuencia_minutos = IntegerField('Frecuencia (minutos)', validators=[
        DataRequired(message='Este campo es obligatorio.'),
        NumberRange(
            min=FRECUENCIA_MIN_MINUTOS, max=FRECUENCIA_MAX_MINUTOS,
            message=f'Ingrese un valor entre {FRECUENCIA_MIN_MINUTOS} y {FRECUENCIA_MAX_MINUTOS} minutos.',
        ),
    ])
    submit = SubmitField('Guardar')
