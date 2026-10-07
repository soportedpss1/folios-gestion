"""Módulo de escaneos: subir JPG de folios y marcarlos como escaneados."""

import os
from io import BytesIO

import pytest
from werkzeug.datastructures import FileStorage

from app.config import Config
from app.extensions import db
from app.models.audit_log import AuditLog
from app.services.escaneos import guardar_y_matchear, validar_carpeta
from app.services.permisos import PERMISOS, puede
from tests.conftest import make_folio, make_user


def test_permiso_escaneos_existe_y_es_edit():
    assert 'escaneos.subir' in PERMISOS
    assert PERMISOS['escaneos.subir'] == ('Subir escaneos', 'edit')


def test_permiso_escaneos_por_rol(app):
    operador = make_user('operador', 'operador')
    lectura = make_user('lector', 'lectura')
    assert puede('escaneos.subir', operador) is True
    assert puede('escaneos.subir', lectura) is False


def test_config_scans_folder():
    assert Config.SCANS_FOLDER.endswith('scans')
    assert os.path.isabs(Config.SCANS_FOLDER)


@pytest.fixture()
def scans_dir(app, tmp_path):
    """Apunta SCANS_FOLDER a un tmp por test: nada toca la carpeta real."""
    path = tmp_path / 'scans'
    app.config['SCANS_FOLDER'] = str(path)
    return path


def jpg(nombre, data=b'JPEGDATA'):
    return FileStorage(stream=BytesIO(data), filename=nombre)


def test_servicio_guarda_y_marca(app, tipo, scans_dir):
    folio = make_folio(tipo, anio=2026, numero=1000)
    db.session.commit()
    with app.test_request_context():
        reporte = guardar_y_matchear([jpg('1000.jpg')], 2026, folio.id)
    assert reporte['marcados'] == 1
    assert reporte['resultados'][0]['estado'] == 'marcado'
    assert reporte['resultados'][0]['folios'] == 1
    assert folio.escaneado is True
    assert (scans_dir / '2026' / '1000.jpg').read_bytes() == b'JPEGDATA'


def test_servicio_marca_todos_los_tipos(app, tipo, scans_dir):
    from app.models.tipo_certificado import TipoCertificado
    otro = TipoCertificado(name='Nacimientos', color='#0D6EFD', activo=True)
    db.session.add(otro)
    db.session.commit()
    f1 = make_folio(tipo, anio=2026, numero=1000)
    f2 = make_folio(otro, anio=2026, numero=1000, rangoId=2)
    db.session.commit()
    with app.test_request_context():
        reporte = guardar_y_matchear([jpg('1000.jpg')], 2026, 1)
    assert f1.escaneado is True
    assert f2.escaneado is True
    assert reporte['resultados'][0]['folios'] == 2


def test_servicio_sin_coincidencia_guarda_igual(app, scans_dir):
    with app.test_request_context():
        reporte = guardar_y_matchear([jpg('9999.jpg')], 2026, 1)
    assert reporte['sin_coincidencia'] == 1
    assert reporte['marcados'] == 0
    assert (scans_dir / '2026' / '9999.jpg').exists()


def test_servicio_nombres_invalidos_no_escriben(app, scans_dir):
    invalidos = ['1000 copia.jpg', '../../1000.jpg', 'abc.jpg',
                 '1000.png', '1000', '.jpg']
    with app.test_request_context():
        reporte = guardar_y_matchear([jpg(n) for n in invalidos], 2026, 1)
    assert reporte['invalidos'] == len(invalidos)
    assert reporte['resultados'][0]['estado'] == 'nombre_invalido'
    assert not scans_dir.exists(), 'ningún inválido debe crear la carpeta'


def test_servicio_nombre_con_demasiados_digitos_no_crashea(app, scans_dir):
    # >4300 dígitos: int() lanzaría ValueError (límite CPython) y abortaría el
    # lote. Con el gate de 1-10 dígitos el nombre queda inválido y el resto sigue.
    nombre_largo = '9' * 5000 + '.jpg'
    with app.test_request_context():
        reporte = guardar_y_matchear(
            [jpg(nombre_largo), jpg('1000.jpg')], 2026, 1)
    assert reporte['invalidos'] == 1
    assert reporte['resultados'][0]['estado'] == 'nombre_invalido'
    assert (scans_dir / '2026' / '1000.jpg').exists(), \
        'el válido del mismo lote debe procesarse igual'


