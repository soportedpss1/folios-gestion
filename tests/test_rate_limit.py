"""Fase 3 — rate limit con storage compartido entre workers (no in-memory en producción)."""

import os
import subprocess
import sys


def _print_config_value(env_extra):
    env = os.environ.copy()
    env['SECRET_KEY'] = 'test-secret-key-not-for-production'
    env.update(env_extra)
    result = subprocess.run(
        [sys.executable, '-c',
         'from app.config import Config; print(getattr(Config, "RATELIMIT_STORAGE_URI", "MISSING"))'],
        capture_output=True, text=True, env=env,
        cwd=os.path.dirname(os.path.dirname(__file__)),
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_config_define_rate_limit_storage():
    """Sin esta clave, Flask-Limiter usa memoria por worker (límite inútil con gunicorn x4)."""
    valor = _print_config_value({})
    assert valor != 'MISSING', 'Config no define RATELIMIT_STORAGE_URI'
    assert valor.endswith('://'), f'RATELIMIT_STORAGE_URI inválido: {valor}'


def test_limiter_storage_respeta_env():
    assert _print_config_value({'RATELIMIT_STORAGE_URI': 'redis://redis-host:6379'}) == \
        'redis://redis-host:6379'


def test_limiter_storage_redis_disponible():
    """compose apunta a redis://...: el cliente redis debe estar en las dependencies.

    limits construye el storage eager en init_app → sin el paquete, la app no arranca.
    """
    from limits.storage import storage_from_string
    storage = storage_from_string('redis://redis:6379')
    assert storage is not None, 'storage redis no se pudo construir'


def test_config_swallow_errors_rate_limit():
    """Si Redis cae, el login debe seguir funcionando (fail-open) en vez de 500."""
    from app.config import Config
    assert getattr(Config, 'RATELIMIT_SWALLOW_ERRORS', None) is True, \
        'Config no define RATELIMIT_SWALLOW_ERRORS=True'


def test_login_limita_a_429(limiter_client):
    """Regresión: el límite 10/min de login sigue activo."""
    statuses = []
    for _ in range(11):
        resp = limiter_client.post(
            '/auth/login',
            data={'username': 'no-existe', 'password': 'mala'},
        )
        statuses.append(resp.status_code)
    assert statuses[-1] == 429, f'esperaba 429 en la 11ª petición, llegó {statuses}'


def test_config_define_tope_global():
    """Sin tope global, cualquier autenticado puede martillar exports PDF/Excel."""
    from app.config import Config
    assert getattr(Config, 'RATELIMIT_DEFAULT', None), 'Config no define RATELIMIT_DEFAULT'


def test_health_exento_de_rate_limit(limiter_client):
    """/health lo pingea el healthcheck de compose cada 30 s: no debe consumir cuota."""
    health = limiter_client.get('/health')
    assert health.status_code == 200
    assert health.headers.get('X-RateLimit-Limit') is None, '/health no está exento'

    protegida = limiter_client.get('/dashboard/')
    assert protegida.headers.get('X-RateLimit-Limit'), 'las rutas normales sin límite visible'
