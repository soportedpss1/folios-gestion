"""Permisos granulares: grants por usuario (solo suman al rol)."""

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.permiso_usuario import PermisoUsuario
from app.services.permisos import PERMISOS, puede
from tests.conftest import make_user


# --- semántica puede() ---


def test_admin_tiene_todos_los_permisos(admin):
    for clave in PERMISOS:
        assert puede(clave, admin), f'admin sin {clave}'


def test_operador_default_solo_edicion(operador):
    assert puede('recepcion.crear', operador)
    assert puede('folios.actualizar', operador)
    assert not puede('usuarios.gestionar', operador)
    assert not puede('centros.importar', operador)
    assert not puede('auditoria.ver', operador)


def test_lectura_sin_grants_no_edita(app):
    lectura = make_user('lectura', 'lectura')
    for clave in PERMISOS:
        assert not puede(clave, lectura), f'lectura no debe tener {clave}'


def test_grant_suma_al_rol(app):
    lectura = make_user('lectura', 'lectura')
    assert not puede('centros.gestionar', lectura)
    db.session.add(PermisoUsuario(user_id=lectura.id, permiso='centros.gestionar'))
    db.session.commit()
    assert puede('centros.gestionar', lectura)
    assert not puede('centros.importar', lectura), 'un grant no abre otra clave'


def test_clave_desconocida_false(admin):
    assert not puede('no.existe', admin)


def test_anonimo_false():
    class _Anon:
        is_authenticated = False
    assert not puede('recepcion.crear', _Anon())


# --- rutas del módulo ---


def test_rutas_requieren_login(client):
    assert client.get('/permisos/').status_code == 302
    assert client.get('/permisos/1').status_code == 302


def test_operador_bloqueado(auth_client):
    resp = auth_client.get('/permisos/', follow_redirects=True)
    assert resp.status_code == 200
    assert 'No tiene permisos' in resp.get_data(as_text=True)
    assert '/dashboard' in resp.request.path


def test_lectura_bloqueado(client, app):
    make_user('lectura', 'lectura')
    client.post('/auth/login', data={'username': 'lectura', 'password': 'pass12345'})
    resp = client.get('/permisos/', follow_redirects=True)
    assert 'No tiene permisos' in resp.get_data(as_text=True)


def test_admin_ve_lista(admin_client):
    resp = admin_client.get('/permisos/')
    assert resp.status_code == 200
    assert 'adminuser' in resp.get_data(as_text=True)


def test_admin_abre_gestion(admin_client, operador):
    resp = admin_client.get(f'/permisos/{operador.id}')
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert 'permiso_centros_gestionar' in text
    assert 'Permisos concedidos' in text


def test_checkbox_marcado_si_hay_grant(admin_client, operador):
    db.session.add(PermisoUsuario(user_id=operador.id, permiso='centros.importar'))
    db.session.commit()
    text = admin_client.get(f'/permisos/{operador.id}').get_data(as_text=True)
    import re
    campo = re.search(
        r'<input[^>]*name="permiso_centros_importar"[^>]*>', text)
    assert campo, 'campo del grant ausente'
    assert 'checked' in campo.group(0), 'grant existente no se refleja'


# --- guardar ---


def test_admin_guarda_rol_y_grants(admin_client, operador):
    resp = admin_client.post(f'/permisos/{operador.id}', data={
        'rol': 'lectura',
        'activo': 'y',
        'permiso_centros_gestionar': 'y',
        'permiso_recepcion_crear': 'y',
    }, follow_redirects=True)

    assert resp.status_code == 200
    db.session.refresh(operador)
    assert operador.rol == 'lectura'
    grants = {p.permiso for p in PermisoUsuario.query.filter_by(user_id=operador.id)}
    assert grants == {'centros.gestionar', 'recepcion.crear'}

    log = AuditLog.query.filter_by(tabla='permiso_usuarios',
                                   registro_id=operador.id).one()
    assert log.accion == 'UPDATE'
    assert 'centros.gestionar' in log.datos_nuevos['grants']


def test_repost_sin_casillas_retira_grants(admin_client, operador):
    db.session.add(PermisoUsuario(user_id=operador.id, permiso='centros.importar'))
    db.session.commit()

    admin_client.post(f'/permisos/{operador.id}', data={
        'rol': 'operador', 'activo': 'y',
    }, follow_redirects=True)

    assert PermisoUsuario.query.filter_by(user_id=operador.id).count() == 0


def test_ultimo_admin_no_se_degrada(admin_client, admin):
    resp = admin_client.post(f'/permisos/{admin.id}', data={
        'rol': 'operador', 'activo': 'y',
    }, follow_redirects=True)

    text = resp.get_data(as_text=True)
    assert 'último administrador' in text
    db.session.refresh(admin)
    assert admin.rol == 'admin'


# --- efecto end-to-end del grant ---


def test_grant_habilita_ruta_admin(client, app):
    lectura = make_user('lectura', 'lectura')
    db.session.add(PermisoUsuario(user_id=lectura.id, permiso='centros.gestionar'))
    db.session.commit()
    client.post('/auth/login', data={'username': 'lectura', 'password': 'pass12345'})

    resp = client.get('/centros/create')
    assert resp.status_code == 200, 'grant debió habilitar el formulario'


def test_sin_grant_ruta_admin_bloqueada(auth_client, operador):
    resp = auth_client.get('/centros/create', follow_redirects=True)
    assert 'No tiene permisos' in resp.get_data(as_text=True)


def test_grant_usuarios_gestionar_abre_usuarios(client, app):
    lectura = make_user('lectura', 'lectura')
    db.session.add(PermisoUsuario(user_id=lectura.id, permiso='usuarios.gestionar'))
    db.session.commit()
    client.post('/auth/login', data={'username': 'lectura', 'password': 'pass12345'})

    resp = client.get('/usuarios/')
    assert resp.status_code == 200


def test_grant_importar_recepcion(client, app):
    lectura = make_user('lectura', 'lectura')
    db.session.add(PermisoUsuario(user_id=lectura.id, permiso='recepcion.importar'))
    db.session.commit()
    client.post('/auth/login', data={'username': 'lectura', 'password': 'pass12345'})

    assert client.get('/recepcion/importar').status_code == 200
    assert client.get('/recepcion/create').status_code == 302, \
        'el grant de importar no habilita crear recepciones'


# --- sidebar ---


def test_sidebar_permisos_visible_admin(admin_client):
    assert '/permisos' in admin_client.get('/dashboard/').get_data(as_text=True)


def test_sidebar_permisos_oculto_operador(auth_client):
    assert '/permisos' not in auth_client.get('/dashboard/').get_data(as_text=True)
