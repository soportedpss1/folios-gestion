import json
from datetime import date

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import String, cast
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from app.extensions import db
from app.models.centro import Centro
from app.models.entrega_folio import EntregaFolio
from app.models.folio import Folio
from app.models.tipo_certificado import TipoCertificado
from app.entregas.forms import EntregaCreateForm, EntregaEditForm, ImportarEntregaForm
from app.services import import_excel
from app.services import movimientos as mov
from app.services.audit import log_audit
from app.services.mensajes import REFRESQUE_INTENTE
from app.services.queries import get_or_404, usuario_activo
from app.utils import plural
from app.decorators import permiso_requerido


entregas_bp = Blueprint('entregas', __name__, url_prefix='/entregas')

HEADERS_FOLIOS = ['folio', 'tipoCert', 'anioCert', 'fecha', 'centro',
                  import_excel.COLUMNA_USUARIO]
MAX_PREVIA_MOSTRAR = 200


@entregas_bp.route('/')
@login_required
def index():
    page = request.args.get('page', 1, type=int)
    busqueda = request.args.get('busqueda', '').strip()[:50]
    centro_id = request.args.get('centroId', type=int)
    # type= date.fromisoformat devuelve None si el valor es inválido:
    # el filtro se ignora y la lista queda completa.
    desde = request.args.get('desde', type=date.fromisoformat)
    hasta = request.args.get('hasta', type=date.fromisoformat)

    query = EntregaFolio.query.options(
        selectinload(EntregaFolio.folio),
        selectinload(EntregaFolio.centro),
        selectinload(EntregaFolio.usuario),
    )
    if busqueda:
        # Folio.folio es Integer: LIKE directo deprecado (SADeprecationWarning)
        query = query.join(EntregaFolio.folio).filter(
            cast(Folio.folio, String).like(f'%{busqueda}%'))
    if centro_id:
        # filter() con columna explícita: filter_by tras el join del filtro
        # de folio resolvería la key contra la entidad joined (Folio).
        query = query.filter(EntregaFolio.centroId == centro_id)
    if desde:
        query = query.filter(EntregaFolio.fechaEntrega >= desde)
    if hasta:
        query = query.filter(EntregaFolio.fechaEntrega <= hasta)

    pagination = query.order_by(EntregaFolio.created_at.desc()) \
        .paginate(page=page, per_page=25, error_out=False)
    centros = Centro.query.filter_by(activo=True).order_by(Centro.name).all()
    return render_template('entregas/index.html', entregas=pagination.items,
                           pagination=pagination, centros=centros,
                           current_busqueda=busqueda, current_centro=centro_id,
                           current_desde=desde, current_hasta=hasta)


@entregas_bp.route('/api/folios-disponibles')
@login_required
def folios_disponibles():
    """Búsqueda paginada de folios disponibles para el select de nueva entrega.

    Evita renderizar un <select> con miles de <option> (antes cargaba todos los
    folios disponibles en cada GET del formulario).
    """
    q = request.args.get('q', '').strip()
    tipo_id = request.args.get('tipo', type=int)
    # limit solo lo manda el create (sin búsqueda pide el total del tipo);
    # sin el parámetro se mantiene el tope de 100 que usa editar entrega.
    limit = min(max(request.args.get('limit', 100, type=int), 1), mov.MAX_FOLIOS_SELECT)
    folios, total = mov.folios_disponibles(q, tipo_id, limit)
    response = jsonify(folios)
    # El select puede quedar truncado (total > limit): el JS avisa al usuario.
    response.headers['X-Folios-Total'] = str(total)
    return response


