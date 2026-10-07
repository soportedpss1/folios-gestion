"""Copia y restauración de todas las tablas de datos en JSON.

- Sin binarios externos: SQLAlchemy Core + stdlib json.
- Restauración transaccional: DELETE + INSERT por tabla en orden de
  dependencia; cualquier error revierte todo (la DB queda como estaba).
- `alembic_version` queda fuera: la gestiona Flask-Migrate.
- **Tolerancia al esquema**: el respaldo guarda `meta.esquema` (columnas de
  cada tabla al momento de copiar). Al restaurar se compara con el esquema
  actual: columnas nuevas se rellenan con su default (o NULL si son
  opcionales) y se bloquea si hay una obligatoria sin default; columnas
  eliminadas se ignoran. Solo los respaldos antiguos, sin `meta.esquema`,
  exigen que `meta.alembic` coincida con la versión actual.
- Se borran TODAS las tablas (no solo las del archivo) para no dejar filas
  huérfanas que violen las claves foráneas, y se rechazan respaldos que
  dejarían la aplicación sin usuarios.
"""

import base64
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Boolean, Integer, LargeBinary, delete, func, select, text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db

FORMATO = 1

# Orden de inserción: padres primero. Borrado = orden inverso (hijos primero),
# así no hace falta desactivar FOREIGN_KEY_CHECKS.
TABLAS_ORDEN = (
    'usuarios',
    'centros',
    'tipo_certificados',
    'recepcion_folios',
    'folios',
    'entrega_folios',
    'devolucion_folios',
    'audit_logs',
    'permiso_usuarios',
    'sync_config',
    'marca_config',
)


class ErrorRespaldo(ValueError):
    """Payload inválido (mensaje ya en español para flash)."""


def version_alembic():
    """Versión actual del esquema, o None si la tabla no existe (tests)."""
    try:
        with db.engine.connect() as conn:
            return conn.execute(text('SELECT version_num FROM alembic_version')).scalar()
    except Exception:
        return None


def esquema_actual():
    """{tabla: [columnas]} del metadata actual, en orden de definición."""
    return {
        nombre: list(db.metadata.tables[nombre].columns.keys())
        for nombre in TABLAS_ORDEN
    }


def _json_default(valor):
    """Serializa los tipos que json no conoce (aplica también anidados)."""
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, bytes):
        return base64.b64encode(valor).decode('ascii')
    if isinstance(valor, Decimal):
        return str(valor)
    raise TypeError(f'Tipo no serializable: {type(valor)!r}')


def crear_backup():
    """Dict {meta, datos} con todas las tablas. json.dumps con default=_json_default."""
    tablas = {}
    datos = {}
    for nombre in TABLAS_ORDEN:
        tabla = db.metadata.tables[nombre]
        filas = [dict(f) for f in db.session.execute(select(tabla)).mappings().all()]
        tablas[nombre] = len(filas)
        datos[nombre] = filas
    return {
        'meta': {
            'formato': FORMATO,
            'creado': datetime.now().isoformat(timespec='seconds'),
            'alembic': version_alembic(),
            'esquema': esquema_actual(),
            'tablas': tablas,
        },
        'datos': datos,
    }


def estadisticas():
    """{tabla: nº de filas actuales} + 'alembic' para el panel."""
    stats = {}
    for nombre in TABLAS_ORDEN:
        tabla = db.metadata.tables[nombre]
        stats[nombre] = db.session.execute(
            select(func.count()).select_from(tabla)).scalar()
    return stats


def _revive(columna, valor):
    """Convierte el valor JSON al tipo de la columna (type-directed)."""
    if valor is None:
        return None
    tipo = columna.type
    if isinstance(tipo, DateTime) and isinstance(valor, str):
        return datetime.fromisoformat(valor)
    if isinstance(tipo, Date) and isinstance(valor, str):
        return date.fromisoformat(valor)
    if isinstance(tipo, LargeBinary) and isinstance(valor, str):
        try:
            return base64.b64decode(valor)
        except Exception as exc:
            raise ErrorRespaldo(f'Imagen corrupta en {columna.name}.') from exc
    if isinstance(tipo, Boolean):
        return bool(valor)
    if isinstance(tipo, Integer) and not isinstance(valor, int):
        raise ErrorRespaldo(f'Entero inválido en columna {columna.name}.')
    return valor


