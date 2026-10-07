"""Fase 4 — guardas de agregación (dashboard/reportes) y paginación de listados."""

import re
from datetime import datetime, date

from app.extensions import db
from app.models.entrega_folio import EntregaFolio
from app.models.recepcion_folio import RecepcionFolio
from tests.conftest import make_folio

Y = datetime.now().year


def _seed_folios_variados(app, tipo, centro, operador):
    """5 folios del año actual con estados variados + 1 del año anterior."""
    f1 = make_folio(tipo, anio=Y, numero=1001, digitado=True)                      # disponible
    f2 = make_folio(tipo, anio=Y, numero=1002, estado='entregado', escaneado=True)  # entregado
    f3 = make_folio(tipo, anio=Y, numero=1003, digitado=True, nulo=True)            # nulo
    f4 = make_folio(tipo, anio=Y, numero=1004, estado='devuelto')                   # devuelto
    f5 = make_folio(tipo, anio=Y, numero=1005)                                      # disponible
    make_folio(tipo, anio=Y - 1, numero=999)                                        # otro año

    db.session.add(EntregaFolio(folio_id=f2.id, fechaEntrega=date(Y, 1, 15),
                                centroId=centro.id, userId=operador.id))
    db.session.add(EntregaFolio(folio_id=f4.id, fechaEntrega=date(Y, 2, 15),
                                centroId=centro.id, userId=operador.id))
    db.session.commit()
    # total, digitados, escaneados, nulos, disponibles, entregados, devueltos
    return dict(total=5, digitados=2, escaneados=1, nulos=1, disponibles=2,
                entregados=1, devueltos=1)


def test_dashboard_kpis_agregados_correctos(auth_client, app, tipo, centro, operador):
    esperado = _seed_folios_variados(app, tipo, centro, operador)

    resp = auth_client.get('/dashboard/')
    assert resp.status_code == 200
    numeros = [int(n) for n in re.findall(
        r'<h3 class="fw-bold mb-0[^"]*">(\d+)</h3>', resp.get_data(as_text=True))]
    assert len(numeros) == 7, f'KPIs encontrados: {numeros}'
    total, digitados, escaneados, nulos, disponibles, entregados, devueltos = numeros
    assert dict(total=total, digitados=digitados, escaneados=escaneados, nulos=nulos,
                disponibles=disponibles, entregados=entregados, devueltos=devueltos) == esperado


def test_reportes_stats_agregados_correctos(auth_client, app, tipo, centro, operador):
    esperado = _seed_folios_variados(app, tipo, centro, operador)

    resp = auth_client.get(f'/reportes/api/data?anioCert={Y}')
    assert resp.status_code == 200
    stats = resp.get_json()['stats']
    for clave, valor in esperado.items():
        assert stats[clave] == valor, f'stats[{clave}]={stats[clave]}, esperado {valor}'


def _marcadores_visibles(text, valores):
    return [v for v in valores if v in text]


def test_entregas_index_paginado(auth_client, app, tipo, centro, operador):
    numeros = list(range(12001, 12031))
    for n in numeros:
        folio = make_folio(tipo, anio=Y, numero=n, estado='entregado')
        db.session.add(EntregaFolio(folio_id=folio.id, fechaEntrega=date(Y, 3, 1),
                                    centroId=centro.id, userId=operador.id))
    db.session.commit()

    text = auth_client.get('/entregas/').get_data(as_text=True)
    visibles = _marcadores_visibles(text, [str(n) for n in numeros])
    assert 'page=2' in text, 'sin paginación en entregas'
    assert len(visibles) == 25, f'page1 muestra {len(visibles)} de 30'


def test_devoluciones_index_paginado(auth_client, app, tipo, centro, operador, folio_entregado):
    from app.models.devolucion_folio import DevolucionFolio
    numeros = list(range(13001, 13031))
    for n in numeros:
        folio = make_folio(tipo, anio=Y, numero=n, estado='entregado')
        db.session.add(EntregaFolio(folio_id=folio.id, fechaEntrega=date(Y, 3, 1),
                                    centroId=centro.id, userId=operador.id))
        db.session.add(DevolucionFolio(folio_id=folio.id, fechaDevolucion=date(Y, 3, 2),
                                       centroId=centro.id, userId=operador.id))
        folio.estado = 'devuelto'
    db.session.commit()

    text = auth_client.get('/devoluciones/').get_data(as_text=True)
    visibles = _marcadores_visibles(text, [str(n) for n in numeros])
    assert 'page=2' in text, 'sin paginación en devoluciones'
    assert len(visibles) == 25, f'page1 muestra {len(visibles)} de 30'


def test_recepcion_index_paginado(auth_client, app, tipo, operador):
    for i in range(30):
        base = 5001 + i
        db.session.add(RecepcionFolio(
            fecha=date(Y, 4, 1), anioCert=Y, tipoCert_id=tipo.id,
            folioInicial=base, folioFinal=base, rangoId=base, userId=operador.id))
    db.session.commit()

    text = auth_client.get('/recepcion/').get_data(as_text=True)
    marcadores = [f'{5001 + i} - {5001 + i}' for i in range(30)]
    visibles = _marcadores_visibles(text, marcadores)
    assert 'page=2' in text, 'sin paginación en recepción'
    assert len(visibles) == 25, f'page1 muestra {len(visibles)} de 30'
