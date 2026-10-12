"""Límites de lectura de .xlsx (zip bomb: MAX_CONTENT_LENGTH acota el
archivo comprimido, no el XML descomprimido que openpyxl carga en RAM)."""

from io import BytesIO
from types import SimpleNamespace

import pytest
from openpyxl import Workbook

from app.services import import_excel


def _xlsx_basico():
    wb = Workbook()
    ws = wb.active
    ws.append(['fecha', 'anioCert'])
    ws.append(['2026-01-01', 2026])
    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio


def test_xlsx_bomba_descompresion_rechazada(app, monkeypatch):
    monkeypatch.setattr(import_excel, 'MAX_XLSX_DECOMPRESION', 100)
    fs = SimpleNamespace(stream=_xlsx_basico())
    with pytest.raises(import_excel.ImportExcelError) as exc:
        import_excel.leer_filas(fs, ['fecha', 'anioCert'], max_filas=10)
    assert 'descomprim' in str(exc.value), \
        f'el error debe ser por descompresión, no: {exc.value}'
