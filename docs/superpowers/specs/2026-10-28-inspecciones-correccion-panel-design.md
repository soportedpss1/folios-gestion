# Spec: Corrección desde Inspecciones (paneles que reusan los endpoints dueños)

## Contexto y objetivo

El módulo de inspecciones (spec `2026-10-26-inspecciones-design.md`) detecta
inconsistencias y **linkea** a la pantalla de edición del módulo dueño. El
usuario pide que las correcciones ocurran **desde el propio módulo de
inspecciones**, sin navegar fuera.

Decisión de diseño aprobada (Approach A): paneles modales cuyo POST va a los
**mismos endpoints** de los módulos dueños, con un modo JSON en dichas rutas.
Formularios, validación, guardado y auditoría viven en un solo sitio — el
módulo dueño. Inspecciones no duplica reglas.

## Alcance

- Contrato JSON (`quiere_json()`) en 4 rutas dueñas:
  `entregas.edit`, `devoluciones.edit`, `recepcion.edit`,
  `folios.cambiar_estado` (gana método GET).
- Partials de form compartidos por módulo: la página de edición dueña y el
  modal de inspecciones renderizan **la misma plantilla**.
- Modal genérico en `inspecciones/detalle.html` + JS de panel (fetch, CSRF,
  errores inline).
- Los 6 chequeos obtienen panel (los 4 módulos dueños cubren todos).
- Tests TDD nuevos (~17) + ajuste de 2 tests existentes que exigen la URL
  dueña como substring.

## Fuera de alcance

- Nuevos chequeos o cambios a `CHEQUEOS`/queries del servicio.
- Edición "inline" en celdas de la tabla (sin modal).
- Migraciones, modelos, permisos nuevos.
- `inspecciones/index.html`: las tarjetas y conteos no cambian.
- Cambiar la semántica detect-and-link: sin permiso de edición del módulo
  dueño, el link plano actual sigue funcionando.

## Contrato JSON

Detección única: `quiere_json()` en `app/utils.py` —
`request.accept_mimetypes.best == 'application/json'`. Solo el fetch de
inspecciones envía ese header; la navegación normal (Accept: text/html) no
entra en la rama.

| Caso | Respuesta |
|---|---|
| GET con `Accept: application/json` | `200 {ok: true, campos_html: "<partial _form renderizado>"}` |
| POST válido | `200 {ok: true}` (mismo commit + audit de siempre) |
| POST con error de campo (WTForms) | `400 {ok: false, errores: {campo: primer_mensaje}}` |
| POST con error de negocio (flash de la ruta dueña: folios usados, integridad, fecha inválida en cambiar_estado…) | `400 {ok: false, error: "<mensaje>"}` |
| Sin header JSON | Comportamiento actual **intacto** (redirect/flash/render) — las ramas JSON son exclusivas |

Las ramas JSON están bajo los mismos `@login_required` +
`@permiso_requerido(...)` de siempre: el modo no otorga ningún permiso.

## Rutas dueñas (cambios)

1. `app/entregas/__init__.py` — `edit(id)`: ramas JSON en GET/POST.
2. `app/devoluciones/__init__.py` — `edit(id)`: ídem.
3. `app/recepcion/__init__.py` — `edit(id)`: ídem (incluye errores de solape
   como `errores.folioInicial`/`folioFinal` y el caso de folios usados como
   `error`).
4. `app/folios/__init__.py` — `cambiar_estado`: `methods=['GET', 'POST']`;
   GET devuelve `campos_html` del partial de estado (carga el folio con
   `get_or_404`); POST ya valida — en modo JSON responde el contrato.

Cada ruta: la rama JSON envuelve el flujo existente; la lógica de guardado,
`log_audit` y validación no se mueve ni se copia.

## Partials compartidos

- `app/templates/entregas/_form.html`, `app/templates/devoluciones/_form.html`,
  `app/templates/recepcion/_form.html`: extracción de los campos de sus
  `edit.html` actuales (los edit.html pasan a `{% include %}`).
- `app/templates/folios/_form_estado.html`: el select de estado extraído del
  header de `details.html` (que lo incluye).
- Un solo sitio para campos, mensajes de validación y `csrf_token`.
- La alerta de preview de rangos y el bloque `extra_js` de
  `recepcion/edit.html` **no** entran al partial: se quedan en `edit.html`.

## UI / Modal

- Cada fila de hallazgo con permiso de edición dueño lleva
  `<button data-panel data-url="<URLS_CORREGIR...>" data-titulo="...">Corregir</button>`;
  sin permiso → `<a href>` actual.
- `data-url` = la ruta dueña de la corrección. Excepción: para
  `estado-inconsistente`, `URLS_CORREGIR['folios']` apunta a `folios.details`
  (donde vive el form de estado condicional) — el **link plano** sigue hacia
  el detalle, pero el `data-url` del panel va al endpoint JSON
  `/folios/<id>/estado`. La vista expone `h['url_panel']` para esto.
