"""Chequeos de coherencia del módulo de inspecciones."""

from datetime import date
import re

from app.extensions import db
from app.models.centro import Centro
from app.models.recepcion_folio import RecepcionFolio
from app.models.entrega_folio import EntregaFolio
from app.models.devolucion_folio import DevolucionFolio
from app.models.permiso_usuario import PermisoUsuario
from app.services.inspecciones import (
    CHEQUEOS, entrega_antes_recepcion, devolucion_antes_entrega,
    fechas_futuras, formatear_entrega_antes_recepcion,
    formatear_devolucion_antes_entrega, formatear_fechas_futuras,
    centro_devolucion_distinto, formatear_centro_devolucion_distinto,
    rangos_corruptos, formatear_rangos_corruptos,
    estado_inconsistente, formatear_estado_inconsistente,
)
from tests.conftest import make_folio, make_user


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
    assert res[0]['entrega_id']  # id de la EntregaFolio cruzada
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


def test_estado_entregado_sin_entrega_detectado(app, tipo, centro, operador):
    folio = make_cadena(tipo, centro, operador, numero=5000, rangoId=20,
                        estado='entregado')            # sin fila de entrega
    res = hallazgos(estado_inconsistente(), formatear_estado_inconsistente)
    assert len(res) == 1
    assert res[0]['modulo'] == 'folios'
    assert res[0]['registro_id'] == folio.id
    assert "sin registro de entrega" in res[0]['detalle']


def test_estado_devuelto_sin_devolucion_detectado(app, tipo, centro, operador):
    folio = make_cadena(tipo, centro, operador, numero=5001, rangoId=21,
                        fecha_ent=date(2026, 3, 1))   # estado 'entregado'
    folio.estado = 'devuelto'                          # sin fila de devolución
    db.session.commit()
    res = hallazgos(estado_inconsistente(), formatear_estado_inconsistente)
    assert len(res) == 1 and res[0]['registro_id'] == folio.id
    assert "sin registro de devolución" in res[0]['detalle']


def test_estado_disponible_con_entrega_detectado(app, tipo, centro, operador):
    folio = make_cadena(tipo, centro, operador, numero=5002, rangoId=22,
                        fecha_ent=date(2026, 3, 1), estado='disponible')
    res = hallazgos(estado_inconsistente(), formatear_estado_inconsistente)
    assert len(res) == 1 and res[0]['registro_id'] == folio.id
    assert 'con entrega registrada' in res[0]['detalle']


def test_estados_coherentes_y_perdido_no_alertan(app, tipo, centro, operador):
    make_cadena(tipo, centro, operador, numero=6001, rangoId=23)   # disponible solo
    make_cadena(tipo, centro, operador, numero=6002, rangoId=24,
                fecha_ent=date(2026, 3, 1))                       # entregado ok
    make_cadena(tipo, centro, operador, numero=6003, rangoId=25,
                fecha_ent=date(2026, 3, 1), fecha_dev=date(2026, 3, 10))  # devuelto ok
    make_cadena(tipo, centro, operador, numero=6004, rangoId=26,
                fecha_ent=date(2026, 3, 1), estado='perdido')      # fuera de alcance
    assert hallazgos(estado_inconsistente(),
                     formatear_estado_inconsistente) == []


def test_chequeos_completos_son_seis():
    assert len(CHEQUEOS) == 6
    assert list(CHEQUEOS)[-1] == 'estado-inconsistente'


CHEQUEO_CLAVES = ['entrega-antes-recepcion', 'devolucion-antes-entrega',
                  'fechas-futuras', 'centro-devolucion-distinto',
                  'rangos-corruptos', 'estado-inconsistente']


def test_index_muestra_los_seis_chequeos(admin_client, app):
    # La spec da link solo con hallazgos: en DB limpia se pinesa la tarjeta
    # (título) y que las 6 claves sean ruteables (200 con vacío).
    html = admin_client.get('/inspecciones/').get_data(as_text=True)
    for clave in CHEQUEO_CLAVES:
        assert CHEQUEOS[clave]['titulo'] in html, f'falta tarjeta {clave}'
        assert admin_client.get(f'/inspecciones/{clave}').status_code == 200, \
            f'detalle no ruteable: {clave}'
    assert 'Sin inconsistencias' in html, 'DB limpia → tarjetas verdes'


