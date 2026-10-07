"""Tests del módulo de sincronización con Google Sheets (lógica + rutas + worker)."""

from datetime import timedelta

import pytest

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.sync_config import (
    FRECUENCIA_DEFECTO_MINUTOS,
    RETRASO_REINTENTO_FALLA_MIN,
    debe_ejecutar,
    get_config,
    proximo_intento,
    registrar_intento,
)
from app.services.gsheets import ENCABEZADOS, ErrorSincronizacion, fila_folio
from app.utils import utcnow
from tests.conftest import make_folio

# ---------------------------------------------------------------- fake worksheet

class FakeWS:
    """Worksheet en memoria con la firma de gspread que usa sincronizar()."""

    def __init__(self, values=None):
        self.values = [list(r) for r in (values or [])]
        self.batch_llamadas = []
        self.append_llamadas = []
        self.delete_llamadas = []
        self.update_llamadas = []

    def get_all_values(self, *args, **kwargs):
        return [list(r) for r in self.values]

    def update(self, values, range_name=None, value_input_option=None, **kwargs):
        self.update_llamadas.append((range_name, values))
        fila = list(values[0])
        if self.values:
            self.values[0] = fila
        else:
            self.values.append(fila)

    def batch_update(self, data, value_input_option=None, **kwargs):
        self.batch_llamadas.extend(data)
        for item in data:
            inicio = int(item['range'].split(':')[0][1:])
            self.values[inicio - 1] = list(item['values'][0])

    def append_rows(self, rows, value_input_option='RAW', **kwargs):
        self.append_llamadas.append(list(rows))
        self.values.extend(list(r) for r in rows)

    def delete_rows(self, start, end=None, **kwargs):
        end = end if end is not None else start
        self.delete_llamadas.append((start, end))
        del self.values[start - 1:end]


@pytest.fixture()
def fake_ws(monkeypatch):
    """sincronizar() usa este worksheet; get_client no toca la red."""
    ws = FakeWS()
    monkeypatch.setattr('app.services.gsheets.get_client', lambda cfg=None: object())
    monkeypatch.setattr('app.services.gsheets._worksheet', lambda gc: ws)
    return ws


# ------------------------------------------------------------------ upsert

def test_sincronizar_hoja_vacia_escribe_header_y_append(app, tipo, fake_ws):
    make_folio(tipo, numero=1)
    make_folio(tipo, numero=2)
    db.session.commit()

    from app.services.gsheets import sincronizar
    counts = sincronizar()

    assert fake_ws.values[0] == ENCABEZADOS
    assert counts == {'agregadas': 2, 'actualizadas': 0, 'eliminadas': 0, 'total': 2}
    assert len(fake_ws.append_llamadas) == 1
    assert len(fake_ws.append_llamadas[0]) == 2
    # id como primera columna, folio en la segunda
    assert fake_ws.append_llamadas[0][0][0].isdigit()
    assert fake_ws.append_llamadas[0][0][1] == '1'


def test_sincronizar_upsert_actualiza_elimina_agrega(app, tipo, fake_ws):
    folio = make_folio(tipo, numero=10)
    db.session.commit()

    deseada = fila_folio(folio)
    modificada = list(deseada)
    modificada[5] = 'entregado'              # celda que cambió en la DB
    huerfana = ['999', '999', 'X', '2020', '', 'disponible'] + ['No'] * 3 + ['-'] * 4
    nueva_en_db = make_folio(tipo, numero=11)
    db.session.commit()

    fake_ws.values = [ENCABEZADOS, modificada, huerfana]

    from app.services.gsheets import sincronizar
    counts = sincronizar()

    assert counts == {'agregadas': 1, 'actualizadas': 1, 'eliminadas': 1, 'total': 2}
    assert fake_ws.values[1] == deseada          # fila actualizada con valores de la DB
    assert fake_ws.delete_llamadas               # huérfana borrada
    assert str(nueva_en_db.id) in [r[0] for r in fake_ws.append_llamadas[0]]
    assert '999' not in [r[0] for r in fake_ws.values[1:]]


def test_sincronizar_header_distinto_se_reescribe(app, tipo, fake_ws):
    make_folio(tipo, numero=1)
    db.session.commit()
    fake_ws.values = [['x', 'y', 'z']]

    from app.services.gsheets import sincronizar
    sincronizar()

    assert fake_ws.values[0] == ENCABEZADOS
    assert fake_ws.update_llamadas, 'el header debió reescribirse'


