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

# Nombre estricto: 1-10 dígitos + .jpg/.jpeg. El destino en disco se reconstruye
# desde el número parseado, así que el filename del cliente nunca toca el
# filesystem (no hay path traversal posible). El tope de 10 dígitos es el de
# Folio.folio (Integer) y garantiza que int() nunca lance: una captura más larga
# (>4300 dígitos) haría crashear el lote por el límite int↔str de CPython.
NOMBRE_RE = re.compile(r'^(\d{1,10})\.(jpg|jpeg)$', re.IGNORECASE)

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


ANIO_DIR_RE = re.compile(r'^\d{4}$')


def validar_carpeta(user_id):
    """Reconcilia <SCANS_FOLDER> contra la DB: marca y desmarca `escaneado`.

    Recorre las subcarpetas de año (\\d{4}); cada `NOMBRE_RE` que matchee arma
    el conjunto de (año, número) en disco. Luego:
      - folios cuyo (anioCert, folio) está en disco y está sin marcar → True;
      - folios marcados cuyo par NO está en disco → False, solo si la
        subcarpeta de su año existe (año sin carpeta = volumen a medio montar:
        no se desmarca nada de ese año).
    Raíz ausente → error_raiz y cero cambios. Archivos con nombre inválido o
    sueltos en la raíz → ignorados (solo se reportan).
    Devuelve {'error_raiz', 'marcados', 'desmarcados', 'archivos',
    'ignorados', 'anios_sin_carpeta'}.
    """
    raiz = Path(current_app.config['SCANS_FOLDER'])
    reporte = {'error_raiz': False, 'marcados': 0, 'desmarcados': 0,
               'archivos': 0, 'ignorados': 0, 'anios_sin_carpeta': []}
    if not raiz.is_dir():
        reporte['error_raiz'] = True
        return reporte

    # Inventario en disco: (año, número) válidos, más ignorados.
    en_disco = set()
    anios_con_carpeta = set()
    for hijo in raiz.iterdir():
        if hijo.is_file():
            # Suelto en la raíz: no pertenece a ningún año.
            reporte['ignorados'] += 1
            continue
        if not ANIO_DIR_RE.match(hijo.name):
            continue
        anio = int(hijo.name)
        anios_con_carpeta.add(anio)
        for archivo in hijo.iterdir():
            if not archivo.is_file():
                continue
            match = NOMBRE_RE.match(archivo.name)
            if match:
                en_disco.add((anio, int(match.group(1))))
                reporte['archivos'] += 1
            else:
                reporte['ignorados'] += 1

    # Marcar: folios del año con su número en disco.
    por_anio = {}
    for anio, numero in en_disco:
        por_anio.setdefault(anio, set()).add(numero)
    for anio, numeros in por_anio.items():
        folios = Folio.query.filter(
            Folio.anioCert == anio, Folio.folio.in_(numeros)).all()
        for folio in folios:
            if not folio.escaneado:
                log_audit(user_id, 'UPDATE', 'folios', folio.id,
                          {'escaneado': False}, {'escaneado': True})
                folio.escaneado = True
                reporte['marcados'] += 1

    # Desmarcar: solo años cuya carpeta existe y sin archivo correspondiente.
    sin_carpeta = set()
    for folio in Folio.query.filter_by(escaneado=True).all():
        if folio.anioCert not in anios_con_carpeta:
            sin_carpeta.add(folio.anioCert)
            continue
        if (folio.anioCert, folio.folio) not in en_disco:
            log_audit(user_id, 'UPDATE', 'folios', folio.id,
                      {'escaneado': True}, {'escaneado': False})
            folio.escaneado = False
            reporte['desmarcados'] += 1

    reporte['anios_sin_carpeta'] = sorted(sin_carpeta)
    if reporte['marcados'] or reporte['desmarcados']:
        db.session.commit()
    return reporte
