from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required
from app.extensions import db
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from app.models.folio import Folio
from app.models.entrega_folio import EntregaFolio
from app.models.devolucion_folio import DevolucionFolio
from app.models.tipo_certificado import TipoCertificado
from app.services.kpis import conteos_folios
from datetime import datetime

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')


def _kpis_del_anio(year):
    """Los 7 KPIs del año, vía el servicio compartido con reportes."""
    return conteos_folios(Folio.query.filter(Folio.anioCert == year))


@dashboard_bp.route('/')
@login_required
def index():
    year = datetime.now().year

    kpis = _kpis_del_anio(year)
    (total_folios, digitados, escaneados, nulos,
     disponibles, entregados, devueltos) = (
        kpis['total'], kpis['digitados'], kpis['escaneados'], kpis['nulos'],
        kpis['disponibles'], kpis['entregados'], kpis['devueltos'])

    # La plantilla recorre folio.folio y folio.entrega.centro por fila
    entregas_recientes = EntregaFolio.query.options(
        selectinload(EntregaFolio.folio).selectinload(Folio.entrega)
            .selectinload(EntregaFolio.centro),
        selectinload(EntregaFolio.folio).selectinload(Folio.tipo_cert),
        selectinload(EntregaFolio.centro),
        selectinload(EntregaFolio.usuario),
    ).order_by(EntregaFolio.created_at.desc()).limit(5).all()

    devoluciones_recientes = DevolucionFolio.query.options(
        selectinload(DevolucionFolio.folio).selectinload(Folio.tipo_cert),
        selectinload(DevolucionFolio.centro),
        selectinload(DevolucionFolio.usuario),
    ).order_by(DevolucionFolio.created_at.desc()).limit(5).all()

    return render_template('dashboard/index.html',
        total_folios=total_folios,
        digitados=digitados,
        escaneados=escaneados,
        nulos=nulos,
        disponibles=disponibles,
        entregados=entregados,
        devueltos=devueltos,
        entregas_recientes=entregas_recientes,
        devoluciones_recientes=devoluciones_recientes,
        year=year,
    )


@dashboard_bp.route('/api/tendencia')
@login_required
def tendencia():
    """Entregas y devoluciones por mes de un año (para el gráfico del dashboard)."""
    raw = request.args.get('anio')
    if raw is None:
        anio = datetime.now().year
    else:
        try:
            anio = int(raw)
        except (TypeError, ValueError):
            return jsonify(error='El año solicitado no es válido.'), 400
    if anio < 2000 or anio > datetime.now().year + 1:
        return jsonify(error='El año solicitado no es válido.'), 400

    def _conteos(modelo, columna):
        mes = func.extract('month', columna)
        filas = db.session.query(
            mes, func.count(modelo.id)
        ).filter(func.extract('year', columna) == anio).group_by(mes).all()
        serie = [0] * 12
        for m, n in filas:
            serie[int(m) - 1] = int(n)
        return serie

    return jsonify(
        anio=anio,
        etiquetas=['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
                   'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'],
        entregas=_conteos(EntregaFolio, EntregaFolio.fechaEntrega),
        devoluciones=_conteos(DevolucionFolio, DevolucionFolio.fechaDevolucion),
    )


@dashboard_bp.route('/api/disponibles_por_tipo')
@login_required
def disponibles_por_tipo():
    year = datetime.now().year
    result = db.session.query(
        TipoCertificado.name,
        TipoCertificado.color,
        func.count(Folio.id)
    ).join(Folio, Folio.tipoCert_id == TipoCertificado.id).filter(
        Folio.anioCert == year,
        Folio.estado == 'disponible',
        Folio.nulo == False
    ).group_by(TipoCertificado.name, TipoCertificado.color).all()

    tipos = [{'nombre': nombre, 'color': color or '#6c757d', 'cantidad': cantidad} for nombre, color, cantidad in result]
    return jsonify(tipos=tipos)


@dashboard_bp.route('/api/folios_por_tipo')
@login_required
def folios_por_tipo():
    year = datetime.now().year
    filtro = request.args.get('filter', 'total')

    query = db.session.query(
        TipoCertificado.name,
        TipoCertificado.color,
        func.count(Folio.id)
    ).join(Folio, Folio.tipoCert_id == TipoCertificado.id).filter(
        Folio.anioCert == year
    )

    filtros = {
        'digitado': (Folio.digitado == True,),
        'escaneado': (Folio.escaneado == True,),
        'nulo': (Folio.nulo == True,),
        'disponible': (Folio.estado == 'disponible', Folio.nulo == False),
        'entregado': (Folio.estado == 'entregado', Folio.nulo == False),
        'devuelto': (Folio.estado == 'devuelto', Folio.nulo == False),
    }
    if filtro != 'total':
        if filtro not in filtros:
            return jsonify(error='El filtro solicitado no es válido.'), 400
        query = query.filter(*filtros[filtro])

    result = query.group_by(TipoCertificado.name, TipoCertificado.color).all()

    tipos = [{'nombre': nombre, 'color': color or '#6c757d', 'cantidad': cantidad} for nombre, color, cantidad in result]
    return jsonify(tipos=tipos)