def test_sincronizar_fila_vacia_no_se_borra(app, tipo, fake_ws):
    make_folio(tipo, numero=1)
    db.session.commit()
    fake_ws.values = [ENCABEZADOS, [''] * len(ENCABEZADOS)]

    from app.services.gsheets import sincronizar
    counts = sincronizar()

    assert counts['eliminadas'] == 0
    assert fake_ws.delete_llamadas == []


def test_sincronizar_sin_credencial_lanza_error_en_espanol(app, monkeypatch):
    monkeypatch.setattr('app.services.gsheets.get_client',
                        lambda cfg=None: (_ for _ in ()).throw(
                            ErrorSincronizacion('Falta la credencial de Google: configure GOOGLE_SERVICE_ACCOUNT_JSON.')))
    from app.services.gsheets import sincronizar
    with pytest.raises(ErrorSincronizacion) as exc:
        sincronizar()
    assert 'GOOGLE_SERVICE_ACCOUNT_JSON' in str(exc.value)


def test_lock_ocupado_no_corre(app, monkeypatch):
    monkeypatch.setattr('app.services.gsheets._adquirir_lock', lambda: False)
    from app.services.gsheets import sincronizar
    with pytest.raises(ErrorSincronizacion) as exc:
        sincronizar()
    assert 'ya en curso' in str(exc.value)


# ---------------------------------------------------------------- config worker

def test_debe_ejecutar_estados(app):
    cfg = get_config()
    ahora = utcnow()

    assert debe_ejecutar(cfg, ahora) is False            # activo=False por defecto

    cfg.activo = True
    assert debe_ejecutar(cfg, ahora) is True             # sin intentos ⇒ ya

    registrar_intento(cfg, counts={'agregadas': 1, 'actualizadas': 0, 'eliminadas': 0, 'total': 1})
    exito_en = cfg.ultimo_intento_at
    assert debe_ejecutar(cfg, ahora) is False            # recién corrió
    assert debe_ejecutar(cfg, exito_en + timedelta(minutes=FRECUENCIA_DEFECTO_MINUTOS)) is True

    registrar_intento(cfg, error='Falla de red')
    fallo_en = cfg.ultimo_intento_at
    assert debe_ejecutar(cfg, fallo_en) is False
    assert debe_ejecutar(cfg, fallo_en + timedelta(minutes=RETRASO_REINTENTO_FALLA_MIN - 1)) is False
    assert debe_ejecutar(cfg, fallo_en + timedelta(minutes=RETRASO_REINTENTO_FALLA_MIN)) is True


def test_proximo_intento(app):
    cfg = get_config()
    assert proximo_intento(cfg, utcnow()) is None        # desactivado

    cfg.activo = True
    assert proximo_intento(cfg, utcnow()) is None        # sin intentos ⇒ inmediato

    registrar_intento(cfg, counts={'agregadas': 0, 'actualizadas': 0, 'eliminadas': 0, 'total': 0})
    esperado = cfg.ultimo_intento_at + timedelta(minutes=FRECUENCIA_DEFECTO_MINUTOS)
    assert proximo_intento(cfg, utcnow()) == esperado


def test_registrar_intento_exito_y_fallo(app):
    cfg = get_config()
    registrar_intento(cfg, counts={'agregadas': 2, 'actualizadas': 3, 'eliminadas': 1, 'total': 10})
    assert cfg.ultimo_error is None
    assert cfg.ultimo_sync_at is not None
    assert '2 agregadas' in cfg.ultimo_resultado

    registrar_intento(cfg, error='No se pudo abrir la hoja.')
    assert cfg.ultimo_error == 'No se pudo abrir la hoja.'
    assert cfg.ultimo_sync_at is not None               # último éxito se conserva


def test_worker_tick_inactivo_no_sincroniza(app, monkeypatch):
    import run_worker
    llamado = []
    monkeypatch.setattr(run_worker, 'sincronizar', lambda *a, **k: llamado.append(1) or {})
    run_worker.tick(app)
    assert llamado == []


def test_worker_tick_ejecuta_y_persiste(app, monkeypatch):
    import run_worker
    cfg = get_config()
    cfg.activo = True
    db.session.commit()

    monkeypatch.setattr(run_worker, 'sincronizar',
                        lambda *a, **k: {'agregadas': 1, 'actualizadas': 2, 'eliminadas': 3, 'total': 4})
    run_worker.tick(app)

    db.session.refresh(cfg)
    assert cfg.ultimo_error is None
    assert cfg.ultimo_sync_at is not None
    assert '1 agregadas' in cfg.ultimo_resultado


