import json

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import String, cast
from sqlalchemy.orm import selectinload
from app.decorators import permiso_requerido
from app.extensions import db
from app.folios.forms import ComentarioFolioForm, ImportarFolioForm, TransferirFolioForm
from app.models.centro import Centro
from app.models.folio import Folio
from app.models.folio_comentario import FolioComentario
from app.models.tipo_certificado import TipoCertificado
from app.models.transferencia_folio import TransferenciaFolio
from app.services import import_excel
from app.services.audit import log_audit
from app.services.escaneos import validar_carpeta
from app.services.movimientos import choices_centros
from app.services.permisos import puede
from app.services.queries import get_or_404
from app.utils import plural, quiere_json

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
    return render_template('folios/details.html', **_contexto_detalle(folio))


def _contexto_detalle(folio, form=None, form_transfer=None):
    """Datos del detalle: folio, form de comentario, form de transferencia y
    historiales (comentarios y transferencias, más recientes primero, con
    relaciones eager-loaded para evitar N+1)."""
    comentarios = (FolioComentario.query
                   .filter_by(folio_id=folio.id)
                   .options(selectinload(FolioComentario.usuario))
                   .order_by(FolioComentario.createAt.desc(),
                             FolioComentario.id.desc())
                   .all())
    transferencias = (TransferenciaFolio.query
                      .filter_by(folio_id=folio.id)
                      .options(selectinload(TransferenciaFolio.centro_origen),
                               selectinload(TransferenciaFolio.centro_destino),
                               selectinload(TransferenciaFolio.usuario))
                      .order_by(TransferenciaFolio.fecha.desc(),
                                TransferenciaFolio.id.desc())
                      .all())
    if form_transfer is None:
        form_transfer = TransferirFolioForm()
    if folio.entrega:
        form_transfer.centroDestino.choices = _choices_destino(folio.entrega.centroId)
    return {
        'folio': folio,
        'form': form or ComentarioFolioForm(),
        'form_transfer': form_transfer,
        'comentarios': comentarios,
        'transferencias': transferencias,
    }


def _choices_destino(actual_id):
    """Centros activos para el destino, sin el centro actual del folio."""
    return [(cid, nombre) for cid, nombre
            in choices_centros(None, placeholder='Seleccione el centro destino…')
            if cid and cid != actual_id]


@folios_bp.route('/<int:id>/comentarios', methods=['POST'])
@login_required
def crear_comentario(id):
    """Cualquier rol autenticado puede anotar: es trazabilidad, no edición."""
    folio = get_or_404(Folio, id)
    form = ComentarioFolioForm()
    if not form.validate_on_submit():
        # Re-render del detalle con el error del campo (vacío / >1000).
        return render_template('folios/details.html',
                               **_contexto_detalle(folio, form))

    comentario = FolioComentario(
        folio_id=folio.id,
        user_id=current_user.id,
        texto=form.texto.data.strip(),
    )
    db.session.add(comentario)
    db.session.flush()
    log_audit(current_user.id, 'INSERT', 'folio_comentarios', comentario.id,
              None, {'texto': comentario.texto})
    db.session.commit()
    flash('Comentario añadido.', 'success')
    return redirect(url_for('folios.details', id=folio.id) + '#comentarios')


@folios_bp.route('/comentarios/<int:cid>/editar', methods=['POST'])
@login_required
def editar_comentario(cid):
    comentario = get_or_404(FolioComentario, cid)
    ancla = url_for('folios.details', id=comentario.folio_id) + '#comentarios'

    if comentario.user_id != current_user.id:
        flash('No tiene permisos para esta acción.', 'danger')
        return redirect(ancla)

    form = ComentarioFolioForm()
    if not form.validate_on_submit():
        flash('El comentario no puede estar vacío ni superar 1000 caracteres.',
              'danger')
        return redirect(ancla)

    old = {'texto': comentario.texto}
    comentario.texto = form.texto.data.strip()
    log_audit(current_user.id, 'UPDATE', 'folio_comentarios', comentario.id,
              old, {'texto': comentario.texto})
    db.session.commit()
    flash('Comentario actualizado.', 'success')
    return redirect(ancla)


