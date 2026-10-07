"""Fase 5 — deuda técnica: refactors de estructura, warnings legacy y session timeout."""

import warnings

from app.extensions import db
from tests.conftest import make_folio, make_user


# --- guardas de estructura (los módulos nuevos deben existir) -----------------

def test_log_audit_vive_en_servicio():
    from app.services.audit import log_audit
    assert callable(log_audit)


def test_queries_get_or_404_en_servicio():
    from app.services.queries import get_or_404
    assert callable(get_or_404)


def test_formularios_entregas_en_forms():
    from app.entregas.forms import EntregaCreateForm, EntregaEditForm
    assert EntregaCreateForm is not None and EntregaEditForm is not None


def test_decorator_edit_required_disponible():
    from app.decorators import edit_required
    assert callable(edit_required)


def test_utils_utcnow_disponible():
    from datetime import datetime, timezone
    from app.utils import utcnow
    ahora = utcnow()
    assert isinstance(ahora, datetime)
    assert ahora.tzinfo is None, 'las columnas DateTime son naive: utcnow no debe devolver tz'
    dif = datetime.now(timezone.utc).replace(tzinfo=None) - ahora
    assert abs(dif.total_seconds()) < 10


# --- session timeout ----------------------------------------------------------

def test_config_define_session_timeout():
    from app.config import Config
    valor = getattr(Config, 'PERMANENT_SESSION_LIFETIME', None)
    assert valor is not None, 'Config no define PERMANENT_SESSION_LIFETIME'


def test_login_marca_sesion_permanente(client, app, operador):
    resp = client.post(
        '/auth/login',
        data={'username': operador.username, 'password': 'pass12345'},
    )
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess.permanent, 'la sesión no está marcada como permanente'


# --- warnings legacy ----------------------------------------------------------

def test_rutas_sin_legacy_query_get(auth_client, app, centro):
    """get_or_404 interno usa Query.get() (LegacyAPIWarning); debe eliminarse."""
    from sqlalchemy.exc import LegacyAPIWarning
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        resp = auth_client.get(f'/centros/{centro.id}/detail')
        assert resp.status_code == 200
    legacy = [str(w.message) for w in caught if issubclass(w.category, LegacyAPIWarning)]
    assert not legacy, f'LegacyAPIWarning en rutas: {legacy}'


def test_modelos_no_usan_utcnow_deprecated(app, tipo):
    """datetime.utcnow() emite DeprecationWarning desde Python 3.12."""
    with warnings.catch_warnings():
        warnings.filterwarnings('error', message='datetime.datetime.utcnow')
        make_folio(tipo, anio=2026, numero=8001)
        db.session.commit()


# --- caracterizaciones (protegen los refactors) --------------------------------

def test_usuario_lectura_no_puede_editar(app, client):
    make_user('lector', 'lectura')
    client.post('/auth/login', data={'username': 'lector', 'password': 'pass12345'})
    resp = client.get('/entregas/create', follow_redirects=True)
    assert resp.status_code == 200
    assert 'No tiene permisos' in resp.get_data(as_text=True)


def test_auditoria_registra_insert_de_recepcion(admin_client, app, tipo):
    from app.models.audit_log import AuditLog
    resp = admin_client.post(
        '/recepcion/create',
        data={'fecha': '2026-09-28', 'anioCert': 2026, 'tipoCert': tipo.id,
              'folioInicial': 9001, 'folioFinal': 9003},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    logs = AuditLog.query.filter_by(accion='INSERT', tabla='recepcion_folios').all()
    assert len(logs) == 1, f'esperaba 1 registro de auditoría, hay {len(logs)}'


# --- LIKE sobre Integer (SADeprecationWarning: sin like_op en tipos numéricos) ----

def test_api_disponibles_busca_sin_warning_like(auth_client, app, tipo, recwarn):
    make_folio(tipo, anio=2026, numero=4321)
    resp = auth_client.get('/entregas/api/folios-disponibles?q=432')
    assert resp.status_code == 200
    assert [i['id'] for i in resp.get_json()], 'búsqueda sin resultados'
    sad = [w for w in recwarn.list if 'like_op' in str(w.message)]
    assert not sad, 'LIKE aplicado a columna Integer sin cast'


def test_folios_busqueda_por_numero(auth_client, app, tipo, recwarn):
    make_folio(tipo, anio=2026, numero=4322)
    db.session.commit()
    resp = auth_client.get('/folios/?busqueda=4322')
    assert resp.status_code == 200
    assert '4322' in resp.get_data(as_text=True)
    sad = [w for w in recwarn.list if 'like_op' in str(w.message)]
    assert not sad, 'LIKE aplicado a columna Integer sin cast'
