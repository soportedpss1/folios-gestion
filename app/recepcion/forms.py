from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import DateField, IntegerField, SelectField, SubmitField
from wtforms.validators import DataRequired, NumberRange
from datetime import date

from app.services.mensajes import msg_solape

# Tope de folios por recepción: sin él un solo POST puede pedir un rango de
# millones y dejar el servidor insertando filas durante minutos.
MAX_FOLIOS_POR_RECEPCION = 10000


def detectar_solape(anioCert, tipoCert_id, folioInicial, folioFinal,
                    excluir_id=None):
    """Devuelve el rango existente que se cruza con estos valores, o None.

    `excluir_id` ignora una recepción propia: al editar, su rango actual se
    cruza siempre consigo mismo.
    """
    from app.models.recepcion_folio import RecepcionFolio
    query = RecepcionFolio.query.filter(
        RecepcionFolio.anioCert == anioCert,
        RecepcionFolio.tipoCert_id == tipoCert_id,
        RecepcionFolio.folioInicial <= folioFinal,
        RecepcionFolio.folioFinal >= folioInicial,
    )
    if excluir_id is not None:
        query = query.filter(RecepcionFolio.id != excluir_id)
    return query.first()


class RecepcionForm(FlaskForm):
    fecha = DateField('Fecha de Recepción', validators=[
        DataRequired(message='Seleccione una fecha.'),
    ], default=date.today)
    anioCert = IntegerField('Año del Certificado', validators=[
        DataRequired(message='Este campo es obligatorio.'),
        NumberRange(min=2000, max=2100, message='Ingrese un año entre 2000 y 2100.'),
    ])
    tipoCert = SelectField('Tipo de Certificado', coerce=int, validators=[
        DataRequired(message='Seleccione un tipo de certificado.'),
    ])
    folioInicial = IntegerField('Folio Inicial', validators=[
        DataRequired(message='Este campo es obligatorio.'),
        NumberRange(min=1, message='Ingrese un número mayor o igual a 1.'),
    ])
    folioFinal = IntegerField('Folio Final', validators=[
        DataRequired(message='Este campo es obligatorio.'),
        NumberRange(min=1, message='Ingrese un número mayor o igual a 1.'),
    ])
    submit = SubmitField('Registrar Recepción')
    # Las ediciones lo sobrescriben por instancia: su propio rango no cuenta
    # como solape.
    excluir_id = None

    @property
    def total_folios(self):
        if self.folioInicial.data is None or self.folioFinal.data is None:
            return None
        return self.folioFinal.data - self.folioInicial.data + 1

    def validate_on_submit(self):
        if not super().validate_on_submit():
            return False
        if self.folioFinal.data < self.folioInicial.data:
            self.folioFinal.errors.append('El folio final debe ser mayor o igual al folio inicial.')
            return False

        total = self.total_folios
        if total > MAX_FOLIOS_POR_RECEPCION:
            self.folioFinal.errors.append(
                f'El rango no puede superar {MAX_FOLIOS_POR_RECEPCION} folios '
                f'(pidió {total}). Divida la recepción en varias.'
            )
            return False

        solape = detectar_solape(self.anioCert.data, self.tipoCert.data,
                                 self.folioInicial.data, self.folioFinal.data,
                                 excluir_id=self.excluir_id)
        if solape:
            self.folioInicial.errors.append(msg_solape(
                self.folioInicial.data, self.folioFinal.data,
                solape.folioInicial, solape.folioFinal,
            ))
            return False
        return True


class EditarRecepcionForm(RecepcionForm):
    """RecepcionForm + responsable. La vista carga los choices de tipoCert y
    usuario (create no tiene usuario, por eso no vive en la clase base)."""
    usuario = SelectField('Responsable', coerce=int, validators=[
        DataRequired(message='Seleccione un responsable.'),
    ])
    submit = SubmitField('Guardar cambios')


class ImportarRecepcionForm(FlaskForm):
    archivo = FileField('Archivo Excel (.xlsx)', validators=[
        FileRequired(message='Seleccione un archivo.'),
        FileAllowed(['xlsx'], message='El archivo debe ser un Excel (.xlsx).'),
    ])
    submit = SubmitField('Validar archivo')
