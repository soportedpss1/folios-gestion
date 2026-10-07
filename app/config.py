import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


def _env_bool(name, default=None):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise RuntimeError('SECRET_KEY no está configurada. Genere una con: python -c "import secrets; print(secrets.token_hex(32))"')
    if SECRET_KEY.strip().lower() in ('change-me-in-production', 'changeme', 'secret') \
            or SECRET_KEY.strip().lower().startswith('cambie-'):
        raise RuntimeError('SECRET_KEY es un valor de ejemplo. Genere una real con: python -c "import secrets; print(secrets.token_hex(32))"')

    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_PORT = int(os.environ.get('DB_PORT', 3306))
    DB_NAME = os.environ.get('DB_NAME', 'folios_bioest')
    DB_USER = os.environ.get('DB_USER', 'root')
    DB_PASSWORD = os.environ.get('DB_PASSWORD')

    # DATABASE_URL (si existe) tiene prioridad — usado para migraciones/entornos alternativos
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_recycle': 280,
        'pool_pre_ping': True,
    }

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    # Flask por defecto es True: en HTTP plano el navegador descarta la cookie
    # y el login no persiste. Activar solo detrás de TLS.
    SESSION_COOKIE_SECURE = _env_bool('SESSION_COOKIE_SECURE', False)

    # Sesión: caduca a las 8 horas (login la marca permanente; Flask renueva la
    # cookie en cada petición mientras el usuario siga activo)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None

    # Tope de subida: los .xlsx de importar son pequeños; sin él un cliente
    # puede mandar un body enorme y agotar RAM/disco (werkzeug responde 413).
    # 32 MB: el respaldo JSON de backup/restaurar puede superar los 5 MB viejos.
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 32 * 1024 * 1024))

    # Almacenamiento de rate limits. Default memoria (dev local); en Docker/Gunicorn
    # compose inyecta redis:// para que los 4 workers compartan el contador.
    RATELIMIT_STORAGE_URI = os.environ.get('RATELIMIT_STORAGE_URI', 'memory://')
    # Si Redis cae, el login sigue funcionando sin límite (fail-open) en vez de 500
    RATELIMIT_SWALLOW_ERRORS = True
    # Tope global: sin él cualquier usuario autenticado puede martillar
    # exports PDF/Excel (CPU/RAM) sin límite.
    RATELIMIT_DEFAULT = os.environ.get('RATELIMIT_DEFAULT', '300 per hour')
    RATELIMIT_HEADERS_ENABLED = True

    # Solo detrás de un proxy/reverse proxy que fije X-Forwarded-For.
    # Sin eso, un cliente puede forzar su propia IP y esquivar los rate limits.
    TRUST_PROXY = os.environ.get('TRUST_PROXY', 'false').lower() == 'true'

    # --- Sincronización con Google Sheets (cuenta de servicio) ---
    # Ruta al JSON de credenciales; vacío = módulo muestra config incompleta.
    GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON', '')
    GOOGLE_SHEET_ID = os.environ.get('GOOGLE_SHEET_ID', '')
    GOOGLE_SHEET_WORKSHEET = os.environ.get('GOOGLE_SHEET_WORKSHEET', 'folios')
    # Token del trigger externo POST /sincronizacion/api/sincronizar; vacío = ruta 403.
    SHEET_SYNC_TOKEN = os.environ.get('SHEET_SYNC_TOKEN', '')

    @classmethod
    def warn_on_weak_config(cls, logger):
        """Avisa en arranque de configuraciones inseguras que no frenan el boot."""
        if cls.DB_USER == 'root':
            logger.warning(
                'DB_USER=root: la aplicación corre con privilegios de superusuario de MariaDB. '
                'Cree un usuario con privilegios solo sobre %s.', cls.DB_NAME)


def apply_runtime_env(app):
    """Vuelve a leer del entorno las claves booleanas derivadas de variables.

    `from_object` copia los atributos al importar el módulo de config, así que
    una env var puesta después (tests, arranque de gunicorn) no llegaría.
    """
    value = _env_bool('SESSION_COOKIE_SECURE')
    if value is not None:
        app.config['SESSION_COOKIE_SECURE'] = value
    value = _env_bool('TRUST_PROXY')
    if value is not None:
        app.config['TRUST_PROXY'] = value


class DevelopmentConfig(Config):
    DEBUG = True
    # Dev local es HTTP: una cookie Secure nunca se guarda y el login no persiste.
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    DEBUG = False
    # Detrás de TLS poner SESSION_COOKIE_SECURE=true; en HTTP plano dejarlo en
    # false, si no el navegador descarta la cookie y el login no persiste.
    # El valor final se relee del entorno en apply_runtime_env().
    SESSION_COOKIE_SECURE = _env_bool('SESSION_COOKIE_SECURE', False)