- Un único modal Bootstrap (`modal-lg`, `modal-dialog-scrollable` — el form de
  recepción es grande) en `detalle.html`.
- JS del panel (`app/static/js/inspecciones_panel.js`, cargado por
  `detalle.html`):
  1. Abrir → fetch GET `data-url` con `Accept: application/json` → inyectar
     `campos_html` en el body del modal.
  2. Submit → fetch POST con `FormData` (incluye `csrf_token` oculto) +
     `Accept: application/json`.
  3. `ok` → toast de éxito, cerrar modal, `location.reload()` (el hallazgo
     desaparece y baja el conteo si quedó corregido).
  4. `errores.campo` → `.is-invalid` + `.invalid-feedback` en ese campo;
     `error` → banner dentro del modal. Ambos pueden venir juntos.
  5. Respuesta no-JSON (p. ej. redirect por permiso) o fallo de red → toast
     de error genérico sin navegar.

Textos en español; nunca "correctamente" (invariante de la suite).
Toast de éxito pineado: `Corregido exitosamente.`; toast de fallo de
red/respuesta: `No se pudo guardar. Intente de nuevo.`

## Permisos

- Botón de panel solo si `puede('entregas.gestionar' | 'devoluciones.gestionar'
  | 'recepcion.gestionar' | 'folios.actualizar')` según el módulo dueño del
  hallazgo; el modal es UI — la autoridad sigue siendo la ruta dueña.
- `inspecciones.ver` no cambia.

## Seguridad

- Sin parámetro `next`: el fetch no navega → cero superficie de
  open-redirect nueva.
- `campos_html` es un partial renderizado por el servidor (values escapados
  por Jinja) — no se refleja input del usuario sin escapar.
- CSRF: token en `FormData` (Flask-WTF lo valida igual que en form normal).

## Manejo de errores

- Errores de negocio que hoy hacen `flash(...)` + redirect: en modo JSON
  responden `400 {ok: false, error}` con el **mismo** mensaje.
- Fallo de red / JSON malformado → toast de error, el modal queda abierto
  (no se pierde lo escrito).
- Si la validación pasa pero el hallazgo persiste (dato correlacionado en
  otra tabla), la recarga lo vuelve a mostrar — comportamiento esperado, no
  se oculta.

## Testing (TDD)

Archivo nuevo `tests/test_inspecciones_panel.py` (~17 tests):

- **entregas**: GET-json devuelve `campos_html` con `name="fechaEntrega"`;
  POST-json válido → `{ok:true}` + fecha cambiada + `audit_log` UPDATE;
  POST-json con fecha futura → 400 `errores.fechaEntrega` + sin cambio;
  POST-json con regla de negocio (folio devuelto + centro cambiado) → 400
  `{error}` sin clave `errores`; POST **sin** header → redirect intacto.
- **devoluciones**: mismo triple (campo `fechaDevolucion`; error de fecha
  futura). Su único `error` de negocio es `IntegrityError` (indirecto: la
  forma `{error}` ya la cubren entregas/cambiar_estado).
- **recepcion**: GET-json con `name="folioInicial"`; POST-json corrige un
  solape → `{ok:true}` y el chequeo `rangos-corruptos` queda sin hallazgo;
  POST-json con solape nuevo → 400 con `errores` no vacío + sin cambio.
- **cambiar_estado**: GET-json devuelve select; POST-json válido → estado +
  audit; POST-json `'perdido'` → 400 `{error}` + sin cambio; GET **sin**
  header → redirect al detalle.
- **detalle.html**: los 6 hallazgos renderizan `data-panel` + `data-url`
  correcto; usuario con `inspecciones.ver` pero sin permiso de edición dueño
  → `<a href>` (sin `data-panel`).
- **Ajuste de 2 tests existentes** (`test_detalle_muestra_hallazgo_y_link_corregir`,
  `test_fechas_futuras_link_por_modulo`): hoy exigen la URL dueña como
  substring suelta; se endurecen a `data-url="<url exacta>"` — la spec
  obliga a que el control de corrección (admin tiene permiso) sea el botón
  con `data-url`.
- Regresión: suites existentes de entregas/devoluciones/recepcion/folios
  intactas (la rama no-JSON no cambió) — correr la suite completa.

## Compatibilidad

- Sin cambios de modelo, migración, config ni permisos.
- `URLS_CORREGIR` pasa de alimentar `<a href>` a alimentar `data-url`
  (con `h['url_panel']` para el endpoint de estado, ver UI/Modal).
- Las páginas de edición dueñas quedan visualmente idénticas (mismo partial).
