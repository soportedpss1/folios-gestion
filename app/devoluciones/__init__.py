import json
from datetime import date

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import String, cast
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from app.extensions import db
from app.models.centro import Centro
from app.models.devolucion_folio import DevolucionFolio
from app.models.folio import Folio
from app.models.tipo_certificado import TipoCertificado
from app.devoluciones.forms import DevolucionForm, DevolucionEditForm, ImportarDevolucionForm
from app.services import import_excel
from app.services import movimientos as mov
from app.services.audit import log_audit
from app.services.mensajes import REFRESQUE_INTENTE
from app.services.queries import get_or_404, usuario_activo
from app.utils import plural
from app.decorators import permiso_requerido

devoluciones_bp = Blueprint('devoluciones', __name__, url_prefix='/devoluciones')

HEADERS_FOLIOS = ['folio', 'tipoCert', 'anioCert', 'fecha', 'centro',
                  import_excel.COLUMNA_USUARIO]
MAX_PREVIA_MOSTRAR = 200


@devoluciones_bp.route('/')
@login_required
def index():
    page = request.args.get('page', 1, type=int)
    busqueda = request.args.get('busqueda', '').strip()[:50]
    centro_id = request.args.get('centroId', type=int)
    # type= date.fromisoformat devuelve None si el valor es inválido:
    # el filtro se ignora y la lista queda completa.
    desde = request.args.get('desde', type=date.fromisoformat)
    hasta = request.args.get('hasta', type=date.fromisoformat)

    query = DevolucionFolio.query.options(
        selectinload(DevolucionFolio.folio),
        selectinload(DevolucionFolio.centro),
        selectinload(DevolucionFolio.usuario),
    )
    if busqueda:
        # Folio.folio es Integer: LIKE directo deprecado (SADeprecationWarning)
        query = query.join(DevolucionFolio.folio).filter(
            cast(Folio.folio, String).like(f'%{busqueda}%'))
    if centro_id:
        # filter() con columna explícita: filter_by tras el join del filtro
        # de folio resolvería la key contra la entidad joined (Folio).
        query = query.filter(DevolucionFolio.centroId == centro_id)
    if desde:
        query = query.filter(DevolucionFolio.fechaDevolucion >= desde)
    if hasta:
        query = query.filter(DevolucionFolio.fechaDevolucion <= hasta)

    pagination = query.order_by(DevolucionFolio.created_at.desc()) \
        .paginate(page=page, per_page=25, error_out=False)
    centros = Centro.query.filter_by(activo=True).order_by(Centro.name).all()
    return render_template('devoluciones/index.html', devoluciones=pagination.items,
                           pagination=pagination, centros=centros,
                           current_busqueda=busqueda, current_centro=centro_id,
                           current_desde=desde, current_hasta=hasta)


