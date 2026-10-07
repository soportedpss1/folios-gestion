"""Conteos de KPIs de folios en una sola query (COUNT + CASE WHEN).

Una única fuente de verdad para dashboard y reportes: antes cada blueprint
tenía su propia copia y las semánticas divergieron.
"""

from sqlalchemy import and_, case, func

from app.models.folio import Folio


def conteos_folios(query):
    """7 conteos (total, digitado, escaneado, nulo, disponible, entregado, devuelto).

    `entregado`/`devuelto` excluyen nulos, igual que los filtros de estado de
    los listados, para que las tarjetas coincidan con las filas visibles.
    """
    row = query.with_entities(
        func.count(Folio.id),
        func.coalesce(func.sum(case((Folio.digitado == True, 1), else_=0)), 0),
        func.coalesce(func.sum(case((Folio.escaneado == True, 1), else_=0)), 0),
        func.coalesce(func.sum(case((Folio.nulo == True, 1), else_=0)), 0),
        func.coalesce(func.sum(case(
            (and_(Folio.estado == 'disponible', Folio.nulo == False), 1), else_=0)), 0),
        func.coalesce(func.sum(case(
            (and_(Folio.estado == 'entregado', Folio.nulo == False), 1), else_=0)), 0),
        func.coalesce(func.sum(case(
            (and_(Folio.estado == 'devuelto', Folio.nulo == False), 1), else_=0)), 0),
    ).one()
    total, digitados, escaneados, nulos, disponibles, entregados, devueltos = row

    return {
        'total': int(total or 0),
        'digitados': int(digitados or 0),
        'escaneados': int(escaneados or 0),
        'nulos': int(nulos or 0),
        'disponibles': int(disponibles or 0),
        'entregados': int(entregados or 0),
        'devueltos': int(devueltos or 0),
    }
