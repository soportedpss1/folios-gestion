"""Campos de formulario compartidos entre módulos."""

from datetime import date

from wtforms import DateField, widgets
from wtforms.validators import ValidationError


class FlatpickrInput(widgets.TextInput):
    """Input de texto con flatpickr: el formato de presentación lo controla
    la librería (d/m/Y, siempre dd/mm/aaaa), no el locale del navegador."""

    def __call__(self, field, **kwargs):
        clases = kwargs.get('class', '').split()
        if 'flatpickr' not in clases:
            clases.append('flatpickr')
        kwargs['class'] = ' '.join(clases)
        kwargs.setdefault('placeholder', 'dd/mm/aaaa')
        kwargs.setdefault('autocomplete', 'off')
        return super().__call__(field, **kwargs)


class FechaLatinaField(DateField):
    """DateField que emite dd/mm/aaaa y acepta dd/mm/aaaa o ISO.

    El formato es una lista (no tupla): DateTimeField.__init__ solo desempaqueta
    cadenas — una tupla quedaría envuelta entera como un solo formato.
    ISO se conserva como fallback: marcadores de URL, importaciones y tests
    que ya lo envían.
    """
    widget = FlatpickrInput()

    def __init__(self, label=None, validators=None, **kwargs):
        super().__init__(label, validators,
                         format=['%d/%m/%Y', '%Y-%m-%d'], **kwargs)


class NoFutura:
    """Validator que rechaza fechas posteriores al día actual.

    `date.today()` es hora local del sistema (honra TZ): el límite de la
    interfaz es el día del usuario, no el UTC. Hoy se acepta; mañana no.
    """

    def __init__(self, message='La fecha no puede ser posterior a hoy.'):
        self.message = message

    def __call__(self, form, field):
        if field.data is not None and field.data > date.today():
            raise ValidationError(self.message)
