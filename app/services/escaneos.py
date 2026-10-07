"""Guardado de JPG de folios escaneados y marcado en la DB.

Un fallo por archivo (nombre inválido, error de disco) no aborta el lote:
cada archivo se procesa de forma independiente y queda reportado.
"""

import re
from pathlib import Path

from flask import current_app

from app.extensions import db
from app.models.folio import Folio
from app.services.audit import log_audit

# Nombre estricto: solo dígitos + .jpg/.jpeg. El destino en disco se reconstruye
# desde el número parseado, así que el filename del cliente nunca toca el
# filesystem (no hay path traversal posible).
NOMBRE_RE = re.compile(r'^(\d+)\.(jpg|jpeg)$', re.IGNORECASE)

MARCADO = 'marcado'
SIN_COINCIDENCIA = 'sin_coincidencia'
NOMBRE_INVALIDO = 'nombre_invalido'
ERROR_GUARDAR = 'error_guardar'


def guardar_y_matchear(archivos, anio, user_id):
    """Guarda cada JPG en <SCANS_FOLDER>/<anio>/<numero>.jpg y marca los folios.

    `archivos`: lista de FileStorage (MultipleFileField).
    `anio`: año del selector del form (int) — manda sobre cualquier otra fecha.
    Devuelve el reporte:
      {'resultados': [{'nombre', 'numero', 'estado', 'folios'}],
       'marcados', 'sin_coincidencia', 'invalidos', 'errores'}
    """
    carpeta = Path(current_app.config['SCANS_FOLDER']) / str(anio)
    reporte = {'resultados': [], 'marcados': 0, 'sin_coincidencia': 0,
               'invalidos': 0, 'errores': 0}

    for archivo in archivos:
        nombre = archivo.filename or ''
        match = NOMBRE_RE.match(nombre)
        if not match:
            reporte['resultados'].append(
                {'nombre': nombre, 'numero': None, 'estado': NOMBRE_INVALIDO,
                 'folios': 0})
            reporte['invalidos'] += 1
            continue

        numero = int(match.group(1))
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
            archivo.save(carpeta / f'{numero}.jpg')
        except OSError:
            reporte['resultados'].append(
                {'nombre': nombre, 'numero': numero, 'estado': ERROR_GUARDAR,
                 'folios': 0})
            reporte['errores'] += 1
            continue

        folios = Folio.query.filter_by(anioCert=anio, folio=numero).all()
        for folio in folios:
            if not folio.escaneado:
                log_audit(user_id, 'UPDATE', 'folios', folio.id,
                          {'escaneado': False}, {'escaneado': True})
                folio.escaneado = True
        if folios:
            db.session.commit()
            estado = MARCADO
            reporte['marcados'] += 1
        else:
            estado = SIN_COINCIDENCIA
            reporte['sin_coincidencia'] += 1
        reporte['resultados'].append(
            {'nombre': nombre, 'numero': numero, 'estado': estado,
             'folios': len(folios)})

    return reporte
