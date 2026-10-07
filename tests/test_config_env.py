"""Config: DATABASE_URL (usado para migraciones y entorno alternativo)."""

import os
import subprocess
import sys


def _config_uri(extra_env):
    env = os.environ.copy()
    env['SECRET_KEY'] = 'test-secret-key-not-for-production'
    env.update(extra_env)
    result = subprocess.run(
        [sys.executable, '-c',
         'from app.config import Config; print(Config.SQLALCHEMY_DATABASE_URI)'],
        capture_output=True, text=True, env=env, cwd=os.path.dirname(os.path.dirname(__file__)),
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_database_url_sobreescribe_uri_mysql():
    uri = _config_uri({'DATABASE_URL': 'sqlite:///migraciones.db'})
    assert uri == 'sqlite:///migraciones.db', f'DATABASE_URL ignorado: {uri}'


def test_sin_database_url_usa_mysql_de_env():
    uri = _config_uri({'DATABASE_URL': '', 'DB_HOST': 'dbhost', 'DB_USER': 'miuser',
                       'DB_PASSWORD': 'mipass', 'DB_NAME': 'midb'})
    # load_dotenv no pisa variables ya presentes; '' debe tratarse como ausente
    assert 'mysql+pymysql://miuser:mipass@dbhost' in uri and 'midb' in uri, uri
