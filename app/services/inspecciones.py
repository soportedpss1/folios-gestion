"""Chequeos de coherencia de datos para el módulo de inspecciones.

Cada chequeo devuelve una query paginable (columnas con nombre, `order_by`
incluido — la paginación sin orden estable solapa páginas) y un `formatear`
que convierte cada fila en el dict de display `{titulo, detalle, modulo,
registro_id}`. Solo lectura: la corrección ocurre en la pantalla de edición
del módulo dueño (URLS_CORREGIR).
"""

from collections import OrderedDict
from datetime import date

from sqlalchemy import literal, or_

from app.extensions import db
from app.models.recepcion_folio import RecepcionFolio
from app.models.entrega_folio import EntregaFolio
from app.models.devolucion_folio import DevolucionFolio
from app.models.folio import Folio

# modulo → endpoint de la pantalla de corrección (lo consume la ruta detalle).
URLS_CORREGIR = {
    'recepcion': 'recepcion.edit',
    'entregas': 'entregas.edit',
    'devoluciones': 'devoluciones.edit',
    'folios': 'folios.details',
}

NOMBRES_MODULO = {
    'recepcion': 'Recepción',
    'entregas': 'Entrega',
    'devoluciones': 'Devolución',
}


def dmy(f):
    """Fecha Date → dd/mm/aaaa ('-' si falta)."""
    return f.strftime('%d/%m/%Y') if f else '-'


def entrega_antes_recepcion():
    """Entregas cuya fecha es anterior a la recepción que creó el folio."""
    return (
        db.session.query(
            EntregaFolio.id.label('registro_id'),
            EntregaFolio.fechaEntrega,
            RecepcionFolio.fecha,
            Folio.folio,
        )
        .join(Folio, EntregaFolio.folio_id == Folio.id)
        .join(RecepcionFolio, Folio.rangoId == RecepcionFolio.rangoId)
        .filter(EntregaFolio.fechaEntrega < RecepcionFolio.fecha)
        .order_by(EntregaFolio.id)
    )


def formatear_entrega_antes_recepcion(row):
    return {
        'titulo': f'Entrega #{row.registro_id} · Folio {row.folio}',
        'detalle': (f'Entrega {dmy(row.fechaEntrega)} anterior a la recepción '
                    f'{dmy(row.fecha)}'),
        'modulo': 'entregas',
        'registro_id': row.registro_id,
    }


def devolucion_antes_entrega():
    """Devoluciones cuya fecha es anterior a la entrega del mismo folio."""
    return (
        db.session.query(
            DevolucionFolio.id.label('registro_id'),
            DevolucionFolio.fechaDevolucion,
            EntregaFolio.fechaEntrega,
            Folio.folio,
        )
        .join(EntregaFolio, DevolucionFolio.folio_id == EntregaFolio.folio_id)
        .join(Folio, DevolucionFolio.folio_id == Folio.id)
        .filter(DevolucionFolio.fechaDevolucion < EntregaFolio.fechaEntrega)
        .order_by(DevolucionFolio.id)
    )


def formatear_devolucion_antes_entrega(row):
    return {
        'titulo': f'Devolución #{row.registro_id} · Folio {row.folio}',
        'detalle': (f'Devolución {dmy(row.fechaDevolucion)} anterior a la '
                    f'entrega {dmy(row.fechaEntrega)}'),
        'modulo': 'devoluciones',
        'registro_id': row.registro_id,
    }


def fechas_futuras():
    """Registros con fecha posterior a hoy en las tres tablas de movimiento.

    UNION de columnas crudas: no hay CONCAT portable entre SQLite y MySQL;
    el contexto del hallazgo lo da el link de corrección.
    """
    hoy = date.today()
    rec = db.session.query(
        literal('recepcion').label('modulo'),
        RecepcionFolio.id.label('registro_id'),
        RecepcionFolio.fecha.label('fecha'),
    ).filter(RecepcionFolio.fecha > hoy)
    ent = db.session.query(
        literal('entregas').label('modulo'),
        EntregaFolio.id.label('registro_id'),
        EntregaFolio.fechaEntrega.label('fecha'),
    ).filter(EntregaFolio.fechaEntrega > hoy)
    dev = db.session.query(
        literal('devoluciones').label('modulo'),
        DevolucionFolio.id.label('registro_id'),
        DevolucionFolio.fechaDevolucion.label('fecha'),
    ).filter(DevolucionFolio.fechaDevolucion > hoy)
    return rec.union_all(ent, dev).order_by('modulo', 'registro_id')


def formatear_fechas_futuras(row):
    return {
        'titulo': f'{NOMBRES_MODULO[row.modulo]} #{row.registro_id}',
        'detalle': f'Fecha futura: {dmy(row.fecha)}',
        'modulo': row.modulo,
        'registro_id': row.registro_id,
    }


CHEQUEOS = OrderedDict([
    ('entrega-antes-recepcion', {
        'titulo': 'Entrega anterior a la recepción',
        'descripcion': ('Entregas registradas con fecha anterior a la '
                        'recepción que creó el folio: el folio se entregó '
                        'antes de existir.'),
        'query': entrega_antes_recepcion,
        'formatear': formatear_entrega_antes_recepcion,
    }),
    ('devolucion-antes-entrega', {
        'titulo': 'Devolución anterior a la entrega',
        'descripcion': ('Devoluciones registradas con fecha anterior a la '
                        'entrega del mismo folio.'),
        'query': devolucion_antes_entrega,
        'formatear': formatear_devolucion_antes_entrega,
    }),
    ('fechas-futuras', {
        'titulo': 'Fechas futuras',
        'descripcion': ('Recepciones, entregas o devoluciones con fecha '
                        'posterior a hoy (datos heredados o escritos fuera '
                        'del formulario).'),
        'query': fechas_futuras,
        'formatear': formatear_fechas_futuras,
    }),
])
