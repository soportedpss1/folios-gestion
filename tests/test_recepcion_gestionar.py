"""Acciones en recepción: editar y eliminar rangos (recepcion.gestionar)."""

from datetime import date

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.devolucion_folio import DevolucionFolio
from app.models.entrega_folio import EntregaFolio
from app.models.folio import Folio
from app.models.recepcion_folio import RecepcionFolio
from tests.conftest import make_user

INI, FIN = 100, 105  # rango base de los tests: 6 folios


def crear_recepcion(client, tipo_id, inicial=INI, final=FIN, anio=2026):
    resp = client.post(
        '/recepcion/create',
        data={'fecha': '2026-09-28', 'anioCert': anio, 'tipoCert': tipo_id,
              'folioInicial': inicial, 'folioFinal': final},
        follow_redirects=True,
    )
    assert resp.status_code == 200, 'create de prueba falló'
    return resp


def editar(client, rid, tipo_id, inicial=INI, final=FIN, anio=2026,
           fecha='2026-10-01', usuario_id=None):
    data = {'fecha': fecha, 'anioCert': anio, 'tipoCert': tipo_id,
            'folioInicial': inicial, 'folioFinal': final}
    if usuario_id is not None:
        data['usuario'] = usuario_id
    return client.post(f'/recepcion/{rid}/edit', data=data,
                       follow_redirects=True)


def eliminar(client, rid):
    return client.post(f'/recepcion/{rid}/delete', follow_redirects=True)


def unica_recepcion():
    return RecepcionFolio.query.one()


# --- permisos ---


def test_rutas_requieren_login(client):
    assert client.get('/recepcion/1/edit').status_code == 302
    assert client.post('/recepcion/1/delete').status_code == 302


def test_rutas_bloqueadas_para_operador(auth_client):
    resp = auth_client.get('/recepcion/1/edit', follow_redirects=True)
    assert 'No tiene permisos' in resp.get_data(as_text=True)
    resp = auth_client.post('/recepcion/1/delete', follow_redirects=True)
    assert 'No tiene permisos' in resp.get_data(as_text=True)


def test_col_acciones_oculta_sin_gestionar(client, app, tipo, admin):
    lectura = make_user('lector_acc', 'lectura')
    from app.models.permiso_usuario import PermisoUsuario
    db.session.add(PermisoUsuario(user_id=lectura.id, permiso='recepcion.ver'))
    db.session.commit()
    client.post('/auth/login',
                data={'username': lectura.username, 'password': 'pass12345'})
    text = client.get('/recepcion/').get_data(as_text=True)
    assert 'Acciones' not in text, 'sin recepcion.gestionar no debe ver acciones'


def test_col_acciones_visible_para_admin(admin_client, tipo):
    crear_recepcion(admin_client, tipo.id)
    text = admin_client.get('/recepcion/').get_data(as_text=True)
    assert 'Acciones' in text
    assert '/recepcion/1/edit' in text
    assert '/recepcion/1/delete' in text


def test_grant_gestionar_habilita_rutas(client, app, tipo):
    from app.models.permiso_usuario import PermisoUsuario
    lectura = make_user('lector_ges', 'lectura')
    db.session.add_all([
        PermisoUsuario(user_id=lectura.id, permiso='recepcion.ver'),
        PermisoUsuario(user_id=lectura.id, permiso='recepcion.gestionar'),
    ])
    # La recepción se crea directa: crear() exige recepcion.crear, que este
    # usuario no tiene.
    db.session.add(RecepcionFolio(
        fecha=date(2026, 9, 28), anioCert=2026, tipoCert_id=tipo.id,
        folioInicial=INI, folioFinal=FIN, rangoId=1, userId=lectura.id))
    db.session.commit()
    client.post('/auth/login',
                data={'username': lectura.username, 'password': 'pass12345'})

    resp = client.get('/recepcion/1/edit')
    assert resp.status_code == 200, 'grant debió habilitar el formulario'
    resp = client.post('/recepcion/1/delete', follow_redirects=True)
    assert RecepcionFolio.query.count() == 0, 'grant debió habilitar borrar'


# --- editar: formulario ---


def test_edit_get_muestra_form_con_valores(admin_client, tipo):
    crear_recepcion(admin_client, tipo.id)
    resp = admin_client.get('/recepcion/1/edit')
    text = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert 'Editar Recepción' in text
    assert 'Guardar cambios' in text
    assert 'value="100"' in text
    assert 'value="105"' in text


