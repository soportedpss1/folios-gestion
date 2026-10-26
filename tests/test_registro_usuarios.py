"""Registro público de operadores + aprobación por administrador."""

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.permiso_usuario import PermisoUsuario
from app.models.usuario import Usuario
from tests.conftest import make_user

REGISTRO = {'name': 'Nuevo Usuario', 'username': 'nuevo',
            'email': 'nuevo@example.com', 'password': 'secret123',
            'confirm_password': 'secret123'}


def make_inactivo(username='pendiente'):
    """Usuario operador sin aprobar (como lo crea el registro)."""
    user = Usuario(name='Pendiente Test', username=username,
                   email=f'{username}@test.local', rol='operador',
                   activo=False)
    user.set_password('pass12345')
    db.session.add(user)
    db.session.commit()
    return user


def test_login_muestra_link_de_registro(client):
    html = client.get('/auth/login').get_data(as_text=True)
    assert 'Crear una cuenta' in html, 'falta el link al registro en el login'
    assert '/auth/registro' in html


def test_registro_crea_operador_inactivo(client, app):
    resp = client.post('/auth/registro', data=REGISTRO, follow_redirects=True)
    html = resp.get_data(as_text=True)
    assert 'Un administrador debe aprobarla' in html, 'sin flash de pendiente'
    user = Usuario.query.filter_by(username='nuevo').one()
    assert user.rol == 'operador'
    assert user.activo is False, 'la cuenta nace sin aprobar (activo=False)'
    assert user.check_password('secret123')
    # /dashboard/ sin barra: 308 de strict_slashes antes del view; el punto
    # es que el view responde con el redirect a login (302), no 200.
    assert client.get('/dashboard/').status_code == 302, 'el registro creó sesión'


def test_registro_autenticado_redirige_a_dashboard(auth_client, app):
    resp = auth_client.get('/auth/registro')
    assert resp.status_code == 302
    assert '/dashboard' in resp.headers['Location'], \
        'autenticado no debe ver el formulario de registro'


def test_registro_duplicado_no_crea(client, app):
    client.post('/auth/registro', data=REGISTRO, follow_redirects=True)
    otro = dict(REGISTRO, email='otro@example.com')
    resp = client.post('/auth/registro', data=otro, follow_redirects=True)
    assert 'ya está en uso' in resp.get_data(as_text=True)
    assert Usuario.query.filter_by(username='nuevo').count() == 1


def test_registro_datos_invalidos_no_crea(client, app):
    malo = dict(REGISTRO, email='no-es-email', password='corto',
                confirm_password='distinto')
    resp = client.post('/auth/registro', data=malo, follow_redirects=True)
    assert resp.status_code == 200
    assert Usuario.query.count() == 0


def test_registro_rate_limit_solo_post(limiter_client):
    statuses = []
    for i in range(6):
        resp = limiter_client.post(
            '/auth/registro',
            data=dict(REGISTRO, username=f'user{i}',
                      email=f'user{i}@example.com'),
        )
        statuses.append(resp.status_code)
    assert statuses[-1] == 429, f'esperaba 429 en la 6ª petición, llegó {statuses}'
    assert limiter_client.get('/auth/registro').status_code == 200, \
        'el GET del formulario no consume la cuota del rate limit'


def test_registro_deja_audit_insert(client, app):
    client.post('/auth/registro', data=REGISTRO, follow_redirects=True)
    user = Usuario.query.filter_by(username='nuevo').one()
    from app.models.audit_log import AuditLog
    log = AuditLog.query.filter_by(
        user_id=user.id, accion='INSERT', tabla='usuarios',
        registro_id=user.id).one()
    assert log.datos_nuevos['activo'] is False


def test_login_cuenta_inactiva_mensaje_combinado(client, app):
    make_inactivo('pendiente1')
    resp = client.post('/auth/login', data={
        'username': 'pendiente1', 'password': 'pass12345',
    }, follow_redirects=True)
    html = resp.get_data(as_text=True)
    assert ('Su cuenta no está activa. Si acaba de registrarse, un '
            'administrador debe aprobarla') in html, \
        'falta el mensaje combinado para cuenta inactiva'
    assert client.get('/dashboard/').status_code == 302, 'creó sesión igual'


def test_login_inactiva_password_mala_es_generico(client, app):
    make_inactivo('pendiente2')
    resp = client.post('/auth/login', data={
        'username': 'pendiente2', 'password': 'mala',
    }, follow_redirects=True)
    html = resp.get_data(as_text=True)
    assert 'Usuario o contraseña incorrectos.' in html
    assert 'no está activa' not in html, \
        'sin contraseña correcta no se filtra el estado de la cuenta'


def test_aprobar_activa_cuenta_y_audita(admin_client, app, admin):
    user = make_inactivo('pendiente3')
    resp = admin_client.post(f'/usuarios/{user.id}/aprobar',
                             follow_redirects=True)
    assert 'Usuario aprobado exitosamente.' in resp.get_data(as_text=True)
    db.session.refresh(user)
    assert user.activo is True, 'aprobar no activó la cuenta'
    log = AuditLog.query.filter_by(
        accion='UPDATE', tabla='usuarios', registro_id=user.id).one()
    assert log.user_id == admin.id, 'el audit debe tener al admin como actor'
    assert log.datos_anteriores == {'activo': False}
    assert log.datos_nuevos == {'activo': True}


def test_aprobar_sin_sesion_no_activa(client, app):
    user = make_inactivo('pendiente4')
    resp = client.post(f'/usuarios/{user.id}/aprobar')
    assert resp.status_code == 302
    assert db.session.get(Usuario, user.id).activo is False


def test_aprobar_operador_sin_permiso_no_activa(auth_client, app):
    user = make_inactivo('pendiente5')
    resp = auth_client.post(f'/usuarios/{user.id}/aprobar',
                            follow_redirects=True)
    assert 'No tiene permisos' in resp.get_data(as_text=True)
    db.session.refresh(user)
    assert user.activo is False


def test_aprobar_con_grant_usuarios_gestionar(client, app):
    lector = make_user('lector_aprueba', 'lectura')
    db.session.add(PermisoUsuario(user_id=lector.id,
                                  permiso='usuarios.gestionar'))
    db.session.commit()
    user = make_inactivo('pendiente6')
    client.post('/auth/login',
                data={'username': 'lector_aprueba', 'password': 'pass12345'})
    resp = client.post(f'/usuarios/{user.id}/aprobar', follow_redirects=True)
    assert 'Usuario aprobado exitosamente.' in resp.get_data(as_text=True)
    db.session.refresh(user)
    assert user.activo is True, 'un grant de usuarios.gestionar debe aprobar'


def test_aprobar_ya_activo_es_idempotente(admin_client, app):
    activo = make_user('activo_existente', 'operador')
    resp = admin_client.post(f'/usuarios/{activo.id}/aprobar',
                             follow_redirects=True)
    assert 'Ese usuario ya está activo.' in resp.get_data(as_text=True)
    assert AuditLog.query.filter_by(
        accion='UPDATE', tabla='usuarios', registro_id=activo.id).count() == 0, \
        'reaprobación no debe escribir audit'


def test_index_muestra_boton_aprobar_solo_inactivos(admin_client, app):
    inactivo = make_inactivo('pendiente7')
    html = admin_client.get('/usuarios/').get_data(as_text=True)
    assert f'aria-label="Aprobar usuario {inactivo.username}"' in html, \
        'sin botón de aprobación para el inactivo'
    assert 'Aprobar usuario adminuser' not in html, \
        'los activos no llevan botón de aprobar'
