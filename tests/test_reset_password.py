import pytest

import reset_password as rp
from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.usuario import Usuario
from tests.conftest import make_user


@pytest.fixture()
def patched_cli(app, monkeypatch):
    """Hace que main() use la app de prueba (sqlite) en vez de MySQL."""
    monkeypatch.setattr(rp, 'create_app', lambda *a, **k: app)
    return rp.main


def test_reset_por_username(app, operador):
    old_hash = operador.password_hash

    user, new_password = rp.reset_password('operador', 'nueva12345')

    assert user.id == operador.id
    assert new_password == 'nueva12345'
    db.session.refresh(operador)
    assert operador.password_hash != old_hash
    assert operador.check_password('nueva12345')
    assert not operador.check_password('pass12345')


def test_reset_por_email(app, operador):
    user, new_password = rp.reset_password('operador@test.local', 'nueva12345')
    assert user.id == operador.id


def test_reset_genera_password_aleatoria(app, operador):
    user, new_password = rp.reset_password('operador')
    assert len(new_password) >= 16
    assert user.check_password(new_password)
    assert new_password != 'operador'


def test_reset_usuario_inexistente(app, operador):
    with pytest.raises(LookupError):
        rp.reset_password('no-existe')


def test_reset_password_corta_rechazada(app, operador):
    with pytest.raises(ValueError):
        rp.reset_password('operador', 'abc')
    db.session.rollback()
    db.session.refresh(operador)
    assert operador.check_password('pass12345')


def test_reset_escribe_auditoria_cli(app, operador, admin):
    rp.reset_password('operador', 'nueva12345', by='adminuser')

    log = AuditLog.query.filter_by(tabla='usuarios', registro_id=operador.id).one()
    assert log.accion == 'UPDATE'
    assert log.ip_address == 'cli'
    assert log.user_id == admin.id
    assert log.datos_nuevos['password_hash'] == '***'
    assert 'nueva12345' not in str(log.datos_nuevos)


def test_reset_por_inexistente_no_cambia_nada(app, operador):
    old_hash = operador.password_hash
    with pytest.raises(LookupError):
        rp.reset_password('operador', 'nueva12345', by='fantasma')
    db.session.rollback()
    db.session.refresh(operador)
    assert operador.password_hash == old_hash


def test_main_ok(patched_cli, capsys):
    make_user('maria', 'operador')
    code = rp.main(['maria', '--password', 'secret123'])

    assert code == 0
    out = capsys.readouterr().out
    assert 'Contraseña restablecida para maria' in out
    assert 'secret123' not in out


def test_main_imprime_password_generada(patched_cli, capsys):
    make_user('maria', 'operador')
    code = rp.main(['maria'])

    assert code == 0
    out = capsys.readouterr().out
    assert 'Nueva contraseña:' in out


def test_main_usuario_no_existe(patched_cli, capsys):
    code = rp.main(['fantasma'])
    assert code == 1
    assert 'no encontrado' in capsys.readouterr().err


def test_main_password_corta(patched_cli, capsys):
    make_user('maria', 'operador')
    code = rp.main(['maria', '--password', 'abc'])
    assert code == 1
    assert 'inválida' in capsys.readouterr().err
    user = Usuario.query.filter_by(username='maria').one()
    assert user.check_password('pass12345')