def test_edit_404(admin_client):
    assert admin_client.get('/recepcion/999/edit').status_code == 404
    assert admin_client.post('/recepcion/999/delete').status_code == 404


# --- editar: aplicación ---


def test_edit_sin_cambios_no_choca_consigo_mismo(admin_client, tipo, admin):
    """Revalidar solape contra el propio rango es un falso positivo."""
    crear_recepcion(admin_client, tipo.id)
    resp = editar(admin_client, 1, tipo.id, usuario_id=admin.id)

    text = resp.get_data(as_text=True)
    assert 'solap' not in text.lower(), 'la edición se solapó consigo misma'
    assert 'Recepción actualizada' in text
    assert Folio.query.count() == 6, 'sin cambios no debe tocar folios'


def test_edit_fecha_y_responsable(admin_client, tipo, admin, operador):
    crear_recepcion(admin_client, tipo.id)
    resp = editar(admin_client, 1, tipo.id, fecha='2026-10-05',
                  usuario_id=operador.id)

    assert 'Recepción actualizada' in resp.get_data(as_text=True)
    r = unica_recepcion()
    assert r.fecha == date(2026, 10, 5)
    assert r.userId == operador.id
    assert Folio.query.count() == 6, 'cambiar fecha no debe tocar folios'
    log = AuditLog.query.filter_by(tabla='recepcion_folios', registro_id=r.id,
                                   accion='UPDATE').one()
    assert log.accion == 'UPDATE'


def test_edit_ampliar_rango_crea_folios(admin_client, tipo, admin):
    crear_recepcion(admin_client, tipo.id)
    resp = editar(admin_client, 1, tipo.id, final=110, usuario_id=admin.id)

    assert 'Recepción actualizada' in resp.get_data(as_text=True)
    assert unica_recepcion().folioFinal == 110
    assert Folio.query.count() == 11
    nuevos = Folio.query.filter(Folio.folio > 105).all()
    assert len(nuevos) == 5
    assert all(f.estado == 'disponible' and not f.digitado and not f.nulo
               and not f.escaneado for f in nuevos)


def test_edit_reducir_rango_borra_folios_limpios(admin_client, tipo, admin):
    crear_recepcion(admin_client, tipo.id)
    resp = editar(admin_client, 1, tipo.id, final=102, usuario_id=admin.id)

    assert 'Recepción actualizada' in resp.get_data(as_text=True)
    assert unica_recepcion().folioFinal == 102
    assert Folio.query.count() == 3
    assert Folio.query.filter(Folio.folio.in_([103, 104, 105])).count() == 0


def test_edit_cambia_anio_reescribe_folios(admin_client, tipo, admin):
    crear_recepcion(admin_client, tipo.id)
    resp = editar(admin_client, 1, tipo.id, anio=2027, usuario_id=admin.id)

    assert 'Recepción actualizada' in resp.get_data(as_text=True)
    assert unica_recepcion().anioCert == 2027
    assert Folio.query.count() == 6
    assert all(f.anioCert == 2027 for f in Folio.query.all()), \
        'los folios del rango deben seguir a la recepción'


def test_edit_solape_con_otra_recepcion_bloquea(admin_client, tipo, admin):
    crear_recepcion(admin_client, tipo.id, inicial=100, final=105)
    crear_recepcion(admin_client, tipo.id, inicial=200, final=205)

    resp = editar(admin_client, 2, tipo.id, inicial=103, final=108,
                  usuario_id=admin.id)

    text = resp.get_data(as_text=True)
    assert 'solap' in text.lower()
    assert 'Recepción actualizada' not in text
    r2 = db.session.get(RecepcionFolio, 2)
    assert (r2.folioInicial, r2.folioFinal) == (200, 205), 'dejó editar lo bloqueado'
    assert Folio.query.count() == 12, 'no debe crear folios solapados'


# --- editar: bloqueos ---


def test_edit_reduce_bloquea_si_hay_entrega(admin_client, tipo, admin,
                                            centro, operador):
    crear_recepcion(admin_client, tipo.id, inicial=100, final=110)
    folio_110 = Folio.query.filter_by(folio=110).one()
    folio_110.estado = 'entregado'
    db.session.add(EntregaFolio(folio_id=folio_110.id, fechaEntrega=date(2026, 9, 2),
                                centroId=centro.id, userId=operador.id))
    db.session.commit()

    resp = editar(admin_client, 1, tipo.id, final=105, usuario_id=admin.id)

    text = resp.get_data(as_text=True)
    assert 'No se puede editar' in text
    assert 'Recepción actualizada' not in text
    assert unica_recepcion().folioFinal == 110, 'dejó el rango intacto'
    assert Folio.query.count() == 11, 'no debe borrar el folio entregado'


