"""Sincronización de la tabla folios hacia Google Sheets (cuenta de servicio).

Estrategia: upsert por fila con key = folio.id —
  1. actualizaciones (solo celdas que difieren, preserva formato manual),
  2. eliminación de filas huérfanas (key en el sheet y no en la DB),
  3. append de filas nuevas.
value_input_option='RAW' en todas las escrituras: un valor '=...' se guarda
como texto y nunca se evalúa como fórmula (equivalente a neutralizar_formulas).
"""

import logging
import os

from sqlalchemy import text as sa_text
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.entrega_folio import EntregaFolio
from app.models.folio import Folio
from app.models.devolucion_folio import DevolucionFolio

logger = logging.getLogger(__name__)

ENCABEZADOS = [
    'ID', 'Folio', 'Tipo Certificado', 'Año', 'Centro', 'Estado',
    'Digitado', 'Escaneado', 'Nulo',
    'Fecha Entrega', 'Entregado por', 'Fecha Devolución', 'Recibido Por',
]

LOCK_NAME = 'gsheet_sync'


class ErrorSincronizacion(Exception):
    """Error de sync con mensaje apto para el usuario (ya en español)."""


def _config(app_config):
    if app_config is None:
        from flask import current_app
        app_config = current_app.config
    return (
        app_config.get('GOOGLE_SERVICE_ACCOUNT_JSON', ''),
        app_config.get('GOOGLE_SHEET_ID', ''),
        app_config.get('GOOGLE_SHEET_WORKSHEET', 'folios'),
    )


def get_client(app_config=None):
    """Cliente gspread autenticado con la cuenta de servicio."""
    ruta, _, _ = _config(app_config)
    if not ruta:
        raise ErrorSincronizacion(
            'Falta la credencial de Google: configure GOOGLE_SERVICE_ACCOUNT_JSON.')
    if not os.path.isfile(ruta):
        raise ErrorSincronizacion(
            'No existe el archivo de credenciales de Google en la ruta configurada.')
    try:
        import gspread
        return gspread.service_account(filename=ruta)
    except ErrorSincronizacion:
        raise
    except Exception as exc:
        logger.exception('No se pudo autenticar con Google Sheets')
        raise ErrorSincronizacion(
            'No se pudo autenticar con Google Sheets. Verifique el archivo de credenciales.') from exc


def _eager(query):
    return query.options(
        selectinload(Folio.tipo_cert),
        selectinload(Folio.entrega).selectinload(EntregaFolio.centro),
        selectinload(Folio.entrega).selectinload(EntregaFolio.usuario),
        selectinload(Folio.devolucion).selectinload(DevolucionFolio.centro),
        selectinload(Folio.devolucion).selectinload(DevolucionFolio.usuario),
    )


def fila_folio(f):
    """Fila de 13 columnas: id + los mismos 12 campos/formato del Excel de reportes."""
    entrega = f.entrega
    devolucion = f.devolucion
    return [
        str(f.id),
        str(f.folio),
        f.tipo_cert.name if f.tipo_cert else '',
        str(f.anioCert),
        entrega.centro.name if entrega and entrega.centro else '',
        f.estado,
        'Sí' if f.digitado else 'No',
        'Sí' if f.escaneado else 'No',
        'Sí' if f.nulo else 'No',
        entrega.fechaEntrega.strftime('%d/%m/%Y') if entrega and entrega.fechaEntrega else '-',
        entrega.usuario.username if entrega and entrega.usuario else '-',
        devolucion.fechaDevolucion.strftime('%d/%m/%Y') if devolucion and devolucion.fechaDevolucion else '-',
        devolucion.usuario.username if devolucion and devolucion.usuario else '-',
    ]


def _adquirir_lock():
    """GET_LOCK de MySQL serializa manual vs worker. Otras dialectos (SQLite en
    tests) no tienen el concepto: se salta."""
    if db.engine.dialect.name != 'mysql':
        return True
    fila = db.session.execute(
        sa_text('SELECT GET_LOCK(:nombre, 0)'), {'nombre': LOCK_NAME}
    ).scalar()
    return fila == 1


