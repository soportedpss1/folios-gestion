import json

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import String, cast
from sqlalchemy.orm import selectinload
from app.decorators import permiso_requerido
from app.extensions import db
from app.folios.forms import ImportarFolioForm
from app.models.folio import Folio
from app.models.tipo_certificado import TipoCertificado
from app.services import import_excel
from app.services.audit import log_audit
from app.services.permisos import puede
from app.services.queries import get_or_404
from app.utils import plural

folios_bp = Blueprint('folios', __name__, url_prefix='/folios')

HEADERS_FOLIO = ['folio']
MAX_PREVIA_MOSTRAR = 200


@folios_bp.route('/')
@login_required
def index():
    # tipo_cert se recorre fila a fila en la plantilla: sin esto son +25 queries/página
    query = Folio.query.options(selectinload(Folio.tipo_cert))

    anio = request.args.get('anioCert', type=int)
    tipo = request.args.get('tipoCert', type=int)
    estado = request.args.get('estado')
    busqueda = request.args.get('busqueda', '').strip()[:50]

    if anio:
        query = query.filter_by(anioCert=anio)
    if tipo:
        query = query.filter_by(tipoCert_id=tipo)
    if estado:
        if estado == 'nulo':
            query = query.filter_by(nulo=True)
        elif estado == 'digitado':
            query = query.filter_by(digitado=True, nulo=False)
        elif estado == 'escaneado':
            query = query.filter_by(escaneado=True, nulo=False)
        else:
            query = query.filter_by(estado=estado, nulo=False)
    if busqueda:
        # Folio.folio es Integer: LIKE directo deprecado (SADeprecationWarning)
        query = query.filter(cast(Folio.folio, String).like(f'%{busqueda}%'))

    page = request.args.get('page', 1, type=int)
    per_page = min(max(request.args.get('per_page', 25, type=int), 1), 200)
    # Folio.folio se repite entre año/tipo: sin Folio.id como desempate las
    # páginas se solapan y filas se repiten/saltan con LIMIT/OFFSET.
    pagination = query.order_by(Folio.folio, Folio.id).paginate(page=page, per_page=per_page, error_out=False)

    tipos = TipoCertificado.query.filter_by(activo=True).order_by(TipoCertificado.name).all()

    return render_template('folios/index.html',
        pagination=pagination,
        folios=pagination.items,
        tipos=tipos,
        current_anio=anio,
        current_tipo=tipo,
        current_estado=estado,
        current_busqueda=busqueda
    )


@folios_bp.route('/<int:id>')
@login_required
def details(id):
    folio = get_or_404(Folio, id)
    return render_template('folios/details.html', folio=folio)


@folios_bp.route('/update-status', methods=['POST'])
@login_required
def update_status():
    if not puede('folios.actualizar'):
        return jsonify({'success': False, 'message': 'No tiene permisos.'}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'message': 'Cuerpo JSON inválido.'}), 400

    folio_ids = data.get('folio_ids')
    if not isinstance(folio_ids, list) or not folio_ids:
        return jsonify({'success': False, 'message': 'Se requiere una lista de folios.'}), 400
    if not all(isinstance(i, int) and not isinstance(i, bool) for i in folio_ids):
        return jsonify({'success': False, 'message': "El campo 'folio_ids' debe ser una lista de enteros."}), 400
    if len(folio_ids) > 1000:
        return jsonify({'success': False, 'message': 'Máximo 1000 folios por operación.'}), 400

    flags = {}
    for key in ('digitado', 'escaneado', 'nulo'):
        value = data.get(key)
        if not isinstance(value, bool):
            return jsonify({'success': False, 'message': f"Falta o es inválido el campo '{key}'."}), 400
        flags[key] = value
    digitado, escaneado, nulo = flags['digitado'], flags['escaneado'], flags['nulo']

    folios = Folio.query.filter(Folio.id.in_(folio_ids)).all()
    updated = 0
    for folio in folios:
        old = {'digitado': folio.digitado, 'escaneado': folio.escaneado, 'nulo': folio.nulo}
        folio.digitado = digitado
        folio.escaneado = escaneado
        folio.nulo = nulo
        log_audit(current_user.id, 'UPDATE', 'folios', folio.id, old, {'digitado': digitado, 'escaneado': escaneado, 'nulo': nulo})
        updated += 1

    db.session.commit()
    return jsonify({
        'success': True,
        'message': f'{updated} {plural(updated, "folio")} {plural(updated, "actualizado")}.',
    })


