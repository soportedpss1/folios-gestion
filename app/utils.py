"""Utilidades generales sin dependencias de Flask."""

from datetime import datetime, timezone


def utcnow():
    """UTC naive: compatible con las columnas DateTime sin timezone y sin
    la DeprecationWarning de datetime.utcnow() (Python 3.12+)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def a_hora_local(dt):
    """DateTime UTC naive → hora local del sistema (honra la variable TZ).

    Las columnas created_at/updateAt/fecha se guardan en UTC; renderizarlas
    tal cual mostraba la hora corrida respecto a la hora local.
    """
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)


def coerce_id_opcional(valor):
    """Coerce para SelectField de id con opción placeholder: '' -> None.

    `coerce=int` con un choice de value '' lanza ValueError (500) al renderizar
    y al validar: `_choices_generator` hace `self.coerce(value)` sobre el valor
    del choice, no sobre el dato del form. Con esto, '' llega como None y el
    DataRequired del campo emite su mensaje en español.
    """
    if valor in (None, ''):
        return None
    return int(valor)


def plural(n, singular, plural=None):
    """1 → singular, distinto de 1 → plural.

    `plural` opcional para palabras irregulares (ej. 'registrada', 'registradas').
    """
    if n == 1:
        return singular
    return plural if plural is not None else singular + 's'