def test_index_enlaza_detalle_con_hallazgo(app, tipo, centro, operador,
                                           admin_client):
    make_cadena(tipo, centro, operador, fecha_rec=date(2026, 3, 10),
                fecha_ent=date(2026, 3, 1))
    html = admin_client.get('/inspecciones/').get_data(as_text=True)
    assert '/inspecciones/entrega-antes-recepcion' in html


def test_detalle_muestra_hallazgo_y_link_corregir(app, tipo, centro, operador,
                                                  admin_client):
    make_cadena(tipo, centro, operador, fecha_rec=date(2026, 3, 10),
                fecha_ent=date(2026, 3, 1))
    entrega = EntregaFolio.query.one()
    html = admin_client.get('/inspecciones/entrega-antes-recepcion') \
        .get_data(as_text=True)
    assert f'data-url="/entregas/{entrega.id}/edit"' in html, 'sin panel'
    assert '01/03/2026' in html and '10/03/2026' in html


def test_fechas_futuras_link_por_modulo(app, tipo, centro, operador, admin_client):
    make_cadena(tipo, centro, operador, numero=1000, rangoId=1,
                fecha_rec=date(2027, 1, 1))
    f_ent = make_cadena(tipo, centro, operador, numero=2000, rangoId=2,
                        fecha_rec=date(2026, 3, 1), fecha_ent=date(2027, 1, 1))
    f_dev = make_cadena(tipo, centro, operador, numero=3000, rangoId=3,
                        fecha_rec=date(2026, 3, 1), fecha_ent=date(2026, 3, 1),
                        fecha_dev=date(2027, 1, 1))
    # Cada make_cadena crea su recepción: la futura es la de rangoId=1.
    rec = RecepcionFolio.query.filter_by(rangoId=1).one()
    ent, dev = f_ent.entrega, f_dev.devolucion
    html = admin_client.get('/inspecciones/fechas-futuras') \
        .get_data(as_text=True)
    assert f'data-url="/recepcion/{rec.id}/edit"' in html
    assert f'data-url="/entregas/{ent.id}/edit"' in html
    assert f'data-url="/devoluciones/{dev.id}/edit"' in html


def test_detalle_404_clave_desconocida(admin_client, app):
    assert admin_client.get('/inspecciones/no-existe').status_code == 404


def test_detalle_pagina_estable(app, tipo, centro, operador, admin_client):
    # 26 hallazgos: 25 en página 1, el 26º solo en la 2 (order_by estable).
    for n in range(26):
        make_cadena(tipo, centro, operador, numero=1000 + n, rangoId=100 + n,
                    fecha_rec=date(2026, 3, 10), fecha_ent=date(2026, 3, 1))
    p1 = admin_client.get('/inspecciones/entrega-antes-recepcion') \
        .get_data(as_text=True)
    p2 = admin_client.get('/inspecciones/entrega-antes-recepcion?page=2') \
        .get_data(as_text=True)
    assert 'Folio 1000' in p1 and 'Folio 1000' not in p2
    assert 'Folio 1025' in p2 and 'Folio 1025' not in p1
    assert len(re.findall(r'/entregas/\d+/edit', p1)) == 25


def test_sin_permiso_redirige_a_dashboard(app, client):
    lectura = make_user('lectura_insp', 'lectura')
    client.post('/auth/login', data={'username': lectura.username,
                                     'password': 'pass12345'})
    for url in ('/inspecciones/', '/inspecciones/fechas-futuras'):
        resp = client.get(url)
        assert resp.status_code == 302
        assert '/dashboard' in resp.headers['Location']


def test_grant_inspecciones_ver_permite_ver(app, client):
    lectura = make_user('lectura_insp2', 'lectura')
    db.session.add(PermisoUsuario(user_id=lectura.id,
                                  permiso='inspecciones.ver'))
    db.session.commit()
    client.post('/auth/login', data={'username': lectura.username,
                                     'password': 'pass12345'})
    assert client.get('/inspecciones/').status_code == 200


def test_sidebar_link_visible_para_admin(admin_client, app):
    html = admin_client.get('/dashboard/').get_data(as_text=True)
    assert '/inspecciones/' in html, 'admin debe ver el link'


def test_sidebar_link_oculto_para_lectura_sin_grant(app, client):
    # Dos usuarios autenticados en el mismo test chocan con g._login_user:
    # este test solo loguea a la lectura (regla de un usuario por test).
    lectura = make_user('lectura_insp3', 'lectura')
    client.post('/auth/login', data={'username': lectura.username,
                                     'password': 'pass12345'})
    html = client.get('/dashboard/').get_data(as_text=True)
    assert '/inspecciones/' not in html, 'lector sin grant no ve el link'
