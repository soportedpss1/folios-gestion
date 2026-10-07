from flask import Blueprint, render_template, request, make_response, jsonify
from flask_login import login_required
from app.models.folio import Folio
from app.models.entrega_folio import EntregaFolio
from app.models.devolucion_folio import DevolucionFolio
from app.models.tipo_certificado import TipoCertificado
from app.models.centro import Centro
from sqlalchemy.orm import selectinload
from app.services.excel import neutralizar_formulas
from app.services.kpis import conteos_folios
from app.services.pdf import encabezado_pdf
from markupsafe import escape
from datetime import datetime
from io import BytesIO

reportes_bp = Blueprint('reportes', __name__, url_prefix='/reportes')


def _build_query(anio=None, tipo_id=None, centro_id=None, estado=None):
    query = Folio.query

    if anio:
        query = query.filter(Folio.anioCert == anio)

    if tipo_id:
        query = query.filter(Folio.tipoCert_id == tipo_id)

    if centro_id:
        query = query.join(EntregaFolio, Folio.entrega).filter(EntregaFolio.centroId == centro_id)

    if estado:
        if estado == 'nulo':
            query = query.filter(Folio.nulo == True)
        else:
            query = query.filter(Folio.estado == estado, Folio.nulo == False)

    return query


def _get_stats(anio=None, tipo_id=None, centro_id=None, estado=None):
    """Misma base que la tabla: si el filtro cambia, las tarjetas cambian."""
    return conteos_folios(_build_query(anio, tipo_id, centro_id, estado))


def _add_eager_loading(query):
    return query.options(
        selectinload(Folio.tipo_cert),
        selectinload(Folio.entrega)
            .selectinload(EntregaFolio.centro),
        selectinload(Folio.entrega)
            .selectinload(EntregaFolio.usuario),
        selectinload(Folio.devolucion)
            .selectinload(DevolucionFolio.centro),
        selectinload(Folio.devolucion)
            .selectinload(DevolucionFolio.usuario),
    )


@reportes_bp.route('/')
@login_required
def index():
    tipos = TipoCertificado.query.filter_by(activo=True).order_by(TipoCertificado.name).all()
    centros = Centro.query.filter_by(activo=True).order_by(Centro.name).all()

    return render_template('reportes/index.html',
        folios=[],
        tipos=tipos,
        centros=centros,
        current_anio=datetime.now().year,
        current_tipo=None,
        current_centro=None,
        current_estado=None
    )


@reportes_bp.route('/api/data')
@login_required
def api_data():
    anio = request.args.get('anioCert', type=int)
    tipo_id = request.args.get('tipoCert', type=int)
    centro_id = request.args.get('centroId', type=int)
    estado = request.args.get('estado')
    page = request.args.get('page', 1, type=int)
    per_page = min(max(request.args.get('per_page', 50, type=int), 1), 200)

    query = _build_query(anio, tipo_id, centro_id, estado)
    stats = _get_stats(anio, tipo_id, centro_id, estado)

    query = _add_eager_loading(query)
    pagination = query.order_by(Folio.folio, Folio.id).paginate(page=page, per_page=per_page, error_out=False)

    folios_data = []
    for f in pagination.items:
        folios_data.append({
            'folio': f.folio,
            'tipo_nombre': f.tipo_cert.name if f.tipo_cert else '',
            'tipo_color': f.tipo_cert.color if f.tipo_cert else '#0D6EFD',
            'anioCert': f.anioCert,
            'centro': f.entrega.centro.name if f.entrega and f.entrega.centro else None,
            'estado': f.estado,
            'digitado': f.digitado,
            'escaneado': f.escaneado,
            'nulo': f.nulo,
            'fechaEntrega': f.entrega.fechaEntrega.strftime('%d/%m/%Y') if f.entrega and f.entrega.fechaEntrega else None,
            'entregado_por': f.entrega.usuario.username if f.entrega and f.entrega.usuario else None,
            'fechaDevolucion': f.devolucion.fechaDevolucion.strftime('%d/%m/%Y') if f.devolucion and f.devolucion.fechaDevolucion else None,
            'recibido_por': f.devolucion.usuario.username if f.devolucion and f.devolucion.usuario else None,
        })

    return jsonify({
        'folios': folios_data,
        'stats': stats,
        'pagination': {
            'page': pagination.page,
            'pages': pagination.pages,
            'total': pagination.total,
            'has_next': pagination.has_next,
            'has_prev': pagination.has_prev,
            'next_num': pagination.next_num,
            'prev_num': pagination.prev_num,
        }
    })


