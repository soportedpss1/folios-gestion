import logging
from datetime import datetime
from flask import Flask, jsonify
from flask_wtf.csrf import CSRFError
from app.config import Config, apply_runtime_env
from app.extensions import db, login_manager, migrate, csrf, limiter


def create_app(config_class=None):
    app = Flask(__name__)
    cfg = config_class or Config
    app.config.from_object(cfg)
    apply_runtime_env(app)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)

    if app.config.get('TRUST_PROXY'):
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Por favor inicie sesión para acceder.'
    login_manager.login_message_category = 'warning'

    @login_manager.user_loader
    def load_user(user_id):
        from app.models.usuario import Usuario
        user = db.session.get(Usuario, int(user_id))
        # Usuario desactivado pierde la sesión viva de inmediato.
        if user is None or not user.activo:
            return None
        return user

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    warn = getattr(cfg, 'warn_on_weak_config', None)
    if warn:
        warn(app.logger)

    from app.utils import a_hora_local
    app.jinja_env.filters['localtime'] = a_hora_local

    # Plantillas: {{ puede('centros.importar') }} — rol default OR grant.
    from app.services.permisos import puede
    app.jinja_env.globals['puede'] = puede

    # Marca: nombre/subtítulo/logo/favicon (config singleton, fallback si la DB falla).
    from app.models.marca import marca_template_dict

    @app.context_processor
    def inject_globals():
        """Variables globales de plantilla (años del filtro de folios, marca)."""
        return {'anio_actual': datetime.now().year, 'marca': marca_template_dict()}

    @app.errorhandler(404)
    def not_found(e):
        if request_wants_json():
            return jsonify(error='No encontrado'), 404
        return render_error('404', 'Página no encontrada', 'La página que busca no existe o fue movida.'), 404

    @app.errorhandler(403)
    def forbidden(e):
        if request_wants_json():
            return jsonify(error='Acceso denegado'), 403
        return render_error('403', 'Acceso denegado', 'No tiene permisos para acceder a esta sección.'), 403

    @app.errorhandler(405)
    def method_not_allowed(e):
        if request_wants_json():
            return jsonify(error='Método no permitido'), 405
        return render_error('405', 'Método no permitido', 'Este método no está permitido en esta dirección.'), 405

    @app.errorhandler(429)
    def rate_limited(e):
        if request_wants_json():
            return jsonify(error='Demasiadas solicitudes'), 429
        return render_error(
            '429', 'Demasiadas solicitudes',
            'Realizó demasiados intentos. Espere un minuto y vuelva a intentarlo.'
        ), 429

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        if request_wants_json():
            return jsonify(error='Formulario no válido'), 400
        return render_error(
            '400', 'Formulario no válido',
            'La sesión expiró o el formulario no es válido. Recargue la página e intente de nuevo.'
        ), 400

    @app.errorhandler(400)
    def bad_request(e):
        if request_wants_json():
            return jsonify(error='Solicitud no válida'), 400
        return render_error(
            '400', 'Solicitud no válida',
            'La solicitud no es válida. Recargue la página e intente de nuevo.'
        ), 400

    @app.errorhandler(413)
    def payload_too_large(e):
        if request_wants_json():
            return jsonify(error='Archivo demasiado grande'), 413
        return render_error(
            '413', 'Archivo demasiado grande',
            'El archivo supera el tamaño máximo permitido (5 MB).'
        ), 413

    @app.errorhandler(500)
    def internal_error(e):
        db.session.rollback()
        if request_wants_json():
            return jsonify(error='Error interno del servidor'), 500
        return render_error('500', 'Error interno', 'Ocurrió un error inesperado. Intente de nuevo.'), 500

    @app.route('/health')
    @limiter.exempt
    def health():
        return jsonify(status='ok'), 200

    @app.after_request
    def apply_security_headers(response):
        # setdefault: una respuesta puede sobreescribir su propio header
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        response.headers.setdefault(
            'Strict-Transport-Security', 'max-age=31536000; includeSubDomains'
        )
        return response

    from app.auth import auth_bp
    from app.dashboard import dashboard_bp
    from app.recepcion import recepcion_bp
    from app.folios import folios_bp
    from app.entregas import entregas_bp
    from app.devoluciones import devoluciones_bp
    from app.reportes import reportes_bp
    from app.usuarios import usuarios_bp
    from app.centros import centros_bp
    from app.certificados import certificados_bp
    from app.auditoria import auditoria_bp
    from app.sincronizacion import sincronizacion_bp
    from app.permisos import permisos_bp
    from app.marca import marca_bp
    from app.backup import backup_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(recepcion_bp)
    app.register_blueprint(folios_bp)
    app.register_blueprint(entregas_bp)
    app.register_blueprint(devoluciones_bp)
    app.register_blueprint(reportes_bp)
    app.register_blueprint(usuarios_bp)
    app.register_blueprint(centros_bp)
    app.register_blueprint(certificados_bp)
    app.register_blueprint(auditoria_bp)
    app.register_blueprint(sincronizacion_bp)
    app.register_blueprint(permisos_bp)
    app.register_blueprint(marca_bp)
    app.register_blueprint(backup_bp)

    from app.main import main_bp
    app.register_blueprint(main_bp)

    # Configura los mappers (backrefs folio/centro/usuario) de forma determinista
    # al crear la app, en vez de depender del primer query en ejecución.
    from sqlalchemy.orm import configure_mappers
    configure_mappers()

    return app


def request_wants_json():
    from flask import request
    return request.accept_mimetypes.best == 'application/json'


def render_error(code, title, message):
    from flask import render_template_string
    from app.models.marca import marca_template_dict
    marca = marca_template_dict()
    marca_titulo = marca.get('sufijo') or marca.get('nombre') or 'Gestión de Folios'
    return render_template_string(f'''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title} - {marca_titulo}</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet" integrity="sha384-QWTKZyjpPEjISv5WaRU9OFeRpok6YctnYmDr5pNlyT2bRjXh0JMhjY6hW+ALEwIH" crossorigin="anonymous">
    </head>
    <body class="bg-light d-flex align-items-center justify-content-center" style="min-height:100vh;">
        <div class="text-center">
            <h1 class="display-1 fw-bold text-primary">{code}</h1>
            <h3 class="mb-3">{title}</h3>
            <p class="text-muted mb-4">{message}</p>
            <a href="/" class="btn btn-primary">Volver al Inicio</a>
        </div>
    </body>
    </html>
    ''')
