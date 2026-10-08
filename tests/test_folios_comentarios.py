"""Comentarios en el detalle del folio: historial con autor, edición y borrado."""

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.folio_comentario import FolioComentario
from tests.conftest import make_user


def get(client, ruta):
    resp = client.get(ruta)
    assert resp.status_code == 200, f'{ruta} devolvió {resp.status_code}'
    return resp.get_data(as_text=True)


def comentar(app, folio, user, texto='Folio con mancha en el margen'):
    comentario = FolioComentario(folio_id=folio.id, user_id=user.id, texto=texto)
    db.session.add(comentario)
    db.session.commit()
    return comentario


def login(client, user):
    resp = client.post(
        '/auth/login',
        data={'username': user.username, 'password': 'pass12345'},
    )
    assert resp.status_code == 302, 'login de prueba falló'
    return client


def test_detalle_muestra_formulario_y_estado_vacio(auth_client, folio):
    text = get(auth_client, f'/folios/{folio.id}')
    assert 'Comentarios' in text
    assert 'name="texto"' in text, 'falta el textarea del form'
    assert 'Aún no hay comentarios' in text


def test_crear_comentario(app, auth_client, folio, operador):
    resp = auth_client.post(
        f'/folios/{folio.id}/comentarios',
        data={'texto': 'Folio dañado en la esquina'},
    )
    assert resp.status_code == 302
    assert '#comentarios' in resp.headers['Location'], 'el redirect ancla a la sección'

    text = get(auth_client, f'/folios/{folio.id}')
    assert 'Folio dañado en la esquina' in text
    assert operador.username in text, 'el autor se muestra'
    assert FolioComentario.query.count() == 1


def test_lectura_tambien_puede_comentar(app, folio, client):
    lector = make_user('lector', 'lectura')
    login(client, lector)
    resp = client.post(
        f'/folios/{folio.id}/comentarios',
        data={'texto': 'Anotación del rol lectura'},
    )
    assert resp.status_code == 302
    assert FolioComentario.query.count() == 1, 'cualquier rol autenticado comenta'


def test_texto_largo_rechazado(app, auth_client, folio):
    resp = auth_client.post(
        f'/folios/{folio.id}/comentarios',
        data={'texto': 'x' * 1001},
    )
    assert resp.status_code == 200, 're-render del detalle con el error'
    assert FolioComentario.query.count() == 0, 'el texto largo no se guarda'


def test_texto_vacio_rechazado(app, auth_client, folio):
    resp = auth_client.post(f'/folios/{folio.id}/comentarios', data={'texto': '   '})
    assert resp.status_code == 200
    assert FolioComentario.query.count() == 0


def test_editar_solo_autor(app, auth_client, folio, operador):
    c = comentar(app, folio, operador)
    resp = auth_client.post(
        f'/folios/comentarios/{c.id}/editar',
        data={'texto': 'Texto corregido por el autor'},
    )
    assert resp.status_code == 302
    db.session.refresh(c)
    assert c.texto == 'Texto corregido por el autor'

    text = get(auth_client, f'/folios/{folio.id}')
    assert 'Texto corregido' in text
    assert 'Editado' in text, 'se marca como editado (updateAt != createAt)'


def test_editar_otro_usuario_no_puede(app, client, folio, operador):
    # Un solo login por test (g._login_user se comparte entre clients):
    # el autor solo existe en DB y el cliente inicia sesión como el "otro".
    c = comentar(app, folio, operador)
    otro = make_user('otrousuario', 'operador')
    login(client, otro)
    resp = client.post(
        f'/folios/comentarios/{c.id}/editar',
        data={'texto': 'texto no autorizado'},
    )
    assert resp.status_code == 302, 'denegación por flash + redirect (patrón del código)'
    db.session.refresh(c)
    assert c.texto == 'Folio con mancha en el margen', 'el texto no cambió'


def test_borrar_autor(app, auth_client, folio, operador):
    c = comentar(app, folio, operador)
    resp = auth_client.post(f'/folios/comentarios/{c.id}/borrar')
    assert resp.status_code == 302
    assert FolioComentario.query.count() == 0


def test_admin_borra_comentario_ajeno(app, admin_client, folio, operador):
    c = comentar(app, folio, operador)
    resp = admin_client.post(f'/folios/comentarios/{c.id}/borrar')
    assert resp.status_code == 302
    assert FolioComentario.query.count() == 0


def test_borrar_otro_usuario_no_puede(app, client, folio, operador):
    # Mismo patrón: un solo login (el autor nunca inicia sesión).
    c = comentar(app, folio, operador)
    otro = make_user('otro2', 'operador')
    login(client, otro)
    resp = client.post(f'/folios/comentarios/{c.id}/borrar')
    assert resp.status_code == 302
    assert FolioComentario.query.count() == 1, 'el comentario no se borró'


def test_borrar_pide_confirmacion(app, auth_client, folio, operador):
    comentar(app, folio, operador)
    text = get(auth_client, f'/folios/{folio.id}')
    assert 'data-confirm' in text
    assert 'data-icon="danger"' in text


def test_anonimo_no_acede(app, folio):
    resp = app.test_client().post(
        f'/folios/{folio.id}/comentarios', data={'texto': 'hola'})
    assert resp.status_code == 302
    assert '/auth/login' in resp.headers['Location']


def test_auditoria_insert_y_delete(app, auth_client, folio, operador):
    resp = auth_client.post(
        f'/folios/{folio.id}/comentarios', data={'texto': 'audit test'})
    assert resp.status_code == 302
    c = FolioComentario.query.one()
    inserts = AuditLog.query.filter_by(
        accion='INSERT', tabla='folio_comentarios', registro_id=c.id).all()
    assert inserts, 'INSERT auditado'

    resp = auth_client.post(f'/folios/comentarios/{c.id}/borrar')
    assert resp.status_code == 302
    deletes = AuditLog.query.filter_by(
        accion='DELETE', tabla='folio_comentarios', registro_id=c.id).all()
    assert deletes, 'DELETE auditado'