@reportes_bp.route('/export/excel')
@login_required
def export_excel():
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill

    anio = request.args.get('anioCert', type=int)
    tipo_id = request.args.get('tipoCert', type=int)
    centro_id = request.args.get('centroId', type=int)
    estado = request.args.get('estado')

    query = _build_query(anio, tipo_id, centro_id, estado)
    query = _add_eager_loading(query)
    folios = query.order_by(Folio.folio, Folio.id).all()

    wb = Workbook()
    ws = wb.active
    ws.title = f'Folios {anio or "Todos"}'

    headers = [
        'Folio', 'Tipo Certificado', 'Año', 'Centro', 'Estado',
        'Digitado', 'Escaneado', 'Nulo',
        'Fecha Entrega', 'Entregado por',
        'Fecha Devolución', 'Recibido Por'
    ]

    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='0D6EFD', end_color='0D6EFD', fill_type='solid')
    header_align = Alignment(horizontal='center')

    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align

    for row, f in enumerate(folios, 2):
        ws.cell(row=row, column=1, value=f.folio)
        ws.cell(row=row, column=2, value=f.tipo_cert.name if f.tipo_cert else '')
        ws.cell(row=row, column=3, value=f.anioCert)
        ws.cell(row=row, column=4, value=f.entrega.centro.name if f.entrega and f.entrega.centro else '')
        ws.cell(row=row, column=5, value=f.estado)
        ws.cell(row=row, column=6, value='Sí' if f.digitado else 'No')
        ws.cell(row=row, column=7, value='Sí' if f.escaneado else 'No')
        ws.cell(row=row, column=8, value='Sí' if f.nulo else 'No')

        if f.entrega:
            ws.cell(row=row, column=9, value=f.entrega.fechaEntrega.strftime('%d/%m/%Y') if f.entrega.fechaEntrega else '')
            ws.cell(row=row, column=10, value=f.entrega.usuario.username if f.entrega.usuario else '')
        else:
            ws.cell(row=row, column=9, value='-')
            ws.cell(row=row, column=10, value='-')

        if f.devolucion:
            ws.cell(row=row, column=11, value=f.devolucion.fechaDevolucion.strftime('%d/%m/%Y') if f.devolucion.fechaDevolucion else '')
            ws.cell(row=row, column=12, value=f.devolucion.usuario.username if f.devolucion.usuario else '')
        else:
            ws.cell(row=row, column=11, value='-')
            ws.cell(row=row, column=12, value='-')

    for col in ws.columns:
        max_length = max(len(str(cell.value or '')) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = max_length + 2

    output = BytesIO()
    neutralizar_formulas(wb)  # nunca escribir '=...' como fórmula (inyección al abrir)
    wb.save(output)
    output.seek(0)

    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    response.headers['Content-Disposition'] = f'attachment; filename=folios_{anio or "todos"}.xlsx'
    return response


@reportes_bp.route('/export/pdf')
@login_required
def export_pdf():
    from weasyprint import HTML

    anio = request.args.get('anioCert', type=int)
    tipo_id = request.args.get('tipoCert', type=int)
    centro_id = request.args.get('centroId', type=int)
    estado = request.args.get('estado')

    query = _build_query(anio, tipo_id, centro_id, estado)
    query = _add_eager_loading(query)
    folios = query.order_by(Folio.folio, Folio.id).all()

    encabezado = encabezado_pdf(f'Reporte de Folios - Ano {anio or "Todos"}')
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            @page {{ size: landscape; margin: 1.5cm; }}
            body {{ font-family: Arial, sans-serif; margin: 20px; font-size: 10px; }}
            h1 {{ color: #0d6efd; text-align: center; font-size: 16px; }}
            h2 {{ color: #333; text-align: center; font-size: 13px; margin-top: 5px; }}
            h3 {{ color: #666; text-align: center; font-size: 11px; margin-top: 5px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 9px; }}
            th, td {{ border: 1px solid #ddd; padding: 5px 6px; text-align: left; }}
            th {{ background-color: #0d6efd; color: white; font-size: 9px; }}
            tr:nth-child(even) {{ background-color: #f2f2f2; }}
            .header {{ text-align: center; margin-bottom: 20px; }}
            .date {{ color: #666; font-size: 10px; text-align: right; margin-bottom: 10px; }}
        </style>
    </head>
    <body>
        {encabezado}
        <p class="date">Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
        <table>
            <thead>
                <tr>
                    <th>Folio</th>
                    <th>Tipo Certificado</th>
                    <th>Estado</th>
                    <th>Centro</th>
                    <th>Digitado</th>
                    <th>Escaneado</th>
                    <th>Nulo</th>
                    <th>Fecha Entrega</th>
                    <th>Entregado por</th>
                    <th>Fecha Devolucion</th>
                    <th>Recibido Por</th>
                </tr>
            </thead>
            <tbody>
    """

    filas = []
    for f in folios:
        fecha_entrega = f.entrega.fechaEntrega.strftime('%d/%m/%Y') if f.entrega and f.entrega.fechaEntrega else '-'
        usuario_entrega = f.entrega.usuario.username if f.entrega and f.entrega.usuario else '-'
        centro = f.entrega.centro.name if f.entrega and f.entrega.centro else '-'
        fecha_devolucion = f.devolucion.fechaDevolucion.strftime('%d/%m/%Y') if f.devolucion and f.devolucion.fechaDevolucion else '-'
        usuario_devolucion = f.devolucion.usuario.username if f.devolucion and f.devolucion.usuario else '-'

        filas.append(f"""
                <tr>
                    <td>{f.folio}</td>
                    <td>{escape(f.tipo_cert.name) if f.tipo_cert else ''}</td>
                    <td>{escape(f.estado)}</td>
                    <td>{escape(centro)}</td>
                    <td>{'Si' if f.digitado else 'No'}</td>
                    <td>{'Si' if f.escaneado else 'No'}</td>
                    <td>{'Si' if f.nulo else 'No'}</td>
                    <td>{fecha_entrega}</td>
                    <td>{escape(usuario_entrega)}</td>
                    <td>{fecha_devolucion}</td>
                    <td>{escape(usuario_devolucion)}</td>
                </tr>
        """)

    html_content += ''.join(filas)
    html_content += """
            </tbody>
        </table>
    </body>
    </html>
    """

    pdf = HTML(string=html_content).write_pdf()

    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=folios_{anio or "todos"}.pdf'
    return response
