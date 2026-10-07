"""Módulo de escaneos: subir JPG de folios y marcarlos como escaneados."""

import os
from io import BytesIO

import pytest
from werkzeug.datastructures import FileStorage

from app.config import Config
from app.extensions import db
from app.models.audit_log import AuditLog
from app.services.escaneos import guardar_y_matchear
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
