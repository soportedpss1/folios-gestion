"""Registro de auditoría y su presentación en /auditoria/.

`log_audit` escribe los hechos; `describir_logs` los traduce para la tabla:
etiqueta legible del registro afectado (JSON guardado → DB en lote →
fallback por tabla) y resumen de campos cambiados.
"""

import json
import re

from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.centro import Centro
from app.models.devolucion_folio import DevolucionFolio
from app.models.entrega_folio import EntregaFolio
from app.models.folio import Folio
from app.models.folio_comentario import FolioComentario
from app.models.marca import MarcaConfig
from app.models.recepcion_folio import RecepcionFolio
from app.models.tipo_certificado import TipoCertificado
from app.models.transferencia_folio import TransferenciaFolio
from app.models.usuario import Usuario


def log_audit(user_id, accion, tabla, registro_id, datos_anteriores=None, datos_nuevos=None):
    from flask import request
    log = AuditLog(
        user_id=user_id,
        accion=accion,
        tabla=tabla,
        registro_id=registro_id,
        datos_anteriores=datos_anteriores,
        datos_nuevos=datos_nuevos,
        ip_address=request.remote_addr
    )
    db.session.add(log)


# ------------------------------------------------------- presentación /auditoria/

_MAX_VALOR = 80
_RE_FECHA = re.compile(r'^(\d{4})-(\d{2})-(\d{2})$')
_RE_FECHA_HORA = re.compile(r'^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})')

# Sin fila en DB ni JSON identificable (tablas sin modelo propio).
_ETIQUETAS_TABLA = {'backup': 'Respaldo', 'google_sheets': 'Sincronización'}


def _fila_a_etiqueta(f):
    return f'Folio {f.folio}'


def _loader_simple(modelo, etiqueta_fn, opciones=None):
    """Loader estándar: filas por id → {registro_id: etiqueta}."""
    def cargar(ids):
        query = db.session.query(modelo).filter(modelo.id.in_(ids))
        if opciones is not None:
            query = query.options(opciones)
        etiquetas = {}
        for fila in query.all():
            etiqueta = etiqueta_fn(fila)
            if etiqueta:
                etiquetas[fila.id] = etiqueta
        return etiquetas
    return cargar


def _loader_comentarios(ids):
    """folio_comentarios no expone relación `folio`: join explícito."""
    filas = (db.session.query(FolioComentario, Folio)
             .join(Folio, Folio.id == FolioComentario.folio_id)
             .filter(FolioComentario.id.in_(ids)).all())
    return {comentario.id: f'Folio {folio.folio}'
            for comentario, folio in filas}


def _modelos_etiqueta():
    """tabla → loader(ids) → {registro_id: etiqueta}.

    Se construye en runtime: EntregaFolio.folio/DevolucionFolio.folio son
    backrefs de Folio y no existen al importar el módulo.
    """
    return {
        'folios': _loader_simple(Folio, _fila_a_etiqueta),
        'centros': _loader_simple(Centro, lambda c: c.name or None),
        'usuarios': _loader_simple(Usuario, lambda u: u.username),
        'tipo_certificados': _loader_simple(
            TipoCertificado, lambda t: t.name or None),
        'entrega_folios': _loader_simple(
            EntregaFolio, lambda e: f'Folio {e.folio.folio}' if e.folio else None,
            selectinload(EntregaFolio.folio)),
        'devolucion_folios': _loader_simple(
            DevolucionFolio,
            lambda d: f'Folio {d.folio.folio}' if d.folio else None,
            selectinload(DevolucionFolio.folio)),
        'transferencia_folios': _loader_simple(
            TransferenciaFolio,
            lambda t: f'Folio {t.folio.folio}' if t.folio else None,
            selectinload(TransferenciaFolio.folio)),
        'recepcion_folios': _loader_simple(
            RecepcionFolio, lambda r: f'Rango {r.folioInicial}-{r.folioFinal}'),
        'folio_comentarios': _loader_comentarios,
        # permiso_usuarios audita con registro_id = user.id (no la fila de grant).
        'permiso_usuarios': _loader_simple(Usuario, lambda u: u.username),
        'marca_config': _loader_simple(MarcaConfig, lambda m: m.nombre or None),
    }