def _rellenable(columna):
    """¿Puede la base rellenar esta columna si el respaldo no la trae?

    Si no (sin default, obligatoria) hay que bloquear el restore: si no,
    fallaría la base a mitad de la operación con un error críptico.
    """
    return (columna.default is not None
            or columna.server_default is not None
            or columna.nullable)


def _plan_columnas(nombre, escritor):
    """Compara las columnas que declara el respaldo con las del esquema actual.

    Las columnas que faltan NO se rellenan aquí: se dejan fuera del INSERT y
    SQLAlchemy / la DB aplican su default (o NULL si son opcionales).
    """
    columnas = db.metadata.tables[nombre].columns
    escritor = list(escritor or [])
    usadas = [c for c in escritor if c in columnas]
    plan = {
        'rellenar': [],      # actuales ausentes en el respaldo
        'ignoradas': [],     # del respaldo, ya no existen
        'bloqueantes': [],   # obligatorias sin default
    }
    for columna in escritor:
        if columna not in columnas:
            plan['ignoradas'].append(columna)
    for nombre_col in columnas.keys():
        if nombre_col in usadas:
            continue
        if _rellenable(columnas[nombre_col]):
            plan['rellenar'].append(nombre_col)
        else:
            plan['bloqueantes'].append(nombre_col)
    return plan


def _validar_estructura(datos):
    """Comprueba tablas y filas SIN tocar la DB. Lanza ErrorRespaldo."""
    for nombre, registros in datos.items():
        if nombre not in TABLAS_ORDEN:
            raise ErrorRespaldo(f'Tabla desconocida en el respaldo: {nombre}.')
        if not isinstance(registros, list):
            raise ErrorRespaldo(f'La tabla {nombre} debe ser una lista de filas.')
        for i, registro in enumerate(registros):
            if not isinstance(registro, dict):
                raise ErrorRespaldo(f'Fila inválida en {nombre} (posición {i + 1}).')


def _validar_usuarios(datos):
    """Un respaldo sin usuarios dejaría la aplicación sin cuenta de acceso."""
    if 'usuarios' not in datos:
        raise ErrorRespaldo(
            'El respaldo no incluye la tabla usuarios: restaurarlo dejaría la '
            'aplicación sin cuentas y no podría iniciar sesión.')
    if not datos['usuarios']:
        raise ErrorRespaldo(
            'El respaldo no incluye usuarios (la tabla usuarios está vacía): '
            'restaurarlo dejaría la aplicación sin cuentas y no podría '
            'iniciar sesión.')


def analizar_compatibilidad(datos, esquema_respaldo):
    """Diff entre el respaldo y el esquema actual. NO toca la DB.

    Devuelve {'ok', 'bloqueos', 'tablas': {tabla: {filas, rellenar,
    ignoradas, bloqueantes}}, 'vacias': [tablas ausentes en el respaldo]}.
    """
    if not isinstance(esquema_respaldo, dict):
        raise ErrorRespaldo('El respaldo no describe su esquema (meta.esquema).')
    _validar_estructura(datos)

    bloqueos = []
    try:
        _validar_usuarios(datos)
    except ErrorRespaldo as exc:
        bloqueos.append(str(exc))

    tablas = {}
    for nombre, registros in datos.items():
        plan = _plan_columnas(nombre, esquema_respaldo.get(nombre))
        if plan['bloqueantes']:
            bloqueos.append(
                f'{nombre}: la columna {", ".join(plan["bloqueantes"])} es '
                'obligatoria y no tiene valor por defecto.')
        tablas[nombre] = {
            'filas': len(registros),
            'rellenar': plan['rellenar'],
            'ignoradas': plan['ignoradas'],
            'bloqueantes': plan['bloqueantes'],
        }
    return {
        'ok': not bloqueos,
        'bloqueos': bloqueos,
        'tablas': tablas,
        'vacias': [n for n in TABLAS_ORDEN if n not in datos],
    }


