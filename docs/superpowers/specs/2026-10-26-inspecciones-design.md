# Spec: Inspecciones de datos (recepciones, entregas, devoluciones)

Fecha: 2026-10-26
Estado: aprobado en diseño; pendiente de revisión

## Contexto y objetivo

Los módulos de recepción, entregas y devoluciones ya permiten **corregir**
registros (rutas `edit` con forms, validaciones y audit), pero no hay nada
que ayude a **encontrar** los errores humanos ya registrados: una entrega
con fecha anterior a la recepción de su folio, una devolución anterior a su
entrega, fechas futuras heredadas de antes del validador de fecha no
futura, folios cuyo `estado` no coincide con sus registros, etc.

Objetivo: un módulo **Inspecciones** que corre chequeos automáticos de
coherencia sobre los datos existentes, liste los registros que fallan cada
chequeo, y lleve al usuario a corregirlos con las pantallas de edición ya
existentes.

## Alcance

- Nuevo blueprint `inspecciones` (`/inspecciones`) + servicio de chequeos.
- Permiso granular nuevo `inspecciones.ver` (default `admin`).
- Link en el sidebar (sección admin, junto a Auditoría).
- 6 chequeos de coherencia (detalle abajo).
- **Acción nueva en módulo existente**: `POST /folios/<id>/estado` para
  corregir el estado de un folio desde su detalle (el estado hoy no es
  editable en la UI; sin esto el chequeo 4 quedaría sin camino de
  corrección). Patrón idéntico a `perder`/`recuperar`: POST + flash +
  audit, permiso `folios.actualizar` (ya existe).

## Fuera de alcance

- Corrección inline desde inspecciones: la corrección es siempre vía la
  pantalla de edición del módulo dueño (cero duplicación de forms/reglas).
- Nuevas columnas, modelos o migraciones.
- Cambiar el comportamiento de los flujos existentes de cualquier módulo:
  la única adición a un módulo existente es la acción `folios.<id>/estado`
  descrita en Alcance (no modifica flujos actuales, solo añade uno).
- Chequeo del estado `perdido` (tiene lógica propia de marcado/recuperación).
- Exportación de hallazgos a PDF/Excel.
- Alertas o ejecución programada: la inspección corre bajo demanda.

## Arquitectura

```
app/inspecciones/__init__.py     # blueprint inspecciones_bp (prefix /inspecciones)
app/services/inspecciones.py     # chequeos puros: cada uno devuelve una query
app/templates/inspecciones/index.html    # resumen: una tarjeta por chequeo
app/templates/inspecciones/detalle.html  # listado paginado de un chequeo
```

- Los chequeos viven en el servicio (sin dependencia de Flask-Request):
  probables sin HTTP, como `app/services/kpis.py`.
- Registro de chequeos: estructura `CHEQUEOS` (orden fijo) con
  `clave -> (titulo, descripcion, funcion_query)`. El resumen y el detalle
  recorren el registro; añadir un chequeo futuro = una función + una entrada.
- Cada función de chequeo devuelve una **query** (no una lista) para que la
  ruta pagine en SQL: columnas mínimas `titulo`, `detalle`, `id_corregir`
  (+ `modulo` donde hace falta) y la ruta construye `url_corregir` con
  `url_for` y pagina con `.paginate(page, per_page=25)`.
- Solo lectura: inspecciones **no escribe audit** (las correcciones ya
  auditan en sus módulos de origen).

## Permisos

- Nueva clave en `app/services/permisos.py`:
  `'inspecciones.ver': ('Ver inspecciones de datos', 'admin')`.
- Rutas protegidas con `@login_required` + `@permiso_requerido('inspecciones.ver')`
  (default `hacia='dashboard'`, como las secciones admin).
- La inspección **no amplía poder de edición**: cada link "Corregir" cae en
  una ruta que ya exige su propio permiso (`recepcion.gestionar`,
  `entregas.gestionar`, `devoluciones.gestionar`, `folios.actualizar`).
- Sidebar: link con `{% if puede('inspecciones.ver') %}` (mismo patrón que
  Auditoría).

## Rutas

- `GET /inspecciones/` → `inspecciones.index`: por cada chequeo del
  registro, una tarjeta con título, descripción y conteo de hallazgos.
  Conteo 0 → tarjeta verde "Sin inconsistencias"; > 0 → link al detalle.
- `GET /inspecciones/<clave>` → `inspecciones.detalle`: listado paginado
  (25/página) de los hallazgos. Clave desconocida → 404 (`get_or_404`-like:
  lookup en `CHEQUEOS`, abort 404).

## Chequeos

Todos se resuelven con joins sobre índices existentes
(`entrega_folios.folio_id` y `devolucion_folios.folio_id` son únicos;
`recepcion_folios.rangoId` es unique). Sin N+1.

### 1. `entrega-antes-recepcion`

`EntregaFolio JOIN Folio (folio_id) JOIN RecepcionFolio (Folio.rangoId =
RecepcionFolio.rangoId)` WHERE `EntregaFolio.fechaEntrega <
RecepcionFolio.fecha`. El folio se entregó antes de existir.
"Corregir" → `/entregas/<id>/edit`.

### 2. `devolucion-antes-entrega`

`DevolucionFolio JOIN EntregaFolio (mismo folio_id)` WHERE
`DevolucionFolio.fechaDevolucion < EntregaFolio.fechaEntrega`.
"Corregir" → `/devoluciones/<id>/edit`.

### 3. `fechas-futuras`

