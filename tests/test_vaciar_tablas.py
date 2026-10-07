import pytest

import vaciar_tablas as vt
from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.centro import Centro
from app.models.folio import Folio
from app.models.tipo_certificado import TipoCertificado
from app.models.usuario import Usuario
from tests.conftest import make_folio


@pytest.fixture()
def patched_cli(app, monkeypatch):
    """Hace que main() use la app de prueba (sqlite) en vez de MySQL."""
    monkeypatch.setattr(vt, 'create_app', lambda *a, **k: app)
    return vt.main


def fake_input(respuestas):
    it = iter(respuestas)

    def _input(prompt=''):
        print(prompt, end='')
        return next(it, '')

    return _input


def test_vaciar_deja_solo_usuarios(app, operador, centro, tipo):
    make_folio(tipo)
    db.session.commit()

    filas = vt.vaciar()

    assert filas['centros'] == 1
    assert filas['tipo_certificados'] == 1
    assert filas['folios'] == 1
    assert Centro.query.count() == 0
    assert TipoCertificado.query.count() == 0
    assert Folio.query.count() == 0
    usuarios = Usuario.query.all()
    assert [u.username for u in usuarios] == ['operador']


def test_vaciar_registra_auditoria_cli(app, operador, admin):
    vt.vaciar()

    log = AuditLog.query.filter_by(accion='DELETE', tabla='*').one()
    assert log.ip_address == 'cli'
    assert log.user_id == admin.id
    assert set(log.datos_nuevos['tablas']) == set(vt.TABLAS_A_VACIAR)
    assert set(log.datos_nuevos['filas']) == set(vt.TABLAS_A_VACIAR)


def test_vaciar_by_elige_actor(app, operador, admin):
    vt.vaciar(by='operador')

    log = AuditLog.query.filter_by(accion='DELETE', tabla='*').one()
    assert log.user_id == operador.id


def test_vaciar_por_inexistente_no_borra_nada(app, operador, centro):
    with pytest.raises(LookupError):
        vt.vaciar('fantasma')
    db.session.rollback()
    assert Centro.query.count() == 1
    assert Usuario.query.count() == 1


def test_main_sin_entrada_aborta(patched_cli, monkeypatch, capsys, operador, centro):
    monkeypatch.setattr('builtins.input', fake_input([]))

    code = vt.main([])

    assert code == 1
    assert 'cancelada' in capsys.readouterr().err
    assert Centro.query.count() == 1


def test_main_cancela_en_primer_prompt(patched_cli, monkeypatch, capsys, operador, centro):
    monkeypatch.setattr('builtins.input', fake_input(['n']))

    code = vt.main([])

    assert code == 1
    assert 'cancelada' in capsys.readouterr().err
    assert Centro.query.count() == 1


def test_main_aborta_palabra_erronea(patched_cli, monkeypatch, capsys, operador, centro):
    monkeypatch.setattr('builtins.input', fake_input(['s', 'borrar']))

    code = vt.main([])

    assert code == 1
    assert 'cancelada' in capsys.readouterr().err
    assert Centro.query.count() == 1


def test_main_doble_confirmacion_ok(patched_cli, monkeypatch, capsys, operador, centro):
    monkeypatch.setattr('builtins.input', fake_input(['s', 'BORRAR']))

    code = vt.main([])

    assert code == 0
    out = capsys.readouterr().out
    assert 'BORRAR para confirmar' in out
    assert Centro.query.count() == 0


def test_main_by_inexistente(patched_cli, monkeypatch, capsys, operador, centro):
    monkeypatch.setattr('builtins.input', fake_input(['s', 'BORRAR']))

    code = vt.main(['--by', 'fantasma'])

    assert code == 1
    assert 'no encontrado' in capsys.readouterr().err
    assert Centro.query.count() == 1