@entregas_bp.route('/create', methods=['GET', 'POST'])
@login_required
@permiso_requerido('entregas.gestionar', hacia='blueprint')
def create():

    form = EntregaCreateForm()
    # tipoFilter es solo filtro de interfaz (no es campo del form): se lee para
    # reseleccionar el tipo tras una revalidación de POST.
    tipo_actual = request.form.get('tipoFilter', type=int) if request.method == 'POST' else None
    # choices solo en POST y solo para los folios enviados (validación):
    # en GET el select se llena vía JS contra /api/folios-disponibles.
    seleccionados = request.form.getlist('folio_ids', type=int) if request.method == 'POST' else []
    form.folio_ids.choices = mov.choices_folios_entrega(seleccionados)
    form.centroId.choices = mov.choices_centros(
        None, placeholder='Seleccione el centro de salud')

    if form.validate_on_submit():
        foliosSeleccionados = form.folio_ids.data
        if not foliosSeleccionados:
            flash('Seleccione al menos un folio.', 'danger')
            return redirect(url_for('entregas.create'))

        try:
            count, omitidos = mov.crear_movimiento(
                modelo=EntregaFolio,
                fecha_field='fechaEntrega',
                folio_ids=foliosSeleccionados,
                fecha=form.fechaEntrega.data,
                centro_id=form.centroId.data,
                user=current_user,
                estado_origen='disponible',
                estado_destino='entregado',
                excluir_nulos=True,
                tabla_audit='entrega_folios',
                log_audit=log_audit,
            )
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('Registro duplicado: el folio ya tiene una entrega registrada por otra '
                  'operación. ' + REFRESQUE_INTENTE, 'danger')
            return redirect(url_for('entregas.create'))

        if omitidos:
            flash(
                f'{count} {plural(count, "entrega")} {plural(count, "registrada")}; '
                f'{omitidos} {plural(omitidos, "folio")} {plural(omitidos, "omitido")} '
                'porque ya no estaban disponibles. Refresque la lista.',
                'warning',
            )
        else:
            flash(
                f'{count} {plural(count, "entrega")} {plural(count, "registrada")} exitosamente.',
                'success',
            )
        return redirect(url_for('entregas.index'))

    tipos = TipoCertificado.query.filter_by(activo=True) \
        .order_by(TipoCertificado.name).all()
    return render_template('entregas/create.html', form=form, tipos=tipos,
                           tipo_actual=tipo_actual)


@entregas_bp.route('/plantilla')
@login_required
@permiso_requerido('entregas.importar')
def plantilla():
    tipo = TipoCertificado.query.filter_by(activo=True) \
        .order_by(TipoCertificado.name).first()
    centro = Centro.query.filter_by(activo=True).order_by(Centro.name).first()
    ejemplo = [1000, tipo.name if tipo else 'Tipo de certificado', 2026,
               date.today().strftime('%d/%m/%Y'),
               centro.name if centro else 'Nombre del centro',
               current_user.username]
    return import_excel.respuesta_plantilla(
        'plantilla_entregas.xlsx', HEADERS_FOLIOS, ejemplo)


@entregas_bp.route('/importar', methods=['GET', 'POST'])
@login_required
@permiso_requerido('entregas.importar')
def importar():

    form = ImportarEntregaForm()

    if form.validate_on_submit():
        try:
            filas = import_excel.leer_filas(
                form.archivo.data, HEADERS_FOLIOS,
                import_excel.MAX_FOLIOS_POR_ARCHIVO)
        except import_excel.ImportExcelError as e:
            flash(str(e), 'danger')
            return render_template('entregas/importar.html', form=form)

        preview, payload = mov.resolver_folios_para_importar(
            filas, estado='disponible', excluir_nulos=True)
        total_validos = sum(1 for p in preview if p['error'] is None)
        if not total_validos:
            flash('Ningún folio del archivo está disponible para entrega.', 'danger')
        centros_nombre = ', '.join(sorted(
            {p['centro'] for p in preview if p['error'] is None and p['centro']}))
        return render_template(
            'entregas/importar.html', form=form, preview=preview,
            payload_json=json.dumps(payload), total_validas=total_validos,
            max_mostrar=MAX_PREVIA_MOSTRAR,
            centros_nombre=centros_nombre,
        )
    return render_template('entregas/importar.html', form=form)