def test_worker_tick_fallo_persiste_error(app, monkeypatch):
    import run_worker
    cfg = get_config()
    cfg.activo = True
    db.session.commit()

    def _falla(*a, **k):
        raise ErrorSincronizacion('Falta la credencial de Google.')
    monkeypatch.setattr(run_worker, 'sincronizar', _falla)
    run_worker.tick(app)

    db.session.refresh(cfg)
    assert cfg.ultimo_error == 'Falta la credencial de Google.'
    assert cfg.ultimo_sync_at is None


# ---------------------------------------------------------------------- rutas

def _login_admin(client, admin):
    resp = client.post('/auth/login',
                       data={'username': admin.username, 'password': 'pass12345'})
    assert resp.status_code == 302


def test_index_requiere_login(client):
    resp = client.get('/sincronizacion/')
    assert resp.status_code == 302
    assert '/auth/login' in resp.headers['Location']


def test_index_prohibido_para_operador(auth_client):
    resp = auth_client.get('/sincronizacion/', follow_redirects=True)
    assert resp.status_code == 200
    assert 'No tiene permisos' in resp.get_data(as_text=True)


def test_index_admin_renderiza(client, admin):
    _login_admin(client, admin)
    resp = client.get('/sincronizacion/')
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert 'Sincronización con Google Sheets' in html
    assert 'Configuración incompleta' in html          # sin GOOGLE_* en tests


def test_config_guardar(client, admin):
    _login_admin(client, admin)
    resp = client.post('/sincronizacion/config',
                       data={'activo': 'on', 'frecuencia_minutos': 30},
                       follow_redirects=True)
    assert resp.status_code == 200
    cfg = get_config()
    assert cfg.activo is True
    assert cfg.frecuencia_minutos == 30
    assert 'guardada' in resp.get_data(as_text=True)


def test_config_frecuencia_invalida(client, admin):
    _login_admin(client, admin)
    resp = client.post('/sincronizacion/config',
                       data={'frecuencia_minutos': 1})
    html = resp.get_data(as_text=True)
    assert 'Ingrese un valor entre 5 y 10080 minutos.' in html
    assert get_config().frecuencia_minutos == FRECUENCIA_DEFECTO_MINUTOS


def test_sincronizar_ahora_ok(client, admin, monkeypatch):
    _login_admin(client, admin)
    monkeypatch.setattr('app.sincronizacion.sincronizar',
                        lambda *a, **k: {'agregadas': 1, 'actualizadas': 0, 'eliminadas': 0, 'total': 1})
    resp = client.post('/sincronizacion/sincronizar', follow_redirects=True)
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert 'Sincronización completada: 1 agregadas' in html
    cfg = get_config()
    assert cfg.ultimo_error is None and cfg.ultimo_sync_at is not None
    assert AuditLog.query.filter_by(tabla='google_sheets').count() == 1


def test_sincronizar_ahora_error(client, admin, monkeypatch):
    _login_admin(client, admin)

    def _falla(*a, **k):
        raise ErrorSincronizacion('No se pudo abrir la hoja. Verifique GOOGLE_SHEET_ID.')
    monkeypatch.setattr('app.sincronizacion.sincronizar', _falla)
    resp = client.post('/sincronizacion/sincronizar', follow_redirects=True)
    html = resp.get_data(as_text=True)
    assert 'No se pudo abrir la hoja' in html
    assert get_config().ultimo_error is not None
    assert AuditLog.query.filter_by(tabla='google_sheets').count() == 0


# ------------------------------------------------------------ API token (cron)

def test_api_sin_token_configurado(app, client):
    app.config['SHEET_SYNC_TOKEN'] = ''
    resp = client.post('/sincronizacion/api/sincronizar')
    assert resp.status_code == 403
    assert 'Token no configurado' in resp.get_json()['error']


def test_api_token_incorrecto(app, client):
    app.config['SHEET_SYNC_TOKEN'] = 'secreto'
    resp = client.post('/sincronizacion/api/sincronizar',
                       headers={'X-Sync-Token': 'otro'})
    assert resp.status_code == 403
    assert 'Token inválido' in resp.get_json()['error']


def test_api_token_correcto(app, client, monkeypatch):
    app.config['SHEET_SYNC_TOKEN'] = 'secreto'
    monkeypatch.setattr('app.sincronizacion.sincronizar',
                        lambda *a, **k: {'agregadas': 0, 'actualizadas': 2, 'eliminadas': 0, 'total': 5})
    resp = client.post('/sincronizacion/api/sincronizar',
                       headers={'X-Sync-Token': 'secreto'})
    assert resp.status_code == 200
    assert resp.get_json() == {'agregadas': 0, 'actualizadas': 2, 'eliminadas': 0, 'total': 5}
    # sin sesión: el estado queda en sync_config y NO en auditoría
    assert get_config().ultimo_error is None
    assert AuditLog.query.filter_by(tabla='google_sheets').count() == 0