@folios_bp.route('/comentarios/<int:cid>/borrar', methods=['POST'])
@login_required
def borrar_comentario(cid):
    comentario = get_or_404(FolioComentario, cid)
    ancla = url_for('folios.details', id=comentario.folio_id) + '#comentarios'

    if comentario.user_id != current_user.id and not current_user.is_admin():
        flash('No tiene permisos para esta acción.', 'danger')
        return redirect(ancla)

    old = {'texto': comentario.texto}
    db.session.delete(comentario)
    log_audit(current_user.id, 'DELETE', 'folio_comentarios', cid, old, None)
    db.session.commit()
    flash('Comentario eliminado.', 'success')
    return redirect(ancla)


@folios_bp.route('/validar-escaneados', methods=['POST'])
@login_required
@permiso_requerido('escaneos.subir', hacia='blueprint')
def validar_escaneados():
    """Reconcilia scans/ contra la DB (marca y desmarca folios escaneados)."""
    reporte = validar_carpeta(current_user.id)

    if reporte['error_raiz']:
        flash('No existe la carpeta de escaneados: nada fue validado.',
              'danger')
        return redirect(url_for('folios.index'))

    m, d = reporte['marcados'], reporte['desmarcados']
    partes = [f'{m} {plural(m, "folio")} {plural(m, "marcado")}',
              f'{d} {plural(d, "folio")} {plural(d, "desmarcado")}']
    if reporte['ignorados']:
        i = reporte['ignorados']
        partes.append(f'{i} {plural(i, "archivo")} {plural(i, "ignorado")}')
    flash('Validación completada: ' + ', '.join(partes) + '.', 'success')
    if reporte['anios_sin_carpeta']:
        anios = ', '.join(str(a) for a in reporte['anios_sin_carpeta'])
        flash(f'Sin carpeta para {anios}: esos folios no se desmarcaron.',
              'warning')
    return redirect(url_for('folios.index'))


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


# --- estado 'perdido' (marcaje reversible, solo desde el detalle) ---

ESTADOS_MARCABLES_PERDIDO = ('disponible', 'entregado')


def _destino_de_recuperacion(folio):
    """Estado previo DERIVADO del registro de entrega: con EntregaFolio →
    entregado; sin registro → disponible."""
    return 'entregado' if folio.entrega is not None else 'disponible'


def _cambiar_estado(folio, destino):
    """Transición del estado del folio con auditoría (el llamador valida)."""
    old = {'estado': folio.estado}
    folio.estado = destino
    log_audit(current_user.id, 'UPDATE', 'folios', folio.id, old,
              {'estado': destino})


@folios_bp.route('/<int:id>/perder', methods=['POST'])
@permiso_requerido('folios.actualizar', hacia='blueprint')
def perder(id):
    folio = get_or_404(Folio, id)
    if folio.estado not in ESTADOS_MARCABLES_PERDIDO:
        flash('Solo se pueden marcar como perdidos folios disponibles '
              'o entregados.', 'danger')
        return redirect(url_for('folios.details', id=folio.id))
    _cambiar_estado(folio, 'perdido')
    db.session.commit()
    flash('Folio marcado como perdido.', 'success')
    return redirect(url_for('folios.details', id=folio.id))


@folios_bp.route('/<int:id>/recuperar', methods=['POST'])
@permiso_requerido('folios.actualizar', hacia='blueprint')
def recuperar(id):
    folio = get_or_404(Folio, id)
    if folio.estado != 'perdido':
        flash('Solo los folios perdidos se pueden recuperar.', 'danger')
        return redirect(url_for('folios.details', id=folio.id))
    _cambiar_estado(folio, _destino_de_recuperacion(folio))
    db.session.commit()
    flash('Folio recuperado.', 'success')
    return redirect(url_for('folios.details', id=folio.id))


# --- corrección manual de estado (sin entrega/devolución que lo justifique) ---

ESTADOS_CORREGIBLES = ('disponible', 'entregado', 'devuelto')


