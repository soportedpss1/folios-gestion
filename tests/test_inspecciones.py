"""Chequeos de coherencia del módulo de inspecciones."""

from datetime import date

from app.extensions import db
from app.models.centro import Centro
from app.models.recepcion_folio import RecepcionFolio
from app.models.entrega_folio import EntregaFolio
from app.models.devolucion_folio import DevolucionFolio
from app.services.inspecciones import (
    CHEQUEOS, entrega_antes_recepcion, devolucion_antes_entrega,
    fechas_futuras, formatear_entrega_antes_recepcion,
    formatear_devolucion_antes_entrega, formatear_fechas_futuras,
    centro_devolucion_distinto, formatear_centro_devolucion_distinto,
    rangos_corruptos, formatear_rangos_corruptos,
)
from tests.conftest import make_folio


def make_cadena(tipo, centro, user, *, numero=1000, rangoId=1,
                fecha_rec=date(2026, 3, 1), fecha_ent=None, fecha_dev=None,
                estado=None):
    """Recepción de un folio + opcional entrega/devolución. Devuelve el Folio.

    estado default derivado: con fecha_ent → 'entregado'; con fecha_dev →
    'devuelto'; si no → 'disponible'. `estado` explícito permite crear
    estados incoherentes para los chequeos."""
    rec = RecepcionFolio(fecha=fecha_rec, anioCert=2026, tipoCert_id=tipo.id,
                         folioInicial=numero, folioFinal=numero,
                         rangoId=rangoId, userId=user.id)
    db.session.add(rec)
    folio = make_folio(tipo, anio=2026, numero=numero, rangoId=rangoId,
                       estado=estado or ('entregado' if fecha_ent else
                                         'devuelto' if fecha_dev else 'disponible'))
    if fecha_ent:
        db.session.add(EntregaFolio(folio_id=folio.id, fechaEntrega=fecha_ent,
                                    centroId=centro.id, userId=user.id))
    if fecha_dev:
        db.session.add(DevolucionFolio(folio_id=folio.id,
                                       fechaDevolucion=fecha_dev,
                                       centroId=centro.id, userId=user.id))
    db.session.commit()
    return folio


def hallazgos(query, formatear):
    return [formatear(r) for r in query.all()]


def test_entrega_antes_recepcion_detecta(app, tipo, centro, operador):
    # entrega 01/03/2026 < recepción 10/03/2026
    folio = make_cadena(tipo, centro, operador,
                        fecha_rec=date(2026, 3, 10), fecha_ent=date(2026, 3, 1))
    res = hallazgos(entrega_antes_recepcion(), formatear_entrega_antes_recepcion)
    assert len(res) == 1
    assert res[0]['modulo'] == 'entregas'
    assert res[0]['registro_id']  # id de la EntregaFolio
    assert f'Folio {folio.folio}' in res[0]['titulo']
    assert '01/03/2026' in res[0]['detalle'] and '10/03/2026' in res[0]['detalle']


def test_entrega_antes_recepcion_no_alerta_orden_correcto(app, tipo, centro, operador):
    make_cadena(tipo, centro, operador, numero=2000, rangoId=2,
                fecha_rec=date(2026, 3, 1), fecha_ent=date(2026, 3, 10))
    make_cadena(tipo, centro, operador, numero=3000, rangoId=3,
                fecha_rec=date(2026, 3, 1))          # sin entrega
    assert hallazgos(entrega_antes_recepcion(),
                     formatear_entrega_antes_recepcion) == []


def test_devolucion_antes_entrega_detecta(app, tipo, centro, operador):
    folio = make_cadena(tipo, centro, operador, fecha_ent=date(2026, 3, 10),
                        fecha_dev=date(2026, 3, 1))
    res = hallazgos(devolucion_antes_entrega(), formatear_devolucion_antes_entrega)
    assert len(res) == 1
    assert res[0]['modulo'] == 'devoluciones'
    assert f'Folio {folio.folio}' in res[0]['titulo']
    assert '01/03/2026' in res[0]['detalle'] and '10/03/2026' in res[0]['detalle']


def test_devolucion_antes_entrega_no_alerta_orden_correcto(app, tipo, centro, operador):
    make_cadena(tipo, centro, operador, numero=2000, rangoId=2,
                fecha_ent=date(2026, 3, 1), fecha_dev=date(2026, 3, 10))
    assert hallazgos(devolucion_antes_entrega(),
                     formatear_devolucion_antes_entrega) == []


