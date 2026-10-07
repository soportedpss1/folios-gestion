import pytest

import init_db
from app.models.usuario import Usuario


@pytest.fixture()
def patched_init_db(app, monkeypatch):
    """Hace que init_database() use la app de prueba (sqlite) en vez de MySQL."""
    monkeypatch.setattr(init_db, 'create_app', lambda *a, **k: app)
    return init_db.init_database


def test_admin_no_usa_password_por_defecto(patched_init_db, app):
    patched_init_db()

    admin = Usuario.query.filter_by(username='admin').first()
    assert admin is not None, 'no se creó el usuario admin'
    assert not admin.check_password('admin123'), (
        'el usuario admin queda con la credencial por defecto admin123'
    )


def test_init_db_es_idempotente(patched_init_db, app):
    patched_init_db()
    first_hash = Usuario.query.filter_by(username='admin').one().password_hash

    patched_init_db()

    assert Usuario.query.filter_by(username='admin').count() == 1
    assert Usuario.query.filter_by(username='admin').one().password_hash == first_hash


def test_init_db_crea_tipos_de_certificado(patched_init_db, app):
    patched_init_db()
    from app.models.tipo_certificado import TipoCertificado
    assert TipoCertificado.query.count() == 4
