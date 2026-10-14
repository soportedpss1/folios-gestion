"""Lógica compartida entre entregas y devoluciones de folios.

Ambos blueprints hacen lo mismo con estados espejo: entregar pasa
`disponible -> entregado` y devolver `entregado -> devuelto`. Centralizar aquí
choices y consultas de API evita que un cambio llegue a uno y no al otro.
Ningún edit cambia de folio: los estados solo los tocan la creación.
"""

from sqlalchemy import String, cast
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.centro import Centro
from app.models.entrega_folio import EntregaFolio
from app.models.folio import Folio
from app.models.tipo_certificado import TipoCertificado
from app.services.import_excel import COLUMNA_USUARIO, a_entero, a_fecha
from app.services.queries import resolver_usuario_nombre


# Tope de <option> que se piden de una vez a /entregas/api/folios-disponibles.
# El create pide el total del tipo elegido (no hay búsqueda); editar entrega
# no consume esta API porque allí el folio no se cambia.
MAX_FOLIOS_SELECT = 10000


def choices_centros(actual_id, placeholder=None):
    """Choices de centro: siempre los activos, más el actual aunque esté desactivado.

    Sin el actual, un select con valor fuera de choices cae en la primera opción
    y guardar reasigna el registro a otro centro sin avisar.

    `placeholder` añade una primera opción vacía (value="") para forzar una
    elección explícita en los formularios de creación. Solo con value vacío:
    el coerce de id no admite un valor '' distinto de None.
    """
    activos = Centro.query.filter_by(activo=True).order_by(Centro.name).all()
    choices = [(c.id, c.name) for c in activos]
    if actual_id and not any(cid == actual_id for cid, _ in choices):
        actual = db.session.get(Centro, actual_id)
        if actual:
            choices.append((actual.id, f'{actual.name} (inactivo)'))
    if placeholder:
        choices.insert(0, ('', placeholder))
    return choices


def choices_folio_actual(fid):
    """Un solo choice para editar entrega/devolución: el folio de ese registro.

    El folio no se cambia desde editar; cualquier otro valor en el POST queda
    fuera de choices y la validación lo rechaza.
    """
    if not fid:
        return []
    folio = db.session.get(Folio, fid)
    if folio is None:
        return []
    return [(folio.id, f'Folio {folio.folio}')]


def choices_folios_entrega(folio_ids):
    """Choices de creación de entrega: solo los folios enviados y disponibles."""
    if not folio_ids:
        return []
    folios = Folio.query.filter(
        Folio.id.in_(folio_ids),
        Folio.estado == 'disponible',
        Folio.nulo.is_(False),
    ).order_by(Folio.folio, Folio.id).all()
    return [(f.id, f'Folio {f.folio}') for f in folios]


def choices_folios_devolucion(folio_ids, centro_id):
    """Choices de creación de devolución: solo los folios enviados que ese
    centro tenga entregados."""
    if not folio_ids or not centro_id:
        return []
    folios = db.session.query(Folio).join(EntregaFolio).options(
        selectinload(Folio.tipo_cert)
    ).filter(
        EntregaFolio.centroId == centro_id,
        Folio.estado == 'entregado',
        Folio.id.in_(folio_ids),
    ).order_by(Folio.folio, Folio.id).all()
    return [(f.id, f'Folio {f.folio} - {f.tipo_cert.name}') for f in folios]


def folios_disponibles(q, tipo_id=None, limit=100):
    """(lista, total) de búsqueda para el select de nueva entrega.

    `tipo_id` es solo un filtro de vista (no se valida en el POST).
    `total` es el conteo sin el límite: el JS detecta con él si el select
    quedó truncado y avisa al usuario.
    """
    query = Folio.query.filter_by(estado='disponible', nulo=False)
    if tipo_id:
        query = query.filter_by(tipoCert_id=tipo_id)
    if q:
        # Folio.folio es Integer: LIKE directo deprecado (SADeprecationWarning)
        query = query.filter(cast(Folio.folio, String).like(f'%{q}%'))
    total = query.count()
    folios = query.options(selectinload(Folio.tipo_cert)) \
        .order_by(Folio.folio, Folio.id).limit(limit).all()
    lista = [{'id': f.id, 'texto': f'Folio {f.folio} - {f.tipo_cert.name}'} for f in folios]
    return lista, total