def test_servicio_mayusculas_y_jpeg_aceptados(app, tipo, scans_dir):
    folio = make_folio(tipo, anio=2026, numero=1001)
    db.session.commit()
    with app.test_request_context():
        guardar_y_matchear([jpg('1001.JPG'), jpg('1001.jpeg')], 2026, 1)
    assert folio.escaneado is True
    # El destino se reconstruye desde el número: siempre <numero>.jpg
    assert (scans_dir / '2026' / '1001.jpg').exists()


def test_servicio_sobrescribe(app, scans_dir):
    with app.test_request_context():
        guardar_y_matchear([jpg('1000.jpg', b'UNO')], 2026, 1)
        guardar_y_matchear([jpg('1000.jpg', b'DOS')], 2026, 1)
    assert (scans_dir / '2026' / '1000.jpg').read_bytes() == b'DOS'


def test_servicio_anio_distinto_no_matchea(app, tipo, scans_dir):
    folio = make_folio(tipo, anio=2025, numero=1000)
    db.session.commit()
    with app.test_request_context():
        reporte = guardar_y_matchear([jpg('1000.jpg')], 2026, 1)
    assert reporte['sin_coincidencia'] == 1
    assert folio.escaneado is False
    assert (scans_dir / '2026' / '1000.jpg').exists(), 'el archivo va al año pedido'


def test_servicio_audita_solo_cambio(app, tipo, scans_dir):
    folio = make_folio(tipo, anio=2026, numero=1000)
    db.session.commit()
    with app.test_request_context():
        guardar_y_matchear([jpg('1000.jpg')], 2026, 1)
        primera = AuditLog.query.filter_by(tabla='folios', registro_id=folio.id).count()
        guardar_y_matchear([jpg('1000.jpg')], 2026, 1)
        segunda = AuditLog.query.filter_by(tabla='folios', registro_id=folio.id).count()
    assert primera == 1, 'el primer marcado debe auditar'
    assert segunda == 1, 're-subir no debe duplicar el log'


def escribir(scans_dir, anio, nombre):
    """Crea un JPG directamente en la carpeta (simula subida externa/FTP)."""
    carpeta = scans_dir / str(anio)
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / nombre).write_bytes(b'IMG')


# --- validar_carpeta: reconciliar scans/ contra la DB ---


def test_validar_marca_desde_carpeta(app, tipo, scans_dir):
    folio = make_folio(tipo, anio=2026, numero=1000)
    db.session.commit()
    escribir(scans_dir, 2026, '1000.jpg')
    with app.test_request_context():
        reporte = validar_carpeta(1)
    assert folio.escaneado is True
    assert reporte['marcados'] == 1
    assert reporte['desmarcados'] == 0
    log = AuditLog.query.filter_by(
        tabla='folios', registro_id=folio.id).one()
    assert log.datos_anteriores == {'escaneado': False}
    assert log.datos_nuevos == {'escaneado': True}


def test_validar_desmarca_si_carpeta_del_anio_existe_vacia(app, tipo, scans_dir):
    folio = make_folio(tipo, anio=2026, numero=1000, escaneado=True)
    db.session.commit()
    (scans_dir / '2026').mkdir(parents=True)  # carpeta existe, sin archivos
    with app.test_request_context():
        reporte = validar_carpeta(1)
    assert folio.escaneado is False, 'carpeta existente sin archivo ⇒ desmarcar'
    assert reporte['desmarcados'] == 1
    log = AuditLog.query.filter_by(
        tabla='folios', registro_id=folio.id).one()
    assert log.datos_anteriores == {'escaneado': True}
    assert log.datos_nuevos == {'escaneado': False}


