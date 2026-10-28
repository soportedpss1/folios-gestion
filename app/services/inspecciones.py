"""Chequeos de coherencia de datos para el módulo de inspecciones.

Cada chequeo devuelve una query paginable (columnas con nombre, `order_by`
incluido — la paginación sin orden estable solapa páginas) y un `formatear`
que convierte cada fila en el dict de display `{titulo, detalle, modulo,
registro_id}`. Solo lectura: la corrección ocurre en la pantalla de edición
del módulo dueño (URLS_CORREGIR).
"""

from collections import OrderedDict
from datetime import date

from sqlalchemy import and_, literal, or_
from sqlalchemy.orm import aliased

from app.extensions import db
from app.models.recepcion_folio import RecepcionFolio
from app.models.entrega_folio import EntregaFolio
from app.models.devolucion_folio import DevolucionFolio
from app.models.centro import Centro
from app.models.folio import Folio

# modulo → endpoint de la pantalla de corrección (lo consume la ruta detalle).
URLS_CORREGIR = {
    'recepcion': 'recepcion.edit',
    'entregas': 'entregas.edit',
    'devoluciones': 'devoluciones.edit',
    'folios': 'folios.details',
}

# Permiso de edición del módulo dueño: sin él, el hallazgo conserva el
# link plano (detect-and-link original) y el panel de corrección no aparece.
PERMISOS_EDITAR = {
    'recepcion': 'recepcion.gestionar',
    'entregas': 'entregas.gestionar',
    'devoluciones': 'devoluciones.gestionar',
    'folios': 'folios.actualizar',
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


def centro_devolucion_distinto():
    """Devoluciones que apuntan a un centro distinto del de su entrega."""
    cd = aliased(Centro)
    ce = aliased(Centro)
    return (
        db.session.query(
            DevolucionFolio.id.label('registro_id'),
            Folio.folio,
            cd.name.label('centro_devolucion'),
            ce.name.label('centro_entrega'),
        )
        .join(EntregaFolio, DevolucionFolio.folio_id == EntregaFolio.folio_id)
        .join(Folio, DevolucionFolio.folio_id == Folio.id)
        .join(cd, DevolucionFolio.centroId == cd.id)
        .join(ce, EntregaFolio.centroId == ce.id)
        .filter(DevolucionFolio.centroId != EntregaFolio.centroId)
        .order_by(DevolucionFolio.id)
    )


def formatear_centro_devolucion_distinto(row):
    return {
        'titulo': f'Devolución #{row.registro_id} · Folio {row.folio}',
        'detalle': (f'Devolución a {row.centro_devolucion} ≠ entrega a '
                    f'{row.centro_entrega}'),
        'modulo': 'devoluciones',
        'registro_id': row.registro_id,
    }


def rangos_corruptos():
    """Recepciones con rango invertido o solapado con otro del mismo año/tipo.

    El EXISTS correlacionado detecta "existe otro rango que solapa conmigo":
    cada rango del par aparece una sola vez (sin self-join a.id < b.id).
    """
    otro = aliased(RecepcionFolio)
    solapa = (
        db.session.query(otro)
        .filter(
            otro.anioCert == RecepcionFolio.anioCert,
            otro.tipoCert_id == RecepcionFolio.tipoCert_id,
            otro.id != RecepcionFolio.id,
            otro.folioInicial <= RecepcionFolio.folioFinal,
            otro.folioFinal >= RecepcionFolio.folioInicial,
        )
        .exists()
    )
    invertido = RecepcionFolio.folioInicial > RecepcionFolio.folioFinal
    return (
        db.session.query(
            RecepcionFolio.id.label('registro_id'),
            RecepcionFolio.folioInicial,
            RecepcionFolio.folioFinal,
            invertido.label('invertido'),
            solapa.label('solapa'),
        )
        .filter(or_(invertido, solapa))
        .order_by(RecepcionFolio.id)
    )


def formatear_rangos_corruptos(row):
    partes = []
    if row.invertido:
        partes.append(f'rango invertido ({row.folioInicial}-{row.folioFinal})')
    if row.solapa:
        partes.append('solapa con otro rango del mismo año y tipo')
    return {
        'titulo': f'Recepción #{row.registro_id}',
        'detalle': 'Recepción con ' + ' y '.join(partes),
        'modulo': 'recepcion',
        'registro_id': row.registro_id,
    }


def estado_inconsistente():
    """Folios cuyo estado no coincide con sus registros de entrega/devolución.

    El estado 'perdido' no entra en ninguna rama: su recuperación deriva del
    registro de entrega, no del campo estado (por diseño, fuera de alcance).
    """
    con_entrega = (
        db.session.query(EntregaFolio)
        .filter(EntregaFolio.folio_id == Folio.id)
        .exists()
    )
    con_devolucion = (
        db.session.query(DevolucionFolio)
        .filter(DevolucionFolio.folio_id == Folio.id)
        .exists()
    )
    return (
        db.session.query(
            Folio.id.label('registro_id'),
            Folio.folio,
            Folio.estado,
            con_entrega.label('tiene_entrega'),
            con_devolucion.label('tiene_devolucion'),
        )
        .filter(or_(
            and_(Folio.estado == 'entregado', ~con_entrega),
            and_(Folio.estado == 'devuelto', ~con_devolucion),
            and_(Folio.estado == 'disponible', con_entrega),
        ))
        .order_by(Folio.id)
    )


def formatear_estado_inconsistente(row):
    if row.estado == 'entregado':
        detalle = "Estado 'entregado' sin registro de entrega"
    elif row.estado == 'devuelto':
        detalle = "Estado 'devuelto' sin registro de devolución"
    else:
        detalle = "Estado 'disponible' con entrega registrada"
    return {
        'titulo': f'Folio {row.folio}',
        'detalle': detalle,
        'modulo': 'folios',
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
    ('centro-devolucion-distinto', {
        'titulo': 'Centro de devolución distinto al de la entrega',
        'descripcion': ('Devoluciones que apuntan a un centro de salud '
                        'distinto del centro al que se entregó el folio.'),
        'query': centro_devolucion_distinto,
        'formatear': formatear_centro_devolucion_distinto,
    }),
    ('rangos-corruptos', {
        'titulo': 'Rangos de recepción corruptos',
        'descripcion': ('Recepciones con el folio final menor que el inicial '
                        'o rangos solapados entre sí del mismo año y tipo de '
                        'certificado.'),
        'query': rangos_corruptos,
        'formatear': formatear_rangos_corruptos,
    }),
    ('estado-inconsistente', {
        'titulo': 'Estado del folio sin coherencia',
        'descripcion': ('Folios en estado entregado sin entrega registrada, '
                        'devueltos sin devolución, o disponibles con una '
                        'entrega registrada.'),
        'query': estado_inconsistente,
        'formatear': formatear_estado_inconsistente,
    }),
])