def test_edit_cambiar_anio_bloquea_si_hay_escaneado(admin_client, tipo, admin):
    crear_recepcion(admin_client, tipo.id)
    folio_100 = Folio.query.filter_by(folio=100).one()
    folio_100.escaneado = True
    db.session.commit()

    resp = editar(admin_client, 1, tipo.id, anio=2027, usuario_id=admin.id)

    text = resp.get_data(as_text=True)
    assert 'No se puede editar' in text
    assert unica_recepcion().anioCert == 2026, 'dejó el año intacto'
    assert all(f.anioCert == 2026 for f in Folio.query.all())


def test_edit_con_folio_devuelto_permite_editar_fecha(admin_client, tipo, admin,
                                                      centro, operador):
    """Solo folios reescritos/borrados bloquean: la fecha nunca los toca."""
    crear_recepcion(admin_client, tipo.id)
    folio_105 = Folio.query.filter_by(folio=105).one()
    folio_105.estado = 'devuelto'
    db.session.add(DevolucionFolio(folio_id=folio_105.id,
                                   fechaDevolucion=date(2026, 9, 3),
                                   centroId=centro.id, userId=operador.id))
    db.session.commit()

    resp = editar(admin_client, 1, tipo.id, fecha='2026-10-07',
                  usuario_id=admin.id)

    assert 'Recepción actualizada' in resp.get_data(as_text=True)
    assert unica_recepcion().fecha == date(2026, 10, 7)


# --- eliminar ---


def test_delete_limpio_borra_recepcion_y_folios(admin_client, tipo):
    crear_recepcion(admin_client, tipo.id)
    assert Folio.query.count() == 6

    resp = eliminar(admin_client, 1)

    text = resp.get_data(as_text=True)
    assert 'Recepción eliminada' in text
    assert '6 folios' in text
    assert RecepcionFolio.query.count() == 0
    assert Folio.query.count() == 0
    log = AuditLog.query.filter_by(accion='DELETE',
                                   tabla='recepcion_folios').one()
    assert log.registro_id == 1


def test_delete_bloqueado_si_hay_entrega(admin_client, tipo, centro, operador):
    crear_recepcion(admin_client, tipo.id)
    folio_102 = Folio.query.filter_by(folio=102).one()
    folio_102.estado = 'entregado'
    db.session.add(EntregaFolio(folio_id=folio_102.id, fechaEntrega=date(2026, 9, 2),
                                centroId=centro.id, userId=operador.id))
    db.session.commit()

    resp = eliminar(admin_client, 1)

    text = resp.get_data(as_text=True)
    assert 'No se puede eliminar' in text
    assert 'Recepción eliminada' not in text
    assert RecepcionFolio.query.count() == 1, 'borró con folios en uso'
    assert Folio.query.count() == 6
    assert AuditLog.query.filter_by(accion='DELETE').count() == 0


def test_delete_bloqueado_si_hay_escaneado(admin_client, tipo):
    crear_recepcion(admin_client, tipo.id)
    Folio.query.filter_by(folio=100).one().escaneado = True
    db.session.commit()

    resp = eliminar(admin_client, 1)

    assert 'No se puede eliminar' in resp.get_data(as_text=True)
    assert RecepcionFolio.query.count() == 1
    assert Folio.query.count() == 6


def test_delete_bloqueado_si_estado_no_disponible(admin_client, tipo):
    crear_recepcion(admin_client, tipo.id)
    Folio.query.filter_by(folio=103).one().estado = 'entregado'
    db.session.commit()

    resp = eliminar(admin_client, 1)

    assert 'No se puede eliminar' in resp.get_data(as_text=True)
    assert RecepcionFolio.query.count() == 1


def test_delete_bloqueado_si_estado_devuelto(admin_client, tipo, centro,
                                             operador):
    """El estado != disponible es la fuente de verdad del bloqueo."""
    crear_recepcion(admin_client, tipo.id)
    folio = Folio.query.filter_by(folio=104).one()
    folio.estado = 'devuelto'
    db.session.add(DevolucionFolio(folio_id=folio.id,
                                   fechaDevolucion=date(2026, 9, 3),
                                   centroId=centro.id, userId=operador.id))
    db.session.commit()

    resp = eliminar(admin_client, 1)

    assert 'No se puede eliminar' in resp.get_data(as_text=True)
    assert RecepcionFolio.query.count() == 1
