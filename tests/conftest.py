import os

# Must be set before importing app.config (raises if SECRET_KEY missing).
os.environ.setdefault('SECRET_KEY', 'test-secret-key-not-for-production')

import pytest
from datetime import date
from sqlalchemy.pool import StaticPool

from app import create_app
from app.extensions import db
from app.models.usuario import Usuario
from app.models.centro import Centro
from app.models.tipo_certificado import TipoCertificado
from app.models.folio import Folio
from app.models.entrega_folio import EntregaFolio


class TestConfig:
    TESTING = True
    DEBUG = False
    PROPAGATE_EXCEPTIONS = False  # let error handlers run so tests see real status codes
    SECRET_KEY = 'test-secret-key-not-for-production'
    SQLALCHEMY_DATABASE_URI = 'sqlite://'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'poolclass': StaticPool,
        'connect_args': {'check_same_thread': False},
    }
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'


@pytest.fixture()
def app():
    application = create_app(TestConfig)
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def make_user(username='operador', rol='operador', password='pass12345'):
    user = Usuario(
        name=username.title(),
        username=username,
        email=f'{username}@test.local',
        rol=rol,
        activo=True,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def operador(app):
    return make_user('operador', 'operador')


@pytest.fixture()
def admin(app):
    return make_user('adminuser', 'admin')


@pytest.fixture()
def auth_client(client, operador):
    resp = client.post(
        '/auth/login',
        data={'username': operador.username, 'password': 'pass12345'},
    )
    assert resp.status_code == 302, 'login de prueba falló'
    return client


@pytest.fixture()
def admin_client(client, admin):
    """Cliente con sesión de administrador (importar es solo admin)."""
    resp = client.post(
        '/auth/login',
        data={'username': admin.username, 'password': 'pass12345'},
    )
    assert resp.status_code == 302, 'login de admin falló'
    return client


@pytest.fixture()
def centro(app):
    centro = Centro(name='Centro de Prueba', telefono='5555555',
                    direccion='Calle Falsa 123', activo=True)
    db.session.add(centro)
    db.session.commit()
    return centro


@pytest.fixture()
def tipo(app):
    tipo = TipoCertificado(name='Defunciones', color='#0D6EFD', activo=True)
    db.session.add(tipo)
    db.session.commit()
    return tipo


def make_folio(tipo, anio=2026, numero=1000, estado='disponible', **kwargs):
    folio = Folio(
        rangoId=kwargs.pop('rangoId', 1),
        anioCert=anio,
        tipoCert_id=tipo.id,
        folio=numero,
        digitado=kwargs.pop('digitado', False),
        escaneado=kwargs.pop('escaneado', False),
        nulo=kwargs.pop('nulo', False),
        estado=estado,
    )
    db.session.add(folio)
    db.session.flush()
    return folio


@pytest.fixture()
def limiter_client():
    """App con rate limiting REAL (habilitado y con storage propio, no el de los tests)."""
    from app import create_app as _create_app

    class LimiterConfig(TestConfig):
        RATELIMIT_ENABLED = True
        RATELIMIT_STORAGE_URI = 'memory://'
        RATELIMIT_DEFAULT = '300 per hour'
        RATELIMIT_HEADERS_ENABLED = True

    application = _create_app(LimiterConfig)
    with application.app_context():
        db.create_all()
        make_user('operador', 'operador')
        yield application.test_client()
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def folio(app, tipo):
    folio = make_folio(tipo)
    db.session.commit()
    return folio


@pytest.fixture()
def folio_entregado(app, tipo, centro, operador):
    """Folio en estado 'entregado' con su EntregaFolio registrada."""
    folio = make_folio(tipo, estado='entregado')
    entrega = EntregaFolio(
        folio_id=folio.id,
        fechaEntrega=date(2026, 9, 1),
        centroId=centro.id,
        userId=operador.id,
    )
    db.session.add(entrega)
    db.session.commit()
    return folio
