"""Textos de notificación compartidos entre módulos.

Un solo origen para mensajes que aparecen en varios flujos (duplicados de
integridad, solape de recepciones) — evita drift entre copias.
"""

DUP_TIPO_CERT = 'Ya existe un tipo de certificado con ese nombre.'
DUP_USUARIO = 'Ese nombre de usuario o correo ya está en uso.'
REFRESQUE_INTENTE = 'Refresque la lista e intente de nuevo.'
INTENTE_DE_NUEVO = 'Intente de nuevo.'


def msg_solape(ini, fin, existente_ini, existente_fin):
    """Rango nuevo que se cruza con una recepción existente."""
    return (
        f'El rango {ini}-{fin} se solapa con la recepción existente '
        f'{existente_ini}-{existente_fin} (mismo año y tipo de certificado).'
    )
