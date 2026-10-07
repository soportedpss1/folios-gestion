"""Módulo admin de marca: nombre, subtítulo, logo y favicon de la app."""

from flask import Blueprint, Response, abort, flash, redirect, render_template, url_for
from flask_login import current_user

from app.decorators import admin_required
from app.extensions import db, limiter
from app.marca.forms import MarcaForm
from app.models.marca import (
    IMAGEN_MAX_BYTES,
    MIME_POR_EXTENSION,
    get_marca,
)
from app.services.audit import log_audit

marca_bp = Blueprint('marca', __name__, url_prefix='/marca')


def _mime_de(filename):
    """MIME permitido según la extensión, o None si no está permitida."""
    ext = (filename or '').rpartition('.')[2].lower()
    return MIME_POR_EXTENSION.get(ext)


def _imagen_de(archivo, etiqueta, errores):
    """Lee y valida la subida. Devuelve (bytes, mime) o None (error en `errores`)."""
    datos = archivo.read()
    if len(datos) > IMAGEN_MAX_BYTES:
        errores.append(f'{etiqueta}: máximo {IMAGEN_MAX_BYTES // 1024} KB.')
        return None
    mime = _mime_de(archivo.filename)
    if mime is None:
        errores.append(f'{etiqueta}: formato no permitido (PNG, JPG, SVG o WEBP).')
        return None
    if not datos:
        errores.append(f'{etiqueta}: el archivo está vacío.')
        return None
    return datos, mime


def _imagen_response(blob, mime):
    return Response(blob, mimetype=mime or 'image/png', headers={
        'X-Content-Type-Options': 'nosniff',
        'Cache-Control': 'public, max-age=3600',
    })


def _vista(form):
    return render_template('marca/index.html', form=form, cfg=get_marca())


def _snapshot(cfg):
    return {
        'nombre': cfg.nombre,
        'titulo_sufijo': cfg.titulo_sufijo,
        'subtitulo': cfg.subtitulo,
        'tiene_logo': bool(cfg.logo),
        'tiene_favicon': bool(cfg.favicon),
    }


@marca_bp.route('/logo')
@limiter.exempt
def logo():
    """Logo público (lo necesita la página de login, sin sesión)."""
    cfg = get_marca()
    if not cfg.logo:
        abort(404)
    return _imagen_response(cfg.logo, cfg.logo_mime)


@marca_bp.route('/favicon')
@limiter.exempt
def favicon():
    """Favicon público: se pide en cada carga de página."""
    cfg = get_marca()
    if not cfg.favicon:
        abort(404)
    return _imagen_response(cfg.favicon, cfg.favicon_mime)


@marca_bp.route('/')
@admin_required
def index():
    form = MarcaForm()
    cfg = get_marca()
    form.nombre.data = cfg.nombre
    form.titulo_sufijo.data = cfg.titulo_sufijo
    form.subtitulo.data = cfg.subtitulo
    return _vista(form)


@marca_bp.route('/', methods=['POST'])
@admin_required
def guardar():
    form = MarcaForm()
    if not form.validate_on_submit():
        return _vista(form)

    errores = []
    subidas = {}
    for campo, etiqueta in (('logo', 'Logo'), ('favicon', 'Favicon')):
        archivo = getattr(form, campo).data
        if archivo and archivo.filename:
            imagen = _imagen_de(archivo, etiqueta, errores)
            if imagen is not None:
                subidas[campo] = imagen
    if errores:
        for error in errores:
            flash(error, 'danger')
        return _vista(form)

    cfg = get_marca()
    antes = _snapshot(cfg)
    cfg.nombre = form.nombre.data.strip()
    cfg.titulo_sufijo = (form.titulo_sufijo.data or '').strip()
    cfg.subtitulo = (form.subtitulo.data or '').strip()
    for campo, (datos, mime) in subidas.items():
        setattr(cfg, campo, datos)
        setattr(cfg, f'{campo}_mime', mime)

    log_audit(
        current_user.id, 'UPDATE', 'marca_config', cfg.id, antes,
        {**_snapshot(cfg), **{f'{c}_nuevo': True for c in subidas}},
    )
    db.session.commit()
    flash('Marca guardada.', 'success')
    return redirect(url_for('marca.index'))


def _quitar(campo, etiqueta):
    cfg = get_marca()
    antes = _snapshot(cfg)
    setattr(cfg, campo, None)
    setattr(cfg, f'{campo}_mime', None)
    log_audit(current_user.id, 'UPDATE', 'marca_config', cfg.id, antes, _snapshot(cfg))
    db.session.commit()
    flash(f'{etiqueta} eliminado.', 'success')
    return redirect(url_for('marca.index'))


@marca_bp.route('/quitar-logo', methods=['POST'])
@admin_required
def quitar_logo():
    return _quitar('logo', 'Logo')


@marca_bp.route('/quitar-favicon', methods=['POST'])
@admin_required
def quitar_favicon():
    return _quitar('favicon', 'Favicon')
