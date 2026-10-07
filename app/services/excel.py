"""Helpers de exportación Excel."""


def neutralizar_formulas(wb):
    """Fuerza a texto cualquier celda que openpyxl haya escrito como fórmula.

    openpyxl interpreta strings que empiezan con '=' como fórmula: un nombre de
    usuario/tipo con ``=HYPERLINK(...)`` se ejecutaría al abrir el .xlsx.
    Llamar justo antes de ``wb.save()``.
    """
    for ws in wb.worksheets:
        for fila in ws.iter_rows():
            for celda in fila:
                if celda.data_type == 'f':
                    celda.data_type = 's'
