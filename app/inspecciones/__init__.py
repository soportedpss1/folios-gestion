"""Inspecciones: detecta errores humanos ya registrados en los datos.

Solo lectura: cada chequeo lista hallazgos con un link a la pantalla de
edición del módulo dueño (URLS_CORREGIR). La corrección ocurre allí.
"""

from flask import Blueprint, abort, render_template, request, url_for
from flask_login import login_required

from app.decorators import permiso_requerido
from app.services.inspecciones import CHEQUEOS, URLS_CORREGIR

inspecciones_bp = Blueprint('inspecciones', __name__, url_prefix='/inspecciones')


@inspecciones_bp.route('/')
@login_required
@permiso_requerido('inspecciones.ver')
def index():
    conteos = {clave: c['query']().count() for clave, c in CHEQUEOS.items()}
    return render_template('inspecciones/index.html', chequeos=CHEQUEOS,
                           conteos=conteos)


@inspecciones_bp.route('/<clave>')
@login_required
@permiso_requerido('inspecciones.ver')
def detalle(clave):
    chequeo = CHEQUEOS.get(clave)
    if chequeo is None:
        abort(404)
    pag = chequeo['query']().paginate(
        page=request.args.get('page', 1, type=int), per_page=25,
        error_out=False)
    hallazgos = []
    for row in pag.items:
        h = chequeo['formatear'](row)
        h['url'] = url_for(URLS_CORREGIR[h['modulo']], id=h['registro_id'])
        hallazgos.append(h)
    return render_template('inspecciones/detalle.html', clave=clave,
                           chequeo=chequeo, hallazgos=hallazgos,
                           pagination=pag)