def _liberar_lock():
    if db.engine.dialect.name != 'mysql':
        return
    db.session.execute(sa_text('SELECT RELEASE_LOCK(:nombre)'), {'nombre': LOCK_NAME})


def _worksheet(gc):
    import gspread
    _, sheet_id, nombre = _config(None)
    if not sheet_id:
        raise ErrorSincronizacion('Falta la hoja de cálculo: configure GOOGLE_SHEET_ID.')
    try:
        sh = gc.open_by_key(sheet_id)
    except Exception as exc:
        logger.exception('No se pudo abrir la hoja %s', sheet_id)
        raise ErrorSincronizacion(
            'No se pudo abrir la hoja. Verifique GOOGLE_SHEET_ID y que la hoja '
            'esté compartida con la cuenta de servicio como editor.') from exc
    try:
        return sh.worksheet(nombre)
    except gspread.WorksheetNotFound:
        return sh.add_worksheet(title=nombre, rows=1000, cols=len(ENCABEZADOS))


def _fila_vacia(row):
    return not row or not any(str(c).strip() for c in row)


def sincronizar(app_config=None):
    """Upsert completo. Devuelve {'agregadas': n, 'actualizadas': n,
    'eliminadas': n, 'total': n}. Lanza ErrorSincronizacion con mensaje en español."""
    if not _adquirir_lock():
        raise ErrorSincronizacion('Sincronización ya en curso.')

    try:
        gc = get_client(app_config)
        ws = _worksheet(gc)

        valores = ws.get_all_values()
        if not valores:
            ws.update([ENCABEZADOS], 'A1', value_input_option='RAW')
            valores = [ENCABEZADOS]
        elif valores[0] != ENCABEZADOS:
            ws.update([ENCABEZADOS], 'A1', value_input_option='RAW')

        folios = _eager(Folio.query).order_by(Folio.folio, Folio.id).all()
        deseadas = [fila_folio(f) for f in folios]
        por_id_db = {row[0]: row for row in deseadas}

        # filas existentes: índice 1-based (row 1 = header) -> values
        existentes = {}
        for i, row in enumerate(valores[1:], start=2):
            if _fila_vacia(row):
                continue
            existentes[str(row[0])] = (i, row)

        # 1) actualizaciones: solo filas que difieren (posiciones actuales)
        actualizaciones = []
        for key, (indice, row) in existentes.items():
            deseada = por_id_db.get(key)
            if deseada is None:
                continue
            normalizada = list(row) + [''] * (len(ENCABEZADOS) - len(row))
            if normalizada[:len(ENCABEZADOS)] != deseada:
                rango = f'A{indice}:M{indice}'
                actualizaciones.append({'range': rango, 'values': [deseada]})
        if actualizaciones:
            ws.batch_update(actualizaciones, value_input_option='RAW')

        # 2) huérfanas (key en sheet, no en DB): tramos contiguos, ejecutados
        # bottom-up para que borrar filas altas no desplace las bajas.
        indices_huerfanas = sorted(
            i for key, (i, _) in existentes.items() if key not in por_id_db
        )
        tramos = []
        for i in indices_huerfanas:
            if tramos and i == tramos[-1][-1] + 1:
                tramos[-1].append(i)
            else:
                tramos.append([i])
        eliminadas = 0
        for tramo in reversed(tramos):
            ws.delete_rows(tramo[0], tramo[-1])   # delete_rows(start, end) inclusivo
            eliminadas += len(tramo)

        # 3) nuevas: al final (el sheet puede reordenarse a mano; la DB manda el set)
        nuevas = [row for key, row in por_id_db.items() if key not in existentes]
        if nuevas:
            ws.append_rows(nuevas, value_input_option='RAW')

        counts = {
            'agregadas': len(nuevas),
            'actualizadas': len(actualizaciones),
            'eliminadas': eliminadas,
            'total': len(deseadas),
        }
        logger.info('Sync Google Sheets: %s', counts)
        return counts
    finally:
        _liberar_lock()