def test_fechas_futuras_cubre_los_tres_modulos(app, tipo, centro, operador):
    make_cadena(tipo, centro, operador, numero=1000, rangoId=1,
                fecha_rec=date(2027, 1, 1))
    make_cadena(tipo, centro, operador, numero=2000, rangoId=2,
                fecha_rec=date(2026, 3, 1), fecha_ent=date(2027, 1, 1))
    make_cadena(tipo, centro, operador, numero=3000, rangoId=3,
                fecha_rec=date(2026, 3, 1), fecha_ent=date(2026, 3, 1),
                fecha_dev=date(2027, 1, 1))
    res = hallazgos(fechas_futuras(), formatear_fechas_futuras)
    assert len(res) == 3
    por_modulo = {h['modulo']: h for h in res}
    assert set(por_modulo) == {'recepcion', 'entregas', 'devoluciones'}
    assert por_modulo['recepcion']['registro_id']  # id de la RecepcionFolio
    assert por_modulo['entregas']['titulo'].startswith('Entrega')
    assert all('01/01/2027' in h['detalle'] for h in res)


def test_fechas_futuras_ignora_hoy_y_el_pasado(app, tipo, centro, operador):
    # El límite es hoy: hoy NO es futuro (date.today(), hora local).
    make_cadena(tipo, centro, operador, numero=4000, rangoId=4,
                fecha_rec=date.today(), fecha_ent=date(2026, 1, 1),
                fecha_dev=date(2026, 1, 2))
    assert hallazgos(fechas_futuras(), formatear_fechas_futuras) == []


def test_chequeos_incluye_las_tres_claves():
    assert list(CHEQUEOS)[:3] == ['entrega-antes-recepcion',
                                  'devolucion-antes-entrega', 'fechas-futuras']
    for c in CHEQUEOS.values():
        assert c['titulo'] and c['descripcion']
        assert callable(c['query']) and callable(c['formatear'])


def make_rango(tipo, user, ini, fin, rangoId, anio=2026, fecha=date(2026, 3, 1)):
    """Recepción sin folios individuales (el chequeo de rangos solo mira
    recepcion_folios)."""
    rec = RecepcionFolio(fecha=fecha, anioCert=anio, tipoCert_id=tipo.id,
                         folioInicial=ini, folioFinal=fin, rangoId=rangoId,
                         userId=user.id)
    db.session.add(rec)
    db.session.commit()
    return rec


def test_centro_devolucion_distinto_detecta(app, tipo, centro, operador):
    otro = Centro(name='Otro Centro', telefono='555', direccion='Calle 2',
                  activo=True)
    db.session.add(otro)
    db.session.commit()
    folio = make_cadena(tipo, centro, operador, fecha_ent=date(2026, 3, 1),
                        fecha_dev=date(2026, 3, 10))
    folio.devolucion.centroId = otro.id
    db.session.commit()
    res = hallazgos(centro_devolucion_distinto(),
                    formatear_centro_devolucion_distinto)
    assert len(res) == 1
    assert res[0]['modulo'] == 'devoluciones'
    assert res[0]['registro_id'] == folio.devolucion.id
    assert centro.name in res[0]['detalle'] and otro.name in res[0]['detalle']


def test_centro_devolucion_igual_no_alerta(app, tipo, centro, operador):
    make_cadena(tipo, centro, operador, numero=2000, rangoId=2,
                fecha_ent=date(2026, 3, 1), fecha_dev=date(2026, 3, 10))
    assert hallazgos(centro_devolucion_distinto(),
                     formatear_centro_devolucion_distinto) == []


def test_rangos_corruptos_detecta_invertido(app, tipo, operador):
    make_rango(tipo, operador, ini=500, fin=400, rangoId=10)
    res = hallazgos(rangos_corruptos(), formatear_rangos_corruptos)
    assert len(res) == 1
    assert res[0]['modulo'] == 'recepcion'
    assert 'invertido' in res[0]['detalle']


def test_rangos_corruptos_detecta_solape_sin_duplicar(app, tipo, operador):
    make_rango(tipo, operador, ini=1, fin=100, rangoId=11)
    make_rango(tipo, operador, ini=50, fin=150, rangoId=12)   # solapa con 1-100
    res = hallazgos(rangos_corruptos(), formatear_rangos_corruptos)
    assert len(res) == 2, 'cada rango del par debe aparecer exactamente una vez'
    assert all('solapa' in h['detalle'] for h in res)
    assert {h['registro_id'] for h in res} == {r.id for r in
           RecepcionFolio.query.order_by(RecepcionFolio.id).all()}


def test_rangos_sanos_no_alertan(app, tipo, operador):
    make_rango(tipo, operador, ini=1, fin=100, rangoId=13)
    make_rango(tipo, operador, ini=101, fin=200, rangoId=14)  # adyacente no solapa
    make_rango(tipo, operador, ini=1, fin=100, rangoId=15, anio=2025)  # otro año
    assert hallazgos(rangos_corruptos(), formatear_rangos_corruptos) == []