def _etiqueta_desde_json(datos):
    """Identidad del registro desde el JSON ya guardado (sin tocar DB)."""
    if not datos:
        return None
    if datos.get('folio_numero') is not None:
        return f"Folio {datos['folio_numero']}"
    folio = datos.get('folio')
    if isinstance(folio, int) and not isinstance(folio, bool):
        return f'Folio {folio}'
    if datos.get('folioInicial') is not None and datos.get('folioFinal') is not None:
        return f"Rango {datos['folioInicial']}-{datos['folioFinal']}"
    for clave in ('name', 'username', 'nombre'):
        valor = datos.get(clave)
        if valor:
            return str(valor)
    return None


def _formatar(valor):
    """Valor del JSON → texto corto en español (fecha, bool, lista, corte)."""
    if valor is None:
        return '—'
    if isinstance(valor, bool):
        return 'Sí' if valor else 'No'
    if isinstance(valor, list):
        texto = ', '.join(str(v) for v in valor)
    elif isinstance(valor, dict):
        texto = json.dumps(valor, ensure_ascii=False)
    elif isinstance(valor, str):
        match = _RE_FECHA.match(valor) or _RE_FECHA_HORA.match(valor)
        if match:
            grupos = match.groups()
            texto = f'{grupos[2]}/{grupos[1]}/{grupos[0]}'
            if len(grupos) == 5:
                texto += f' {grupos[3]}:{grupos[4]}'
        else:
            texto = valor
    else:
        texto = str(valor)
    if not texto:
        return '—'
    if len(texto) > _MAX_VALOR:
        texto = texto[:_MAX_VALOR] + '…'
    return texto


def _campos(log):
    """[(clave, texto)] del detalle: diff en UPDATE, valores en el resto."""
    if log.accion == 'UPDATE':
        antes = log.datos_anteriores or {}
        despues = log.datos_nuevos or {}
        claves = list(despues) + [k for k in antes if k not in despues]
        return [
            (k, f'{_formatar(antes.get(k))} → {_formatar(despues.get(k))}')
            for k in claves if antes.get(k) != despues.get(k)
        ]
    datos = log.datos_anteriores if log.accion == 'DELETE' else log.datos_nuevos
    return [(k, _formatar(v)) for k, v in (datos or {}).items()]


def describir_logs(logs):
    """{log.id: {'etiqueta': str|None, 'campos': [(clave, texto)]}}.

    La etiqueta resuelve en orden: JSON del log (sin query) → DB en lote
    (una query por tabla de la página) → fallback por tabla → None (la
    plantilla muestra solo #id). Los campos no tocan DB.
    """
    logs = list(logs)
    descripciones = {}
    sin_etiqueta = []
    for log in logs:
        etiqueta = (_etiqueta_desde_json(log.datos_nuevos)
                    or _etiqueta_desde_json(log.datos_anteriores))
        if etiqueta:
            descripciones[log.id] = {'etiqueta': etiqueta, 'campos': _campos(log)}
        else:
            sin_etiqueta.append(log)

    por_tabla = {}
    loaders = _modelos_etiqueta()
    for log in sin_etiqueta:
        if log.tabla in loaders and log.registro_id:
            por_tabla.setdefault(log.tabla, []).append(log)

    encontradas = {}
    for tabla, items in por_tabla.items():
        ids = {log.registro_id for log in items}
        for registro_id, etiqueta in loaders[tabla](ids).items():
            encontradas[(tabla, registro_id)] = etiqueta

    for log in sin_etiqueta:
        etiqueta = (encontradas.get((log.tabla, log.registro_id))
                    or _ETIQUETAS_TABLA.get(log.tabla))
        descripciones[log.id] = {'etiqueta': etiqueta, 'campos': _campos(log)}
    return descripciones
