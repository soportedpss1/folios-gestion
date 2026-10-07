"""Marca visible de la aplicación (nombre, subtítulo, logo y favicon)."""

from sqlalchemy.dialects import mysql

from app.extensions import db
from app.utils import utcnow

NOMBRE_DEFECTO = 'Gestión de Folios'
SUFIJO_DEFECTO = 'D1 Santiago'
SUBTITULO_DEFECTO = 'Bioestadística D1'

NOMBRE_MAX = 50
SUFIJO_MAX = 50
SUBTITULO_MAX = 80
IMAGEN_MAX_BYTES = 512 * 1024  # 512 KB por imagen

# Extensión del archivo → MIME con el que se sirve la imagen.
MIME_POR_EXTENSION = {
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'svg': 'image/svg+xml',
    'webp': 'image/webp',
}
EXTENSIONES_PERMITIDAS = tuple(MIME_POR_EXTENSION)

# BLOB no alcanza para 512 KB (64 KB); en MySQL hace falta LONGBLOB.
_IMAGEN = db.LargeBinary().with_variant(mysql.LONGBLOB(), 'mysql')


class MarcaConfig(db.Model):
    """Fila singleton (id=1) con la marca de la aplicación.

    Logo y favicon se guardan como BLOB: sobreviven a rebuilds de la imagen
    Docker y no requieren volumen. Los textos vacíos caen al default.
    """

    __tablename__ = 'marca_config'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(NOMBRE_MAX), nullable=False, default=NOMBRE_DEFECTO)
    titulo_sufijo = db.Column(db.String(SUFIJO_MAX), default=SUFIJO_DEFECTO)
    subtitulo = db.Column(db.String(SUBTITULO_MAX), default=SUBTITULO_DEFECTO)
    logo = db.Column(_IMAGEN)
    logo_mime = db.Column(db.String(50))
    favicon = db.Column(_IMAGEN)
    favicon_mime = db.Column(db.String(50))
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    def __repr__(self):
        return f'<MarcaConfig {self.nombre!r} logo={bool(self.logo)}>'


def get_marca():
    """Devuelve la fila singleton, creándola con valores por defecto si falta."""
    cfg = db.session.get(MarcaConfig, 1)
    if cfg is None:
        cfg = MarcaConfig(id=1)
        db.session.add(cfg)
        db.session.commit()
    return cfg


def marca_template_dict():
    """Dict inyectado a los templates como `marca`.

    - Cache por request en flask.g (lo consumen base/sidebar/login/error pages).
    - Si la DB falla, devuelve los defaults: las páginas de error deben poder
      renderizarse aunque la DB esté caída.
    - Sin request context (tests de unit) no arma URLs ni cachea.
    """
    from flask import g, has_request_context, url_for

    en_request = has_request_context()
    if en_request:
        cache = getattr(g, 'marca_cache', None)
        if cache is not None:
            return cache

    defecto = {
        'nombre': NOMBRE_DEFECTO,
        'sufijo': SUFIJO_DEFECTO,
        'subtitulo': SUBTITULO_DEFECTO,
        'tiene_logo': False,
        'tiene_favicon': False,
        'logo_mime': None,
        'favicon_mime': None,
        'logo_url': None,
        'favicon_url': None,
    }
    try:
        cfg = get_marca()
        data = {
            'nombre': (cfg.nombre or '').strip() or NOMBRE_DEFECTO,
            'sufijo': (cfg.titulo_sufijo or '').strip(),
            'subtitulo': (cfg.subtitulo or '').strip(),
            'tiene_logo': bool(cfg.logo),
            'tiene_favicon': bool(cfg.favicon),
            'logo_mime': cfg.logo_mime,
            'favicon_mime': cfg.favicon_mime,
            'logo_url': None,
            'favicon_url': None,
        }
        if en_request:
            if data['tiene_logo']:
                data['logo_url'] = url_for('marca.logo')
            if data['tiene_favicon']:
                data['favicon_url'] = url_for('marca.favicon')
    except Exception:
        data = defecto

    if en_request:
        g.marca_cache = data
    return data