@folios_bp.route('/<int:id>/estado', methods=['GET', 'POST'])
@permiso_requerido('folios.actualizar', hacia='blueprint')
def cambiar_estado(id):
    """Corrige a mano el estado del folio (auditado; 'perdido' no entra:

    su marcaje y recuperación son un flujo propio con reglas derivadas del
    registro de entrega)."""
    folio = get_or_404(Folio, id)
    if request.method == 'GET':
        # Panel de inspecciones (JSON): campos del form. Sin JSON no hay
        # form que mostrar en GET → de vuelta al detalle.
        if quiere_json():
            return jsonify(ok=True, campos_html=render_template(
                'folios/_form_estado.html', folio=folio))
        return redirect(url_for('folios.details', id=folio.id))
    nuevo = request.form.get('estado', '').strip()
    if nuevo not in ESTADOS_CORREGIBLES:
        if quiere_json():
            return jsonify(ok=False, error='Estado inválido.'), 400
        flash('Estado inválido.', 'danger')
        return redirect(url_for('folios.details', id=folio.id))
    if nuevo == folio.estado:
        if quiere_json():
            return jsonify(ok=False,
                           error='Ese ya es el estado del folio.'), 400
        flash('Ese ya es el estado del folio.', 'info')
        return redirect(url_for('folios.details', id=folio.id))
    _cambiar_estado(folio, nuevo)
    db.session.commit()
    if quiere_json():
        return jsonify(ok=True)
    flash('Estado actualizado exitosamente.', 'success')
    return redirect(url_for('folios.details', id=folio.id))


# --- transferencia entre centros de salud ---

@folios_bp.route('/<int:id>/transferir', methods=['POST'])
@permiso_requerido('folios.transferir', hacia='blueprint')
def transferir(id):
    """Pasa un folio entregado de un centro a otro, con motivo obligatorio.

    Cambia el centro de la EntregaFolio activa y deja registro inmutable en
    transferencia_folios + audit (UPDATE entrega_folios, INSERT transferencia).
    """
    folio = get_or_404(Folio, id)
    if folio.estado != 'entregado' or folio.entrega is None:
        flash('Solo se pueden transferir folios entregados.', 'danger')
        return redirect(url_for('folios.details', id=folio.id))

    form = TransferirFolioForm()
    form.centroDestino.choices = _choices_destino(folio.entrega.centroId)
    if not form.validate_on_submit():
        # Re-render del detalle con los errores (destino inválido / sin motivo).
        return render_template('folios/details.html',
                               **_contexto_detalle(folio, form_transfer=form))

    centro_origen = folio.entrega.centroId
    centro_destino = form.centroDestino.data
    old = {'centroId': centro_origen}
    folio.entrega.centroId = centro_destino
    registro = TransferenciaFolio(
        folio_id=folio.id,
        centroOrigenId=centro_origen,
        centroDestinoId=centro_destino,
        userId=current_user.id,
        motivo=form.motivo.data.strip(),
    )
    db.session.add(registro)
    db.session.flush()
    log_audit(current_user.id, 'UPDATE', 'entrega_folios', folio.entrega.id,
              old, {'centroId': centro_destino})
    log_audit(current_user.id, 'INSERT', 'transferencia_folios', registro.id,
              None, registro.to_dict())
    db.session.commit()
    flash('Folio transferido exitosamente.', 'success')
    return redirect(url_for('folios.details', id=folio.id))


@folios_bp.route('/transferencias')
@login_required
def transferencias():
    """Seguimiento global de transferencias (paginado, con filtros)."""
    query = TransferenciaFolio.query.options(
        selectinload(TransferenciaFolio.folio),
        selectinload(TransferenciaFolio.centro_origen),
        selectinload(TransferenciaFolio.centro_destino),
        selectinload(TransferenciaFolio.usuario),
    )

    origen = request.args.get('origen', type=int)
    destino = request.args.get('destino', type=int)
    busqueda = request.args.get('busqueda', '').strip()[:50]

    if origen:
        query = query.filter(TransferenciaFolio.centroOrigenId == origen)
    if destino:
        query = query.filter(TransferenciaFolio.centroDestinoId == destino)
    if busqueda:
        query = (query.join(Folio, Folio.id == TransferenciaFolio.folio_id)
                    .filter(cast(Folio.folio, String).like(f'%{busqueda}%')))

    page = request.args.get('page', 1, type=int)
    per_page = min(max(request.args.get('per_page', 25, type=int), 1), 200)
    pagination = query.order_by(TransferenciaFolio.fecha.desc(),
                                TransferenciaFolio.id.desc()) \
                      .paginate(page=page, per_page=per_page, error_out=False)

    centros = Centro.query.order_by(Centro.name).all()
    return render_template('folios/transferencias.html',
        pagination=pagination,
        transferencias=pagination.items,
        centros=centros,
        current_origen=origen,
        current_destino=destino,
        current_busqueda=busqueda,
    )