def test_validar_no_desmarca_si_falta_carpeta_de_anio(app, tipo, scans_dir):
    # Raíz existe pero sin subcarpeta 2026: volumen a medio montar no debe
    # borrar los marcados de ese año.
    folio = make_folio(tipo, anio=2026, numero=1000, escaneado=True)
    db.session.commit()
    scans_dir.mkdir(parents=True)
    with app.test_request_context():
        reporte = validar_carpeta(1)
    assert folio.escaneado is True
    assert reporte['desmarcados'] == 0
    assert reporte['anios_sin_carpeta'] == [2026]


def test_validar_sin_carpeta_raiz_no_toca_nada(app, tipo, scans_dir):
    folio = make_folio(tipo, anio=2026, numero=1000, escaneado=True)
    db.session.commit()
    assert not scans_dir.exists()
    with app.test_request_context():
        reporte = validar_carpeta(1)
    assert reporte['error_raiz'] is True
    assert folio.escaneado is True, 'sin carpeta raíz no se desmarca nada'
    assert reporte['marcados'] == 0
    assert reporte['desmarcados'] == 0
    assert AuditLog.query.count() == 0


def test_validar_ignora_archivos_invalidos_y_de_la_raiz(app, tipo, scans_dir):
    folio = make_folio(tipo, anio=2026, numero=1000)
    db.session.commit()
    escribir(scans_dir, 2026, '1000.jpg')
    escribir(scans_dir, 2026, 'copia 2026.jpg')   # nombre inválido
    (scans_dir / 'suelto.jpg').write_bytes(b'X')   # suelto en la raíz
    with app.test_request_context():
        reporte = validar_carpeta(1)
    assert folio.escaneado is True, 'el inválido no aborta la validación'
    assert reporte['archivos'] == 1
    assert reporte['ignorados'] == 2


def test_validar_idempotente_audita_solo_cambio(app, tipo, scans_dir):
    folio = make_folio(tipo, anio=2026, numero=1000)
    db.session.commit()
    escribir(scans_dir, 2026, '1000.jpg')
    with app.test_request_context():
        validar_carpeta(1)
        validar_carpeta(1)
    logs = AuditLog.query.filter_by(tabla='folios', registro_id=folio.id)
    assert logs.count() == 1, 're-validar no debe duplicar el log'


# --- botón / endpoint en el módulo de folios ---


def test_validar_endpoint_requiere_login(client):
    assert client.post('/folios/validar-escaneados').status_code == 302


def test_validar_endpoint_sin_permiso_redirige(client):
    make_user('lector', 'lectura')
    client.post('/auth/login',
                data={'username': 'lector', 'password': 'pass12345'})
    resp = client.post('/folios/validar-escaneados', follow_redirects=True)
    assert resp.status_code == 200
    assert 'No tiene permisos' in resp.get_data(as_text=True)


def test_validar_endpoint_marca_y_flash(auth_client, folio, scans_dir):
    escribir(scans_dir, 2026, '1000.jpg')
    resp = auth_client.post('/folios/validar-escaneados',
                            follow_redirects=True)
    assert resp.status_code == 200
    assert folio.escaneado is True
    text = resp.get_data(as_text=True)
    assert 'Validación completada' in text
    assert '1 folio marcado' in text


def test_validar_endpoint_sin_carpeta_flash_error(auth_client, folio, scans_dir):
    folio.escaneado = True
    db.session.commit()
    resp = auth_client.post('/folios/validar-escaneados',
                            follow_redirects=True)
    assert resp.status_code == 200
    assert 'No existe la carpeta de escaneados' in resp.get_data(as_text=True)
    assert folio.escaneado is True


# Nota: un solo usuario por test. El fixture `app` mantiene un app context
# activo y Flask lo reusa en cada request ⇒ `g._login_user` (caché de
# Flask-Login) se comparte entre clients del mismo test: un segundo login
# vería al usuario anterior. Con un solo client por test, `g` nace limpio.
def test_boton_visible_para_operador(auth_client):
    text = auth_client.get('/folios/').get_data(as_text=True)
    assert 'Validar Escaneados' in text