@devoluciones_bp.route('/create', methods=['GET', 'POST'])
@login_required
@permiso_requerido('devoluciones.gestionar', hacia='blueprint')
def create():

    form = DevolucionForm()
    # tipoFilter es solo filtro de interfaz (no es campo del form): se lee para
    # reseleccionar el tipo tras una revalidación de POST.
    tipo_actual = request.form.get('tipoFilter', type=int) if request.method == 'POST' else None
    # choices solo para los ids enviados y solo del centro elegido: la lista
    # completa del centro podía cargar miles de filas en cada validación.
    centro_seleccionado = form.centroId.data if request.method == 'POST' else None
    seleccionados = request.form.getlist('folio_ids', type=int) if request.method == 'POST' else []
    form.folio_ids.choices = mov.choices_folios_devolucion(seleccionados, centro_seleccionado)
    form.centroId.choices = mov.choices_centros(
        None, placeholder='Seleccione el centro de salud')

    if form.validate_on_submit():
        foliosSeleccionados = form.folio_ids.data
        if not foliosSeleccionados:
            flash('Seleccione al menos un folio.', 'danger')
            return redirect(url_for('devoluciones.create'))

        try:
            count, omitidos = mov.crear_movimiento(
                modelo=DevolucionFolio,
                fecha_field='fechaDevolucion',
                folio_ids=foliosSeleccionados,
                fecha=form.fechaDevolucion.data,
                centro_id=form.centroId.data,
                user=current_user,
                estado_origen='entregado',
                estado_destino='devuelto',
                excluir_nulos=False,
                tabla_audit='devolucion_folios',
                log_audit=log_audit,
            )
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('Registro duplicado: el folio ya tiene una devolución registrada por otra '
                  'operación. ' + REFRESQUE_INTENTE, 'danger')
            return redirect(url_for('devoluciones.create'))

        if omitidos:
            flash(
                f'{count} {plural(count, "devolución", "devoluciones")} {plural(count, "registrada")}; '
                f'{omitidos} {plural(omitidos, "folio")} {plural(omitidos, "omitido")} '
                'porque ya no estaban entregados. Refresque la lista.',
                'warning',
            )
        else:
            flash(
                f'{count} {plural(count, "devolución", "devoluciones")} '
                f'{plural(count, "registrada")} exitosamente.',
                'success',
            )
        return redirect(url_for('devoluciones.index'))

    tipos = TipoCertificado.query.filter_by(activo=True) \
        .order_by(TipoCertificado.name).all()
    return render_template('devoluciones/create.html', form=form, tipos=tipos,
                           tipo_actual=tipo_actual)


@devoluciones_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@permiso_requerido('devoluciones.gestionar', hacia='blueprint')
def edit(id):

    devolucion = get_or_404(DevolucionFolio, id)
    datos_anteriores = devolucion.to_dict()

    form = DevolucionEditForm()
    # El folio de una devolución no se cambia desde editar: choices con el
    # folio actual; cualquier otro valor en el POST queda fuera de choices.
    form.folio_id.choices = mov.choices_folio_actual(devolucion.folio_id)
    form.centroId.choices = mov.choices_centros(devolucion.centroId)

    if request.method == 'GET':
        form.folio_id.data = devolucion.folio_id
        form.fechaDevolucion.data = devolucion.fechaDevolucion
        form.centroId.data = devolucion.centroId

    if form.validate_on_submit():
        try:
            devolucion.fechaDevolucion = form.fechaDevolucion.data
            devolucion.centroId = form.centroId.data

            log_audit(current_user.id, 'UPDATE', 'devolucion_folios', devolucion.id, datos_anteriores, devolucion.to_dict())
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('Conflicto de concurrencia al actualizar la devolución. '
                  'Refresque la lista e intente de nuevo.', 'danger')
            return render_template('devoluciones/edit.html', form=form, devolucion=devolucion)

        flash('Devolución actualizada exitosamente.', 'success')
        return redirect(url_for('devoluciones.index'))

    return render_template('devoluciones/edit.html', form=form, devolucion=devolucion)


@devoluciones_bp.route('/api/folios/<int:centro_id>')
@login_required
def folios_por_centro(centro_id):
    tipo_id = request.args.get('tipo', type=int)
    return jsonify(mov.folios_entregados_a(centro_id, tipo_id))


@devoluciones_bp.route('/plantilla')
@login_required
@permiso_requerido('devoluciones.importar')
def plantilla():
    tipo = TipoCertificado.query.filter_by(activo=True) \
        .order_by(TipoCertificado.name).first()
    centro = Centro.query.filter_by(activo=True).order_by(Centro.name).first()
    ejemplo = [1000, tipo.name if tipo else 'Tipo de certificado', 2026,
               date.today().strftime('%d/%m/%Y'),
               centro.name if centro else 'Nombre del centro',
               current_user.username]
    return import_excel.respuesta_plantilla(
        'plantilla_devoluciones.xlsx', HEADERS_FOLIOS, ejemplo)