def folios_entregados_a(centro_id, tipo_id=None):
    """JSON de folios entregados a un centro, para el select de devolución."""
    query = db.session.query(Folio).join(EntregaFolio).filter(
        EntregaFolio.centroId == centro_id,
        Folio.estado == 'entregado',
    )
    if tipo_id:
        query = query.filter(Folio.tipoCert_id == tipo_id)
    folios = query.options(selectinload(Folio.tipo_cert)) \
        .order_by(Folio.folio, Folio.id).all()
    return [{'id': f.id, 'texto': f'Folio {f.folio} - {f.tipo_cert.name}'} for f in folios]


def resolver_folios_para_importar(filas, *, estado, excluir_nulos=False):
    """Resuelve filas {folio, tipoCert, anioCert, fecha, centro, usuario} de un .xlsx.

    Compartido por importar de entregas y devoluciones. Devuelve
    (preview, payload): preview tiene una entrada por fila con 'error' en
    español o None, la fecha, el centro y el responsable ('usuario'); payload
    es la lista de {'id': folio_id, 'usuarioId': uid, 'fecha': iso,
    'centroId': cid} de las filas válidas — la columna `fecha` es obligatoria
    por fila (formato dd/mm/aaaa o aaaa-mm-dd, o celda de fecha de Excel) y
    `usuario` TAMBIÉN: celda vacía → 'Usuario vacío.'; desconocida o inactiva
    → la fila queda inválida.

    El centro TAMBIÉN viene por fila (columna obligatoria `centro`) y se
    compara EXACTAMENTE con Centro.name: vacío, desconocido o inactivo deja
    la fila inválida. Para devoluciones (estado='entregado') solo pasa el
    folio si el centro de su fila lo tiene entregado. El folio no es único
    solo por número: se busca por (anioCert, tipoCert_id, folio).
    """
    tipos = {t.name.strip().lower(): t.id
             for t in TipoCertificado.query.filter_by(activo=True).all()}
    centros = {c.name: c for c in Centro.query.all()}

    preview = []
    pendientes = []  # (índice en preview, folio, anio, tipo_id, centro_id)
    for n, row in enumerate(filas, 1):
        num = a_entero(row.get('folio'))
        anio = a_entero(row.get('anioCert'))
        nombre = str(row.get('tipoCert') or '').strip()
        tipo_id = tipos.get(nombre.lower())
        fecha = a_fecha(row.get('fecha'))
        crudo = row.get('centro')
        texto_centro = crudo if isinstance(crudo, str) else (
            '' if crudo is None else str(crudo))
        etiqueta = f'Folio {num if num is not None else "?"} - {nombre or "?"} {anio or ""}'
        error = None
        usuario = None
        centro_id = None
        if num is None or num < 1:
            error = 'Número de folio inválido.'
        elif anio is None or not 2000 <= anio <= 2100:
            error = 'Año fuera de rango (2000-2100).'
        elif tipo_id is None:
            error = f'Tipo de certificado desconocido: {nombre or "vacío"}.'
        elif fecha is None:
            error = 'Fecha inválida (use dd/mm/aaaa).'
        if error is None:
            if not texto_centro.strip():
                error = 'Centro de salud vacío.'
            else:
                centro = centros.get(texto_centro)
                if centro is None:
                    error = f'Centro de salud desconocido: {texto_centro}.'
                elif not centro.activo:
                    error = f'Centro de salud inactivo: {texto_centro}.'
                else:
                    centro_id = centro.id
        if error is None:
            usuario, error = resolver_usuario_nombre(
                row.get(COLUMNA_USUARIO))
        preview.append({
            'n': n,
            'etiqueta': etiqueta,
            'fecha': fecha,
            'centro': texto_centro or None,
            'centro_id': centro_id,
            'usuario': usuario.username if usuario else None,
            'usuario_id': usuario.id if usuario else None,
            'error': error,
        })
        if error is None:
            pendientes.append((len(preview) - 1, num, anio, tipo_id, centro_id))

    if pendientes:
        encontrados = Folio.query.filter(
            Folio.anioCert.in_({p[2] for p in pendientes}),
            Folio.tipoCert_id.in_({p[3] for p in pendientes}),
            Folio.folio.in_({p[1] for p in pendientes}),
        ).all()
        mapa = {(f.anioCert, f.tipoCert_id, f.folio): f for f in encontrados}

        entregado_en = set()
        if estado == 'entregado' and encontrados:
            entregado_en = {
                (e.folio_id, e.centroId) for e in EntregaFolio.query.filter(
                    EntregaFolio.folio_id.in_([f.id for f in encontrados]),
                    EntregaFolio.centroId.in_({p[4] for p in pendientes}),
                ).all()
            }

        vistos = set()
        for idx, num, anio, tipo_id, centro_id in pendientes:
            folio = mapa.get((anio, tipo_id, num))
            if folio is None:
                preview[idx]['error'] = 'El folio no existe.'
                continue
            clave = (anio, tipo_id, num)
            if clave in vistos:
                preview[idx]['error'] = 'Folio repetido en el archivo.'
                continue
            vistos.add(clave)
            if folio.estado != estado:
                preview[idx]['error'] = f'El folio no está {estado}.'
                continue
            if excluir_nulos and folio.nulo:
                preview[idx]['error'] = 'El folio está marcado como nulo.'
                continue
            if estado == 'entregado' and (folio.id, centro_id) not in entregado_en:
                preview[idx]['error'] = 'Ese centro no lo tiene entregado.'
                continue
            preview[idx]['id'] = folio.id

    payload = [{'id': p['id'], 'usuarioId': p['usuario_id'],
                'fecha': p['fecha'].isoformat(), 'centroId': p['centro_id']}
               for p in preview if 'id' in p]
    return preview, payload


