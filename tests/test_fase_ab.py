"""Regresiones de las fases A (seguridad) y B (bugs)."""

from datetime import date

from app.extensions import db
from app.models.devolucion_folio import DevolucionFolio
from app.models.entrega_folio import EntregaFolio
from app.models.folio import Folio
from app.models.recepcion_folio import RecepcionFolio
from tests.conftest import make_folio, make_user

Y = 2026


# ---------------------------------------------------------------- recepción


def test_recepcion_rechaza_rango_demasiado_grande(admin_client, app, tipo, operador):
    resp = admin_client.post('/recepcion/create', data={
        'fecha': '2026-01-01', 'anioCert': Y, 'tipoCert': tipo.id,
        'folioInicial': 1, 'folioFinal': 10000000,
    }, follow_redirects=True)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'no puede superar' in html, 'rango gigante aceptado'
    assert Folio.query.count() == 0, 'se insertaron folios a pesar del rechazo'


def test_recepcion_acepta_rango_normal(admin_client, app, tipo, operador):
    resp = admin_client.post('/recepcion/create', data={
        'fecha': '2026-01-01', 'anioCert': Y, 'tipoCert': tipo.id,
        'folioInicial': 1, 'folioFinal': 5,
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert Folio.query.count() == 5
    assert RecepcionFolio.query.count() == 1


# ----------------------------------------------------------------- sesión


def test_load_user_devuelve_none_si_inactivo(app, operador):
    """El user loader ignora usuarios desactivados: la sesión viva muere."""
    from app.extensions import login_manager

    assert login_manager._user_callback(str(operador.id)) is operador

    operador.activo = False
    db.session.commit()

    assert login_manager._user_callback(str(operador.id)) is None, (
        'la sesión de un usuario desactivado seguía resolviendo')


def test_load_user_devuelve_none_si_no_existe(app):
    from app.extensions import login_manager
    assert login_manager._user_callback('999999') is None


# ------------------------------------------------- permisos / último admin


def test_certificados_index_requiere_admin(auth_client, app):
    resp = auth_client.get('/certificados/')
    assert resp.status_code == 302
    assert '/dashboard' in resp.headers['Location']


def test_admin_no_puede_degradarse_a_si_mismo_si_es_el_unico(admin, app):
    """Autodegradar/autodesactivar al único admin deja el sistema sin salida."""
    client = app.test_client()
    client.post('/auth/login', data={'username': admin.username, 'password': 'pass12345'})

    resp = client.post(f'/usuarios/{admin.id}/edit', data={
        'name': admin.name, 'username': admin.username, 'email': 'adminuser@example.com',
        'rol': 'operador', 'activo': 'y',
    }, follow_redirects=True)

    assert resp.status_code == 200
    db.session.refresh(admin)
    assert admin.rol == 'admin', 'el único admin se degradó a sí mismo'
    assert 'último administrador' in resp.get_data(as_text=True)


def test_se_puede_desactivar_un_admin_si_queda_otro(admin, app):
    otro_admin = make_user('admin2', 'admin')
    client = app.test_client()
    client.post('/auth/login', data={'username': admin.username, 'password': 'pass12345'})

    resp = client.post(f'/usuarios/{otro_admin.id}/delete')
    assert resp.status_code == 302

    db.session.refresh(otro_admin)
    assert otro_admin.activo is False, 'con dos admin, desactivar uno debe permitirse'


def test_usuario_duplicado_no_devuelve_500(admin, app, operador):
    client = app.test_client()
    client.post('/auth/login', data={'username': admin.username, 'password': 'pass12345'})

    resp = client.post('/usuarios/create', data={
        'name': 'Otro', 'username': operador.username, 'email': 'libre@example.com',
        'password': 'pass12345', 'confirm_password': 'pass12345', 'rol': 'operador',
    })
    assert resp.status_code == 200, f'username duplicado dio {resp.status_code}'
    assert 'ya está en uso' in resp.get_data(as_text=True)


def test_certificado_duplicado_no_devuelve_500(admin, app, tipo):
    client = app.test_client()
    client.post('/auth/login', data={'username': admin.username, 'password': 'pass12345'})

    resp = client.post('/certificados/create', data={
        'name': tipo.name, 'descripcion': 'x', 'color': '#0D6EFD',
    })
    assert resp.status_code == 200, f'nombre duplicado dio {resp.status_code}'
    assert 'Ya existe' in resp.get_data(as_text=True)


# ------------------------------------------------------------ entregas


def test_edit_entrega_rechaza_otro_folio(auth_client, app, tipo, centro, operador):
    entregado = make_folio(tipo, anio=Y, numero=3001, estado='entregado')
    entrega = EntregaFolio(folio_id=entregado.id, fechaEntrega=date(Y, 1, 1),
                           centroId=centro.id, userId=operador.id)
    db.session.add(entrega)
    entregado.estado = 'devuelto'
    db.session.add(DevolucionFolio(folio_id=entregado.id, fechaDevolucion=date(Y, 2, 1),
                                   centroId=centro.id, userId=operador.id))
    libre = make_folio(tipo, anio=Y, numero=3002)
    db.session.commit()

    resp = auth_client.post(f'/entregas/{entrega.id}/edit', data={
        'folio_id': libre.id, 'fechaEntrega': '2026-01-01', 'centroId': centro.id,
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert 'Not a valid choice.' in resp.get_data(as_text=True), (
        'el folio de otra entrega entró en choices de edición')

    db.session.refresh(entrega)
    assert entrega.folio_id == entregado.id, 'la entrega se reasignó dejando huérfana la devolución'


def test_edit_entrega_folio_fijo_sin_busqueda(auth_client, app, tipo, centro, operador):
    folio = make_folio(tipo, anio=Y, numero=3051, estado='entregado')
    entrega = EntregaFolio(folio_id=folio.id, fechaEntrega=date(Y, 1, 1),
                           centroId=centro.id, userId=operador.id)
    db.session.add(entrega)
    db.session.commit()

    html = auth_client.get(f'/entregas/{entrega.id}/edit').get_data(as_text=True)
    assert 'folio-search' not in html, 'quedó el campo de búsqueda de folios'
    assert 'folios-disponibles' not in html, 'el edit sigue pidiendo folios a la API'
    assert 'readonly' in html and f'value="Folio {folio.folio}"' in html, (
        'el folio no aparece como texto de solo lectura')


def test_edit_entrega_no_toca_estado_del_folio(auth_client, app, tipo, centro, operador):
    """Editar fecha/centro no debe reescribir el estado del folio."""
    folio = make_folio(tipo, anio=Y, numero=3071, estado='entregado')
    entrega = EntregaFolio(folio_id=folio.id, fechaEntrega=date(Y, 1, 1),
                           centroId=centro.id, userId=operador.id)
    db.session.add(entrega)
    folio.estado = 'devuelto'
    db.session.add(DevolucionFolio(folio_id=folio.id, fechaDevolucion=date(Y, 2, 1),
                                   centroId=centro.id, userId=operador.id))
    db.session.commit()

    resp = auth_client.post(f'/entregas/{entrega.id}/edit', data={
        'folio_id': folio.id, 'fechaEntrega': '2026-03-05', 'centroId': centro.id,
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert 'exitosamente' in resp.get_data(as_text=True), (
        'la edición de fecha/centro falló: ' + resp.get_data(as_text=True)[:200])

    db.session.refresh(folio)
    db.session.refresh(entrega)
    assert folio.estado == 'devuelto', f'estado reescrito a {folio.estado}'
    assert entrega.fechaEntrega == date(Y, 3, 5)


def test_edit_entrega_muestra_centro_desactivado(auth_client, app, tipo, centro, operador):
    folio = make_folio(tipo, anio=Y, numero=3101, estado='entregado')
    entrega = EntregaFolio(folio_id=folio.id, fechaEntrega=date(Y, 1, 1),
                           centroId=centro.id, userId=operador.id)
    db.session.add(entrega)
    centro.activo = False
    db.session.commit()

    html = auth_client.get(f'/entregas/{entrega.id}/edit').get_data(as_text=True)
    assert f'value="{centro.id}"' in html, (
        'el centro desactivado no figura en el select: el navegador enviaría '
        'la primera opción activa y la entrega se reasignaría sin aviso')


# --------------------------------------------------- KPIs / paginación


def test_kpis_entregados_excluyen_nulos(auth_client, app, tipo, centro, operador):
    make_folio(tipo, anio=Y, numero=4001, estado='entregado', nulo=True)
    make_folio(tipo, anio=Y, numero=4002, estado='entregado')
    db.session.commit()

    resp = auth_client.get('/reportes/api/data?anioCert=Y')
    stats = resp.get_json()['stats']
    assert stats['entregados'] == 1, f"nulos contados como entregados: {stats['entregados']}"


def test_stats_reportes_siguen_el_filtro_de_estado(auth_client, app, tipo, centro, operador):
    make_folio(tipo, anio=Y, numero=4101, estado='disponible')
    folio = make_folio(tipo, anio=Y, numero=4102, estado='entregado')
    db.session.add(EntregaFolio(folio_id=folio.id, fechaEntrega=date(Y, 1, 1),
                                centroId=centro.id, userId=operador.id))
    db.session.commit()

    data = auth_client.get(f'/reportes/api/data?anioCert=Y&estado=entregado').get_json()
    assert data['pagination']['total'] == 1
    assert data['stats']['total'] == 1, (
        'las tarjetas no siguen el filtro de estado y quedan '
        f"en {data['stats']['total']} frente a {data['pagination']['total']} filas")


def test_folios_per_page_con_tope(auth_client, app, tipo):
    for n in range(20001, 20251):
        make_folio(tipo, anio=Y, numero=n)
    db.session.commit()

    html = auth_client.get('/folios/?per_page=1000000').get_data(as_text=True)
    visibles = [n for n in range(20001, 20251) if str(n) in html]
    assert len(visibles) <= 200, f'per_page sin tope: {len(visibles)} filas renderizadas'


def test_update_status_rechaza_mas_de_1000_folios(auth_client, app, tipo):
    resp = auth_client.post('/folios/update-status', json={
        'folio_ids': list(range(1, 1500)), 'digitado': True, 'escaneado': False, 'nulo': False,
    })
    assert resp.status_code == 400


def test_edit_entrega_select_acotado(auth_client, app, tipo, centro, operador):
    """El select de edición no debe renderizar un option por cada folio disponible."""
    folio = make_folio(tipo, anio=Y, numero=5001, estado='entregado')
    entrega = EntregaFolio(folio_id=folio.id, fechaEntrega=date(Y, 1, 1),
                           centroId=centro.id, userId=operador.id)
    db.session.add(entrega)
    for n in range(5100, 5300):
        make_folio(tipo, anio=Y, numero=n)
    db.session.commit()

    html = auth_client.get(f'/entregas/{entrega.id}/edit').get_data(as_text=True)
    opciones = html.count('<option')
    assert opciones < 40, f'{opciones} options en el select de edición'


def test_edit_devolucion_select_acotado(auth_client, app, tipo, centro, operador):
    from app.models.devolucion_folio import DevolucionFolio as Dev

    folio = make_folio(tipo, anio=Y, numero=5401, estado='entregado')
    db.session.add(EntregaFolio(folio_id=folio.id, fechaEntrega=date(Y, 1, 1),
                                centroId=centro.id, userId=operador.id))
    db.session.flush()
    dev = Dev(folio_id=folio.id, fechaDevolucion=date(Y, 2, 1),
              centroId=centro.id, userId=operador.id)
    db.session.add(dev)
    folio.estado = 'devuelto'
    for n in range(5500, 5700):
        make_folio(tipo, anio=Y, numero=n, estado='entregado')
    db.session.commit()

    html = auth_client.get(f'/devoluciones/{dev.id}/edit').get_data(as_text=True)
    opciones = html.count('<option')
    assert opciones < 40, f'{opciones} options en el select de edición'


def _devolucion_con_folio(auth_client, app, tipo, centro, operador, numero=5701):
    folio = make_folio(tipo, anio=Y, numero=numero, estado='entregado')
    db.session.add(EntregaFolio(folio_id=folio.id, fechaEntrega=date(Y, 1, 1),
                                centroId=centro.id, userId=operador.id))
    db.session.flush()
    dev = DevolucionFolio(folio_id=folio.id, fechaDevolucion=date(Y, 2, 1),
                          centroId=centro.id, userId=operador.id)
    db.session.add(dev)
    folio.estado = 'devuelto'
    db.session.commit()
    return folio, dev


def test_edit_devolucion_folio_fijo_sin_fetch(auth_client, app, tipo, centro, operador):
    """El folio sale como texto de solo lectura: sin búsqueda ni fetch por centro."""
    folio, dev = _devolucion_con_folio(auth_client, app, tipo, centro, operador)

    html = auth_client.get(f'/devoluciones/{dev.id}/edit').get_data(as_text=True)
    assert 'folio-search' not in html, 'quedó el campo de búsqueda de folios'
    assert '/devoluciones/api/folios/' not in html, (
        'el edit sigue pidiendo folios a la API por centro')
    assert 'readonly' in html and f'value="Folio {folio.folio}"' in html, (
        'el folio no aparece como texto de solo lectura')


def test_edit_devolucion_no_toca_estado_del_folio(auth_client, app, tipo, centro, operador):
    """Editar fecha/centro no debe reescribir el estado del folio."""
    folio, dev = _devolucion_con_folio(auth_client, app, tipo, centro, operador)

    resp = auth_client.post(f'/devoluciones/{dev.id}/edit', data={
        'folio_id': dev.folio_id, 'fechaDevolucion': '2026-03-05', 'centroId': centro.id,
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert 'exitosamente' in resp.get_data(as_text=True), (
        'la edición de fecha/centro falló: ' + resp.get_data(as_text=True)[:200])

    db.session.refresh(folio)
    db.session.refresh(dev)
    assert folio.estado == 'devuelto', f'estado reescrito a {folio.estado}'
    assert dev.fechaDevolucion == date(Y, 3, 5)


def test_edit_devolucion_rechaza_otro_folio(auth_client, app, tipo, centro, operador):
    """La devolución no se reasigna a otro folio: choices solo lleva el actual."""
    from app.models.centro import Centro

    otro = Centro(name='Centro Ajeno', activo=True)
    db.session.add(otro)
    db.session.flush()

    mia = make_folio(tipo, anio=Y, numero=6001, estado='entregado')
    db.session.add(EntregaFolio(folio_id=mia.id, fechaEntrega=date(Y, 1, 1),
                                centroId=centro.id, userId=operador.id))
    db.session.flush()
    dev = DevolucionFolio(folio_id=mia.id, fechaDevolucion=date(Y, 2, 1),
                          centroId=centro.id, userId=operador.id)
    db.session.add(dev)
    mia.estado = 'devuelto'

    ajeno = make_folio(tipo, anio=Y, numero=6002, estado='entregado')
    db.session.add(EntregaFolio(folio_id=ajeno.id, fechaEntrega=date(Y, 1, 1),
                                centroId=otro.id, userId=operador.id))
    db.session.commit()

    resp = auth_client.post(f'/devoluciones/{dev.id}/edit', data={
        'folio_id': ajeno.id, 'fechaDevolucion': '2026-02-01', 'centroId': centro.id,
    }, follow_redirects=True)

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Not a valid choice.' in html, (
        'el otro folio entró en choices de edición')
    db.session.refresh(dev)
    assert dev.folio_id == mia.id, 'la devolución se reasignó a un folio ajeno'