def test_boton_oculto_para_lectura(client):
    make_user('lector', 'lectura')
    client.post('/auth/login',
                data={'username': 'lector', 'password': 'pass12345'})
    text = client.get('/folios/').get_data(as_text=True)
    assert 'Validar Escaneados' not in text, \
        'lectura no debe ver el botón (no tiene escaneos.subir)'


def post_subir(client, anio, archivos):
    """archivos: lista de (nombre, contenido_bytes)."""
    data = {
        'anio': anio,
        'archivos': [(BytesIO(contenido), nombre) for nombre, contenido in archivos],
    }
    return client.post('/escaneos/subir', data=data,
                       content_type='multipart/form-data')


def test_subir_requiere_login(client):
    assert client.get('/escaneos/subir').status_code == 302


def test_subir_sin_permiso_redirige(client):
    from tests.conftest import make_user
    make_user('lector', 'lectura')
    client.post('/auth/login', data={'username': 'lector', 'password': 'pass12345'})
    resp = client.get('/escaneos/subir', follow_redirects=True)
    assert resp.status_code == 200
    assert 'No tiene permisos' in resp.get_data(as_text=True)


def test_subir_muestra_form(auth_client):
    resp = auth_client.get('/escaneos/subir')
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert 'Subir Escaneos' in text
    assert 'multiple' in text  # input multi-archivo


def test_subir_marca_folio(auth_client, folio, scans_dir):
    resp = post_subir(auth_client, folio.anioCert, [('1000.jpg', b'IMG')])
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert 'Marcado' in text
    assert folio.escaneado is True
    assert (scans_dir / '2026' / '1000.jpg').exists()


def test_subir_sin_anio_no_escribe(auth_client, folio, scans_dir):
    resp = post_subir(auth_client, '', [('1000.jpg', b'IMG')])
    assert 'Seleccione un año' in resp.get_data(as_text=True)
    assert folio.escaneado is False
    assert not scans_dir.exists()


def test_subir_anio_inexistente_no_escribe(auth_client, folio, scans_dir):
    resp = post_subir(auth_client, 1999, [('1000.jpg', b'IMG')])
    assert 'Not a valid choice' in resp.get_data(as_text=True)
    assert folio.escaneado is False
    assert not scans_dir.exists()


def test_subir_archivo_repetido_en_lote(auth_client, folio, scans_dir):
    # Dos archivos con el mismo número en un mismo request: gana el último
    # (sobrescritura) y el folio queda marcado igual.
    resp = post_subir(auth_client, 2026,
                      [('1000.jpg', b'UNO'), ('1000.jpg', b'DOS')])
    assert resp.status_code == 200
    assert folio.escaneado is True
    assert (scans_dir / '2026' / '1000.jpg').read_bytes() == b'DOS'


def test_subir_lote_mixto(auth_client, folio, scans_dir):
    resp = post_subir(auth_client, 2026, [
        ('1000.jpg', b'OK'),      # match → marcado
        ('nada.jpg', b'X'),       # nombre inválido → no se escribe
        ('9999.jpg', b'Y'),       # sin folio → guardado, sin coincidencia
    ])
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert folio.escaneado is True, 'un inválido no aborta el lote'
    assert (scans_dir / '2026' / '9999.jpg').exists()
    assert not (scans_dir / '2026' / 'nada.jpg').exists()
    assert 'Nombre inválido' in text
    assert 'Sin coincidencia' in text


def test_subir_lote_mixto_con_png(auth_client, folio, scans_dir):
    # Un .png en el lote no debe rechazar el request completo: el JPG válido
    # se guarda y el folio se marca; el .png se reporta como nombre inválido
    # sin escribir nada en disco.
    resp = post_subir(auth_client, 2026, [
        ('escaneo.png', b'PNGDATA'),  # extensión no permitida → inválido
        ('1000.jpg', b'OK'),          # match → marcado
    ])
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert folio.escaneado is True, 'un no-JPG no aborta el lote'
    assert (scans_dir / '2026' / '1000.jpg').read_bytes() == b'OK'
    assert not (scans_dir / '2026' / 'escaneo.png').exists()
    assert not (scans_dir / '2026' / 'escaneo.jpg').exists()
    assert 'Nombre inválido' in text