def folios_devolubles(folios_centros):
    """{folio_id: centro_id} → ids que el centro de su fila tiene entregados.

    Revalidación del confirm de importar de devoluciones: el centro viene por
    fila, así que el par (folio, centro) se comprueba uno a uno (el hidden es
    editable y el estado pudo cambiar desde la vista previa).
    """
    if not folios_centros:
        return []
    filas = db.session.query(
        EntregaFolio.folio_id, EntregaFolio.centroId
    ).join(Folio, Folio.id == EntregaFolio.folio_id).filter(
        EntregaFolio.folio_id.in_(folios_centros),
        EntregaFolio.centroId.in_(set(folios_centros.values())),
        Folio.estado == 'entregado',
    ).all()
    pares = {(f, c) for f, c in filas}
    return [fid for fid, cid in folios_centros.items() if (fid, cid) in pares]


def crear_movimiento(*, modelo, fecha_field, folio_ids, fecha, centro_id, user,
                     estado_origen, estado_destino, excluir_nulos, tabla_audit,
                     log_audit, actor=None):
    """Registra un lote de entregas o devoluciones en una sola transacción.

    Devuelve (creados, omitidos). Un folio se omite si otra operación ya cambió
    su estado entre la validación del form y este bucle; el llamador lo avisa.

    `user` es el responsable del registro (userId); `actor` quien ejecuta la
    operación y aparece en audit_logs (por defecto, el mismo).
    """
    # IDs repetidos en el POST: el segundo encuentro vería el estado ya
    # mutado y contaría un "omitido" inexistente en el flash.
    folio_ids = list(dict.fromkeys(folio_ids))
    creados = 0
    for folio_id in folio_ids:
        folio = db.session.get(Folio, folio_id)
        if folio is None or folio.estado != estado_origen:
            continue
        if excluir_nulos and folio.nulo:
            continue
        registro = modelo(
            folio_id=folio_id,
            **{fecha_field: fecha},
            centroId=centro_id,
            userId=user.id,
        )
        folio.estado = estado_destino
        db.session.add(registro)
        db.session.flush()
        log_audit((actor or user).id, 'INSERT', tabla_audit, registro.id, None,
                  registro.to_dict())
        creados += 1
    return creados, len(folio_ids) - creados

