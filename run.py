import os

from app import create_app
from app.config import DevelopmentConfig, ProductionConfig

CONFIGS = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
}

# FLASK_CONFIG=development para local; por defecto (Docker/Gunicorn) producción.
config_name = os.environ.get('FLASK_CONFIG', 'production')
app = create_app(CONFIGS.get(config_name, ProductionConfig))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8089)