def test_api_error_devuelve_502(app, client, monkeypatch):
    app.config['SHEET_SYNC_TOKEN'] = 'secreto'

    def _falla(*a, **k):
        raise ErrorSincronizacion('Falta la credencial de Google.')
    monkeypatch.setattr('app.sincronizacion.sincronizar', _falla)
    resp = client.post('/sincronizacion/api/sincronizar',
                       headers={'X-Sync-Token': 'secreto'})
    assert resp.status_code == 502
    assert 'Falta la credencial' in resp.get_json()['error']


def test_api_exenta_de_csrf(app):
    """La ruta del cron no lleva token CSRF (patrón: curl sin sesión)."""
    from sqlalchemy.pool import StaticPool

    from app import create_app

    class CsrfConfig:
        TESTING = True
        PROPAGATE_EXCEPTIONS = False
        SECRET_KEY = 'test-secret-key-not-for-production'
        SQLALCHEMY_DATABASE_URI = 'sqlite://'
        SQLALCHEMY_ENGINE_OPTIONS = {
            'poolclass': StaticPool,
            'connect_args': {'check_same_thread': False},
        }
        WTF_CSRF_ENABLED = True
        WTF_CSRF_TIME_LIMIT = None
        RATELIMIT_ENABLED = False

    application = create_app(CsrfConfig)
    with application.app_context():
        db.create_all()
        try:
            application.config['SHEET_SYNC_TOKEN'] = 'secreto'
            c = application.test_client()
            resp = c.post('/sincronizacion/api/sincronizar',
                          headers={'X-Sync-Token': 'secreto'})
            # 400 sería el rechazo CSRF (bug si aparece); 200/502 = pasó el CSRF
            assert resp.status_code != 400, 'la ruta api no está exempt de CSRF'
            assert resp.status_code in (200, 502)
        finally:
            db.session.remove()
            db.drop_all()


def test_api_proxima_requiere_login(client):
    resp = client.get('/sincronizacion/api/proxima')
    assert resp.status_code == 302
    assert '/auth/login' in resp.headers['Location']


def test_api_proxima_desactivado(auth_client):
    """Operador (navbar visible para todos): sync apagada por defecto."""
    resp = auth_client.get('/sincronizacion/api/proxima')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['activo'] is False
    assert data['proximo'] is None
    assert data['atrasado'] is False


def test_api_proxima_activo_sin_intentos_es_inmediato(client, admin):
    _login_admin(client, admin)
    cfg = get_config()
    cfg.activo = True
    db.session.commit()
    data = client.get('/sincronizacion/api/proxima').get_json()
    assert data['activo'] is True
    assert data['proximo'] is None          # el worker lo toma en su próximo tick


def test_api_proxima_futura(client, admin):
    _login_admin(client, admin)
    cfg = get_config()
    cfg.activo = True
    registrar_intento(cfg, counts={'agregadas': 0, 'actualizadas': 0,
                                   'eliminadas': 0, 'total': 0})
    data = client.get('/sincronizacion/api/proxima').get_json()
    esperado = cfg.ultimo_intento_at + timedelta(minutes=FRECUENCIA_DEFECTO_MINUTOS)
    assert data['proximo'] == esperado.strftime('%Y-%m-%dT%H:%M:%SZ')
    assert data['frecuencia_minutos'] == FRECUENCIA_DEFECTO_MINUTOS
    assert data['atrasado'] is False

    # Tras un fallo el próximo intento se acerca (retraso de reintento).
    registrar_intento(cfg, error='Falla de red')
    esperado_fallo = cfg.ultimo_intento_at + timedelta(minutes=RETRASO_REINTENTO_FALLA_MIN)
    data = client.get('/sincronizacion/api/proxima').get_json()
    assert data['proximo'] == esperado_fallo.strftime('%Y-%m-%dT%H:%M:%SZ')


def test_api_proxima_atrasado(client, admin):
    _login_admin(client, admin)
    cfg = get_config()
    cfg.activo = True
    registrar_intento(cfg, counts={'agregadas': 0, 'actualizadas': 0,
                                   'eliminadas': 0, 'total': 0})
    cfg.ultimo_intento_at = utcnow() - timedelta(hours=2)
    db.session.commit()
    data = client.get('/sincronizacion/api/proxima').get_json()
    assert data['atrasado'] is True
    assert data['proximo'] < utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')


def test_navbar_muestra_temporizador(client, admin):
    _login_admin(client, admin)
    resp = client.get('/dashboard/', follow_redirects=True)
    assert b'id="sync-timer"' in resp.data
    assert b'id="sync-timer-text"' in resp.data