def _preparar(datos, esquema_respaldo):
    """Valida y arma las filas a insertar. NO toca la DB.

    `esquema_respaldo` = meta['esquema'] del archivo, o None si es un respaldo
    antiguo (en ese caso las columnas se infieren de las propias filas).

    Devuelve (filas_a_insertar, analisis).
    """
    _validar_estructura(datos)
    escritor = esquema_respaldo if esquema_respaldo is not None else columnas_de_filas(datos)
    analisis = analizar_compatibilidad(datos, escritor)
    if not analisis['ok']:
        raise ErrorRespaldo(' '.join(analisis['bloqueos']))

    filas = {}
    for nombre, registros in datos.items():
        columnas = db.metadata.tables[nombre].columns
        preparadas = []
        for i, registro in enumerate(registros):
            fila = {}
            for clave, valor in registro.items():
                if clave not in columnas:
                    if esquema_respaldo is None:
                        raise ErrorRespaldo(
                            f'Columnas desconocidas en {nombre}: {clave}.')
                    continue  # columna eliminada del esquema: se ignora
                try:
                    fila[clave] = _revive(columnas[clave], valor)
                except ErrorRespaldo:
                    raise
                except Exception as exc:
                    raise ErrorRespaldo(
                        f'Valor inválido en {nombre} (posición {i + 1}).') from exc
            preparadas.append(fila)
        filas[nombre] = preparadas
    return filas, analisis


def columnas_de_filas(datos):
    """{tabla: [columnas observadas en las filas]} — respaldos sin meta.esquema."""
    return {
        nombre: sorted({clave for fila in registros for clave in fila})
        for nombre, registros in datos.items()
    }


def _extraer(payload):
    """(meta, datos) validando el formato del archivo. Lanza ErrorRespaldo."""
    if not isinstance(payload, dict):
        raise ErrorRespaldo('El archivo no es un respaldo válido.')
    meta = payload.get('meta')
    if not isinstance(meta, dict) or meta.get('formato') != FORMATO:
        raise ErrorRespaldo(
            f'Formato de respaldo desconocido (se espera formato {FORMATO}).')
    datos = payload.get('datos')
    if not isinstance(datos, dict) or not datos:
        raise ErrorRespaldo('El respaldo no contiene datos por tabla.')
    return meta, datos


def _exigir_misma_version(meta):
    """Respaldo antiguo (sin meta.esquema): solo si el esquema no cambió."""
    actual = version_alembic()
    if meta.get('alembic') != actual:
        raise ErrorRespaldo(
            'El respaldo es de otra versión del esquema '
            f'(respaldo: {meta.get("alembic")!r}, actual: {actual!r}). '
            'Restaure con la versión de la aplicación que creó la copia.')


def previsualizar(payload):
    """Valida el respaldo completo y devuelve el análisis. NO toca la DB.

    Lanza ErrorRespaldo con el mismo criterio que restaurar_backup.
    """
    meta, datos = _extraer(payload)
    esquema_respaldo = meta.get('esquema')
    if esquema_respaldo is None:
        _exigir_misma_version(meta)
    _, analisis = _preparar(datos, esquema_respaldo)
    return analisis


def restaurar_backup(payload):
    """Valida y reemplaza las tablas. Devuelve {tabla: filas insertadas}.

    Lanza ErrorRespaldo si el payload no es válido (la DB no se toca) o
    SQLAlchemyError si falla la DB (todo queda como estaba, por rollback).
    """
    meta, datos = _extraer(payload)

    esquema_respaldo = meta.get('esquema')
    if esquema_respaldo is None:
        # Respaldo antiguo (sin esquema declarado): no se pueden predecir las
        # diferencias de columnas, así que exige la misma versión de esquema.
        _exigir_misma_version(meta)

    filas, _ = _preparar(datos, esquema_respaldo)

    try:
        # Se vacían TODAS las tablas, no solo las del archivo: una tabla
        # ausente quedaría con filas viejas apuntando a claves foráneas
        # que ya no existen. Borrado en orden inverso (hijos primero).
        for nombre in reversed(TABLAS_ORDEN):
            db.session.execute(delete(db.metadata.tables[nombre]))
        insertadas = {}
        for nombre in TABLAS_ORDEN:
            registros = filas.get(nombre)
            if registros is None:
                continue
            if registros:
                db.session.execute(db.metadata.tables[nombre].insert(), registros)
            insertadas[nombre] = len(registros)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise
    return insertadas