@entregas_bp.route('/importar/confirmar', methods=['POST'])
@login_required
@permiso_requerido('entregas.importar')
def importar_confirmar():

    items, error = import_excel.parsear_confirmacion(request.form.get('payload'))
    if error:
        flash(error, 'danger')
        return redirect(url_for('entregas.importar'))

    # El centro viene por fila en el payload (el hidden es editable):
    # revalida cada centro contra la DB antes de cualquier registro.
    cids = {cid for _, _, _, cid in items}
    centros = {c.id: c for c in Centro.query.filter(Centro.id.in_(cids)).all()}
    if any(cid not in centros or not centros[cid].activo for cid in cids):
        flash('Centro de salud inválido.', 'danger')
        return redirect(url_for('entregas.importar'))

    # Revalida contra la DB: el estado pudo cambiar desde la vista previa.
    # choices_folios_entrega solo devuelve los que siguen disponibles.
    # Duplicado en el payload: gana la última fila (igual que antes).
    mapa = {}
    for fid, uid, fecha, cid in items:
        mapa[fid] = (uid, fecha, cid)
    ids_validos = [fid for fid, _ in mov.choices_folios_entrega(list(mapa))]
    if not ids_validos:
        flash('Ningún folio sigue disponible para entrega.', 'warning')
        return redirect(url_for('entregas.importar'))

    # Atribución, fecha y centro por folio (el Excel manda por fila): un
    # crear_movimiento por (centro, responsable, fecha) — centros o fechas
    # distintas en un mismo archivo respetan su fila. uid inválido/inexistente
    # → fallback al actor (usuario_activo); audit siempre queda en el actor.
    grupos = {}
    for fid in ids_validos:
        uid, fecha, cid = mapa[fid]
        grupos.setdefault((cid, uid, fecha), []).append(fid)

    try:
        count = 0
        omitidos = 0
        for (cid, uid, fecha), fids in grupos.items():
            parcial, omitidos_parcial = mov.crear_movimiento(
                modelo=EntregaFolio,
                fecha_field='fechaEntrega',
                folio_ids=fids,
                fecha=fecha,
                centro_id=cid,
                user=usuario_activo(uid, current_user),
                actor=current_user,
                estado_origen='disponible',
                estado_destino='entregado',
                excluir_nulos=True,
                tabla_audit='entrega_folios',
                log_audit=log_audit,
            )
            count += parcial
            omitidos += omitidos_parcial
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash('Registro duplicado: el folio ya tiene una entrega registrada por otra '
              'operación. ' + REFRESQUE_INTENTE, 'danger')
        return redirect(url_for('entregas.index'))

    if omitidos:
        flash(
            f'{count} {plural(count, "entrega")} {plural(count, "registrada")}; '
            f'{omitidos} {plural(omitidos, "folio")} {plural(omitidos, "omitido")} '
            'porque ya no estaban disponibles. Refresque la lista.',
            'warning',
        )
    else:
        flash(
            f'{count} {plural(count, "entrega")} {plural(count, "registrada")} exitosamente.',
            'success',
        )
    return redirect(url_for('entregas.index'))


@entregas_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@permiso_requerido('entregas.gestionar', hacia='blueprint')
def edit(id):

    entrega = get_or_404(EntregaFolio, id)
    datos_anteriores = entrega.to_dict()

    form = EntregaEditForm()
    # El folio de una entrega no se cambia desde editar: choices con el folio
    # actual; cualquier otro valor en el POST queda fuera de choices.
    form.folio_id.choices = mov.choices_folio_actual(entrega.folio_id)
    form.centroId.choices = mov.choices_centros(entrega.centroId)

    if request.method == 'GET':
        form.folio_id.data = entrega.folio_id
        form.fechaEntrega.data = entrega.fechaEntrega
        form.centroId.data = entrega.centroId

    if form.validate_on_submit():
        devolucion = entrega.folio.devolucion
        # Con la devolución ya registrada, la entrega no puede re-apuntarse:
        # Reportes y Devoluciones divergirían para siempre sobre qué centro
        # tuvo el folio.
        if devolucion is not None and form.centroId.data != devolucion.centroId:
            flash('El folio ya fue devuelto: no puede cambiarse el centro '
                  'de esta entrega.', 'danger')
            return render_template('entregas/edit.html', form=form, entrega=entrega)
        if devolucion is not None and form.fechaEntrega.data > devolucion.fechaDevolucion:
            flash('La fecha de entrega no puede ser posterior a la '
                  'devolución registrada.', 'danger')
            return render_template('entregas/edit.html', form=form, entrega=entrega)
        try:
            entrega.fechaEntrega = form.fechaEntrega.data
            entrega.centroId = form.centroId.data

            log_audit(current_user.id, 'UPDATE', 'entrega_folios', entrega.id, datos_anteriores, entrega.to_dict())
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('Conflicto de concurrencia al actualizar la entrega. '
                  'Refresque la lista e intente de nuevo.', 'danger')
            return render_template('entregas/edit.html', form=form, entrega=entrega)

        flash('Entrega actualizada exitosamente.', 'success')
        return redirect(url_for('entregas.index'))

    return render_template('entregas/edit.html', form=form, entrega=entrega)