def _preview_digitado(filas):
    """Filas del Excel → (preview, payload).

    Un número de folio no es único (se repite entre año/tipo): cada número
    matchea todos los folios DB con ese número. El preview muestra cuántas
    filas matchean y cuántas quedarían marcadas; el payload lleva solo los
    números válidos.
    """
    preview = []
    numeros = []
    vistos = set()
    for i, fila in enumerate(filas, 1):
        numero = import_excel.a_entero(fila.get('folio'))
        if numero is None or numero <= 0:
            preview.append({'n': i, 'folio': fila.get('folio'), 'encontrados': 0,
                            'ya_digitado': 0, 'a_actualizar': 0,
                            'error': 'Número inválido'})
            continue
        if numero in vistos:
            preview.append({'n': i, 'folio': numero, 'encontrados': 0,
                            'ya_digitado': 0, 'a_actualizar': 0,
                            'error': 'Repetido en el archivo'})
            continue
        vistos.add(numero)
        numeros.append(numero)
        preview.append({'n': i, 'folio': numero, 'encontrados': None,
                        'ya_digitado': 0, 'a_actualizar': 0, 'error': None})

    encontrados = {}
    if numeros:
        for folio in Folio.query.filter(Folio.folio.in_(numeros)).all():
            encontrados.setdefault(folio.folio, []).append(folio)

    payload = []
    for item in preview:
        if item['error'] is not None:
            continue
        filas_folio = encontrados.get(item['folio'], [])
        item['encontrados'] = len(filas_folio)
        item['ya_digitado'] = sum(1 for f in filas_folio if f.digitado)
        item['a_actualizar'] = len(filas_folio) - item['ya_digitado']
        if not filas_folio:
            item['error'] = 'No existe'
            continue
        payload.append(item['folio'])
    return preview, payload


def _parsear_payload(payload_raw):
    """Hidden payload → lista de números únicos, o None si es inválido."""
    try:
        datos = json.loads(payload_raw or '')
    except (TypeError, ValueError):
        return None
    if not isinstance(datos, list) or not datos \
            or len(datos) > import_excel.MAX_FOLIOS_POR_ARCHIVO:
        return None
    numeros = set()
    for valor in datos:
        if not isinstance(valor, int) or isinstance(valor, bool) or valor <= 0:
            return None
        numeros.add(valor)
    return numeros


@folios_bp.route('/plantilla')
@login_required
@permiso_requerido('folios.importar')
def plantilla():
    return import_excel.respuesta_plantilla(
        'plantilla_folios.xlsx', HEADERS_FOLIO, [1000])


@folios_bp.route('/importar', methods=['GET', 'POST'])
@login_required
@permiso_requerido('folios.importar')
def importar():
    form = ImportarFolioForm()
    if form.validate_on_submit():
        try:
            filas = import_excel.leer_filas(
                form.archivo.data, HEADERS_FOLIO,
                import_excel.MAX_FOLIOS_POR_ARCHIVO)
        except import_excel.ImportExcelError as e:
            flash(str(e), 'danger')
            return render_template('folios/importar.html', form=form)

        preview, payload = _preview_digitado(filas)
        total_validos = sum(1 for p in preview if p['error'] is None)
        if not total_validos:
            flash('Ningún folio del archivo coincide con la base de datos.',
                  'danger')
        return render_template(
            'folios/importar.html', form=form, preview=preview,
            payload_json=json.dumps(payload), total_validas=total_validos,
            max_mostrar=MAX_PREVIA_MOSTRAR,
        )
    return render_template('folios/importar.html', form=form)


@folios_bp.route('/importar/confirmar', methods=['POST'])
@login_required
@permiso_requerido('folios.importar')
def importar_confirmar():
    numeros = _parsear_payload(request.form.get('payload'))
    if numeros is None:
        flash('Datos de importación inválidos. Repita la operación.', 'danger')
        return redirect(url_for('folios.importar'))

    # Revalida contra la DB: el hidden es editable y los folios pudieron
    # cambiar desde la vista previa.
    actualizados = 0
    for folio in Folio.query.filter(Folio.folio.in_(numeros)).all():
        if folio.digitado:
            continue
        old = {'digitado': folio.digitado}
        folio.digitado = True
        log_audit(current_user.id, 'UPDATE', 'folios', folio.id, old,
                  {'digitado': True})
        actualizados += 1

    db.session.commit()
    if actualizados:
        flash(f'{actualizados} {plural(actualizados, "folio")} '
              f'{plural(actualizados, "marcado")} como digitado.', 'success')
    else:
        flash('Ningún folio nuevo por marcar: todos ya estaban digitados.',
              'warning')
    return redirect(url_for('folios.index'))
