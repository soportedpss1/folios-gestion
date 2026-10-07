"""Lectura de plantillas .xlsx para importación masiva.

Recepción, entregas y devoluciones leen el mismo tipo de archivo: una hoja con
encabezados fijos en la fila 1 y una fila de datos por registro. Aquí vive lo
genérico —lectura, coerción de celdas, parseo del confirm y descarga de
plantilla—; la validación de negocio queda en cada blueprint.
"""

import json
from datetime import date, datetime
from io import BytesIO

from flask import make_response
from openpyxl import Workbook, load_workbook

from app.services.excel import neutralizar_formulas

# Tope de filas por archivo de folios (entregas/devoluciones). El de rangos de
# recepción lo define su blueprint porque allí cada fila es un rango completo.
MAX_FOLIOS_POR_ARCHIVO = 5000

# Columna final opcional de las plantillas: username del dueño de la fila.
# Los archivos antiguos sin ella se siguen aceptando (fila = usuario actual).
COLUMNA_USUARIO = 'usuario'


class ImportExcelError(Exception):
    """Archivo ilegible o con formato incorrecto. El mensaje ya está en español."""


def leer_filas(file_storage, headers, max_filas, opcionales=()):
    """Devuelve las filas de datos como dicts con llave = encabezado.

    `headers` es la lista completa (en orden) que debe tener la fila 1;
    `opcionales` lista los encabezados finales que pueden faltar (p.ej.
    `usuario` en los archivos antiguos). Lanza ImportExcelError si los
    encabezados no coinciden, si la hoja no tiene datos o si supera `max_filas`
    filas. Las filas totalmente vacías se ignoran.
    """
    try:
        wb = load_workbook(file_storage.stream, read_only=True, data_only=True)
    except Exception:
        raise ImportExcelError('El archivo no es un Excel válido (.xlsx).')

    try:
        ws = wb.active
        esperados = [h.strip().lower() for h in headers]
        requeridos = esperados[:len(esperados) - len(opcionales)]
        filas = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0:
                actual = [('' if c is None else str(c).strip().lower()) for c in row]
                while actual and actual[-1] == '':
                    actual.pop()
                if actual not in (esperados, requeridos):
                    msg = (
                        'Encabezados incorrectos. Se esperaba exactamente: '
                        + ', '.join(headers)
                    )
                    if opcionales:
                        msg += f' (la columna {", ".join(opcionales)} puede omitirse)'
                    raise ImportExcelError(msg + '.')
                continue
            if all(c is None or str(c).strip() == '' for c in row):
                continue
            if len(filas) >= max_filas:
                raise ImportExcelError(
                    f'El archivo supera el máximo de {max_filas} filas.'
                )
            filas.append({h: v for h, v in zip(headers, row)})
    finally:
        wb.close()

    if not filas:
        raise ImportExcelError('El archivo no tiene filas de datos.')
    return filas


def a_entero(valor):
    """Celda → entero, o None si no representa un número entero."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float):
        return int(valor) if valor.is_integer() else None
    try:
        return int(str(valor).strip())
    except ValueError:
        return None


def a_fecha(valor):
    """Celda → date (datetime, date, 'dd/mm/aaaa' o 'aaaa-mm-dd'), o None."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if valor is None:
        return None
    texto = str(valor).strip()
    for formato in ('%d/%m/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def parsear_confirmacion(payload_raw, centro_raw, fecha_raw):
    """Hidden inputs del confirm → (items, centro_id, fecha, error).

    `items` es una lista de (folio_id, usuario_id|None): el payload de
    entregas/devoluciones lleva el responsable por folio (atribución mixta
    por fila). También se acepta la forma antigua de enteros sueltos
    (usuario_id = None → usuario actual en el llamador). Aquí se sanea porque
    el hidden es editable; el estado de cada folio se reconsulta después, en
    el llamador.
    """
    try:
        datos = json.loads(payload_raw or '')
    except (TypeError, ValueError):
        return None, None, None, 'Datos de importación inválidos. Repita la operación.'
    if not isinstance(datos, list) or not datos \
            or len(datos) > MAX_FOLIOS_POR_ARCHIVO:
        return None, None, None, 'Datos de importación inválidos. Repita la operación.'

    items = []
    for dato in datos:
        if isinstance(dato, dict):
            fid, uid = dato.get('id'), dato.get('usuarioId')
        elif isinstance(dato, int) and not isinstance(dato, bool):
            fid, uid = dato, None
        else:
            return None, None, None, 'Datos de importación inválidos. Repita la operación.'
        if not isinstance(fid, int) or isinstance(fid, bool) or fid <= 0:
            return None, None, None, 'Datos de importación inválidos. Repita la operación.'
        if uid is not None and (not isinstance(uid, int) or isinstance(uid, bool)
                                 or uid <= 0):
            return None, None, None, 'Datos de importación inválidos. Repita la operación.'
        items.append((fid, uid))

    centro_id = a_entero(centro_raw)
    fecha = a_fecha(fecha_raw)
    if centro_id is None or fecha is None:
        return None, None, None, 'Indique un centro de salud y una fecha válidos.'
    return items, centro_id, fecha, None


def respuesta_plantilla(nombre_archivo, headers, fila_ejemplo):
    """Response .xlsx con encabezados formateados + fila de ejemplo."""
    wb = Workbook()
    ws = wb.active
    ws.title = 'Plantilla'

    from openpyxl.styles import Alignment, Font, PatternFill
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='0D6EFD', end_color='0D6EFD', fill_type='solid')
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')
    for col, valor in enumerate(fila_ejemplo, 1):
        ws.cell(row=2, column=col, value=valor)
    for col in ws.columns:
        max_len = max(len(str(c.value or '')) for c in col)
        ws.column_dimensions[col[0].column_letter].width = max_len + 2

    output = BytesIO()
    neutralizar_formulas(wb)
    wb.save(output)
    output.seek(0)

    response = make_response(output.getvalue())
    response.headers['Content-Type'] = (
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response.headers['Content-Disposition'] = f'attachment; filename={nombre_archivo}'
    return response