@devoluciones_bp.route('/importar', methods=['GET', 'POST'])
@login_required
@permiso_requerido('devoluciones.importar')
def importar():

    form = ImportarDevolucionForm()

    if form.validate_on_submit():
        try:
            filas = import_excel.leer_filas(
                form.archivo.data, HEADERS_FOLIOS,
                import_excel.MAX_FOLIOS_POR_ARCHIVO)
        except import_excel.ImportExcelError as e:
            flash(str(e), 'danger')
            return render_template('devoluciones/importar.html', form=form)

        preview, payload = mov.resolver_folios_para_importar(
            filas, estado='entregado')
        total_validos = sum(1 for p in preview if p['error'] is None)
        if not total_validos:
            flash('Ningún folio del archivo es válido para devolución.', 'danger')
        centros_nombre = ', '.join(sorted(
            {p['centro'] for p in preview if p['error'] is None and p['centro']}))
        return render_template(
            'devoluciones/importar.html', form=form, preview=preview,
            payload_json=json.dumps(payload), total_validas=total_validos,
            max_mostrar=MAX_PREVIA_MOSTRAR,
            centros_nombre=centros_nombre,
        )
    return render_template('devoluciones/importar.html', form=form)


@devoluciones_bp.route('/importar/confirmar', methods=['POST'])
@login_required
@permiso_requerido('devoluciones.importar')
def importar_confirmar():

    items, error = import_excel.parsear_confirmacion(request.form.get('payload'))
    if error:
        flash(error, 'danger')
        return redirect(url_for('devoluciones.importar'))

    # El centro viene por fila en el payload (el hidden es editable):
    # revalida cada centro contra la DB antes de cualquier registro.
    cids = {cid for _, _, _, cid in items}
    centros = {c.id: c for c in Centro.query.filter(Centro.id.in_(cids)).all()}
    if any(cid not in centros or not centros[cid].activo for cid in cids):
        flash('Centro de salud inválido.', 'danger')
        return redirect(url_for('devoluciones.importar'))

    # Revalida contra la DB: solo los folios que el centro de su fila tenga
    # entregados siguen siendo elegibles; el resto se descarta (pudo cambiar
    # el estado desde la vista previa, y el hidden es editable). Duplicado en
    # el payload: gana la última fila.
    mapa = {}
    for fid, uid, fecha, cid in items:
        mapa[fid] = (uid, fecha, cid)
    ids_validos = mov.folios_devolubles(
        {fid: cid for fid, (uid, fecha, cid) in mapa.items()})
    if not ids_validos:
        flash('Ningún folio sigue entregado a su centro.', 'warning')
        return redirect(url_for('devoluciones.importar'))

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
                modelo=DevolucionFolio,
                fecha_field='fechaDevolucion',
                folio_ids=fids,
                fecha=fecha,
                centro_id=cid,
                user=usuario_activo(uid, current_user),
                actor=current_user,
                estado_origen='entregado',
                estado_destino='devuelto',
                excluir_nulos=False,
                tabla_audit='devolucion_folios',
                log_audit=log_audit,
            )
            count += parcial
            omitidos += omitidos_parcial
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash('Registro duplicado: el folio ya tiene una devolución registrada por otra '
              'operación. ' + REFRESQUE_INTENTE, 'danger')
        return redirect(url_for('devoluciones.index'))

    if omitidos:
        flash(
            f'{count} {plural(count, "devolución", "devoluciones")} {plural(count, "registrada")}; '
            f'{omitidos} {plural(omitidos, "folio")} {plural(omitidos, "omitido")} '
            'porque ya no estaban entregados. Refresque la lista.',
            'warning',
        )
    else:
        flash(
            f'{count} {plural(count, "devolución", "devoluciones")} '
            f'{plural(count, "registrada")} exitosamente.',
            'success',
        )
    return redirect(url_for('devoluciones.index'))