def _preview_flag(filas, attr):
    """Filas del Excel → (preview, payload) para la bandera booleana `attr`.

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
                            'ya_marcado': 0, 'a_actualizar': 0,
                            'error': 'Número inválido'})
            continue
        if numero in vistos:
            preview.append({'n': i, 'folio': numero, 'encontrados': 0,
                            'ya_marcado': 0, 'a_actualizar': 0,
                            'error': 'Repetido en el archivo'})
            continue
        vistos.add(numero)
        numeros.append(numero)
        preview.append({'n': i, 'folio': numero, 'encontrados': None,
                        'ya_marcado': 0, 'a_actualizar': 0, 'error': None})

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
        item['ya_marcado'] = sum(1 for f in filas_folio if getattr(f, attr))
        item['a_actualizar'] = len(filas_folio) - item['ya_marcado']
        if not filas_folio:
            item['error'] = 'No existe'
            continue
        payload.append(item['folio'])
    return preview, payload


def _preview_digitado(filas):
    """Filas del Excel → (preview, payload) para marcar digitado."""
    return _preview_flag(filas, 'digitado')


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


@folios_bp.route('/importar-nulos', methods=['GET', 'POST'])
@login_required
@permiso_requerido('folios.importar')
def importar_nulos():
    """Mismo flujo que importar(), pero marca la bandera `nulo`."""
    form = ImportarFolioForm()
    if form.validate_on_submit():
        try:
            filas = import_excel.leer_filas(
                form.archivo.data, HEADERS_FOLIO,
                import_excel.MAX_FOLIOS_POR_ARCHIVO)
        except import_excel.ImportExcelError as e:
            flash(str(e), 'danger')
            return render_template('folios/importar.html', form=form,
                                   modo='nulo')

        preview, payload = _preview_flag(filas, 'nulo')
        total_validos = sum(1 for p in preview if p['error'] is None)
        if not total_validos:
            flash('Ningún folio del archivo coincide con la base de datos.',
                  'danger')
        return render_template(
            'folios/importar.html', form=form, preview=preview,
            payload_json=json.dumps(payload), total_validas=total_validos,
            max_mostrar=MAX_PREVIA_MOSTRAR, modo='nulo',
        )
    return render_template('folios/importar.html', form=form, modo='nulo')


@folios_bp.route('/importar-nulos/confirmar', methods=['POST'])
@login_required
@permiso_requerido('folios.importar')
def importar_nulos_confirmar():
    numeros = _parsear_payload(request.form.get('payload'))
    if numeros is None:
        flash('Datos de importación inválidos. Repita la operación.', 'danger')
        return redirect(url_for('folios.importar_nulos'))

    # Revalida contra la DB: el hidden es editable y los folios pudieron
    # cambiar desde la vista previa.
    actualizados = 0
    for folio in Folio.query.filter(Folio.folio.in_(numeros)).all():
        if folio.nulo:
            continue
        old = {'nulo': folio.nulo}
        folio.nulo = True
        log_audit(current_user.id, 'UPDATE', 'folios', folio.id, old,
                  {'nulo': True})
        actualizados += 1

    db.session.commit()
    if actualizados:
        flash(f'{actualizados} {plural(actualizados, "folio")} '
              f'{plural(actualizados, "marcado")} como nulo.', 'success')
    else:
        flash('Ningún folio nuevo por marcar: todos ya estaban nulos.',
              'warning')
    return redirect(url_for('folios.index'))