Unión de las tres tablas con su fecha > `date.today()`:
`recepcion_folios.fecha`, `entrega_folios.fechaEntrega`,
`devolucion_folios.fechaDevolucion`. Detecta datos heredados de antes del
validador de fecha no futura (o escritos directo en DB). Cada fila lleva su
módulo; "Corregir" → `/recepcion/<id>/edit`, `/entregas/<id>/edit` o
`/devoluciones/<id>/edit` según el módulo.

### 4. `estado-inconsistente`

`Folios` donde:

- `estado = 'entregado'` y sin fila en `entrega_folios`, o
- `estado = 'devuelto'` y sin fila en `devolucion_folios`, o
- `estado = 'disponible'` y **con** fila en `entrega_folios`.

(El estado `perdido` queda fuera, por diseño: su recuperación deriva del
registro de entrega, no del campo `estado`.)
"Corregir" → `/folios/<id>` (detalle del folio).

### 4b. Acción de corrección de estado (en `app/folios/`)

Como el `estado` no es editable en la UI (el detalle solo lo muestra y el
modal de `/folios/` solo edita digitado/escaneado/nulo), se añade:

- `POST /folios/<id>/estado` → `folios.cambiar_estado`: recibe
  `estado` en el form, valida contra los estados legítimos del sistema
  (`disponible`, `entregado`, `devuelto` — no `perdido`, que tiene su
  flujo propio, ni los flags digitado/escaneado/nulo, que son columnas
  separadas), actualiza `Folio.estado`, audit `UPDATE` (tabla `folios`,
  solo el campo `estado`), commit, flash "Estado actualizado
  exitosamente.", redirect al detalle.
- Permiso: `folios.actualizar` (ya en el catálogo, default `edit`).
- Botón en `details.html`: formulario con select de los 3 estados
  válidos + confirmación (`data-confirm`, patrón del módulo), visible
  igual que los botones perder/recuperar.
- La corrección es manual y consciente: el módulo de inspecciones no
  llama a esta ruta, solo enlaza al detalle donde el usuario la usa.

### 5. `centro-devolucion-distinto`

`DevolucionFolio JOIN EntregaFolio (mismo folio_id)` WHERE
`DevolucionFolio.centroId != EntregaFolio.centroId`. Hoy ya se bloquea al
editar, pero los datos heredados pueden tenerlo.
"Corregir" → `/devoluciones/<id>/edit`.

### 6. `rangos-corruptos`

`RecepcionFolio` donde `folioInicial > folioFinal`, o cuyo rango se solapa
con otro de mismo `anioCert` + `tipoCert_id`
(self-join: `a.id < b.id` para no duplicar filas). La app ya lo impide al
escribir; apunta a datos heredados o importados directo en DB.
"Corregir" → `/recepcion/<id>/edit`.

## UI / Templates

- `index.html`: extiende `base.html`; tarjetas (Bootstrap cards) en grilla,
  una por chequeo: título, descripción, conteo grande, link "Ver
  hallazgos" (solo si > 0). Sin hallazgos → badge verde
  "Sin inconsistencias".
- `detalle.html`: título del chequeo + descripción + tabla con columnas
  `Registro` (titulo), `Detalle` (detalle), `Corregir` (botón/link).
  Filtrado por paginación del patrón del resto de la app (mismos
  controles de paginación que index de otros módulos).
- Fechas en UI: dd/mm/aaaa (filtro `|localtime` para fechas datetime, y
  `strftime('%d/%m/%Y')` para `Date`), como el resto de la app.
- Texto en español; toasts con "exitosamente" (invariante
  `test_flashes_sin_correctamente` — inspecciones no flash de éxito, pero
  aplica si se añade alguno).

## Manejo de errores

- Sin permiso → flash "No tiene permisos para acceder a esta sección." +
  redirect a dashboard (patrón actual de `permiso_requerido`).
- Clave desconocida → 404.
- Chequeo sobre DB vacía → resumen con 6 tarjetas verdes, sin error.

## Testing (TDD)

`tests/test_inspecciones.py`:

- Por cada chequeo: un test que crea datos que **fallan** (hallazgo
  presente, con el registro correcto y link correcto) y datos que **no**
  fallan (cero falsos positivos).
- `fechas-futuras`: cubre las tres tablas.
- `estado-inconsistente`: cubre los tres subcasos + que un folio `devuelto`
  con entrega y devolución **no** aparece.
- Rutas: resumen muestra los 6 conteos; detalle pagina (crear 26+ hallazgos
  → 2 páginas); clave desconocida → 404.
- Permisos: usuario sin `inspecciones.ver` (lector) → redirect a dashboard
  en ambas rutas; admin → 200. Concedido `inspecciones.ver` a un lectura →
  200 (grants funcionan).
- Sidebar: el link aparece para admin y no para un lectura sin grant.
- `folios.cambiar_estado`: cambia entregado-sin-entrega → disponible (y
  audit UPDATE con el campo estado); estado inválido (`perdido`, `digitado`,
  valor inventado) → rechazado sin cambio; sin `folios.actualizar` → 403.

## Rendimiento

- 6 conteos en el resumen: cada uno una query con joins indexados. Con
  decenas de miles de folios y cientos de recepciones es despreciable.
- Los listados se paginan en SQL (25/página), nunca se materializan todos
  los hallazgos en memoria.
- El `self-join` de solapes de rangos es sobre `recepcion_folios` (pocas
  filas por diseño: una por rango recibido).

## Compatibilidad

- Sin migración ni cambio de modelo: solo lectura sobre tablas existentes.
- Los chequeos toleran datos heredados incompletos (FKs son NOT NULL, pero
  los joins usan INNER: una fila huérfana no rompe la query, simplemente
  no se evalúa en ese chequeo).
