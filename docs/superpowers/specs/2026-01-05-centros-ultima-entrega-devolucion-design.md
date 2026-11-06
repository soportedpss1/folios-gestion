# Centros: última entrega y última devolución

Fecha: 2026-01-05
Estado: pendiente de aprobación

## Intención

En el módulo de centros de salud, ver de un vistazo hace cuánto se le entregaron folios a cada centro y hace cuánto devolvió, sin entrar al detalle de cada uno.

## Goals

- Dos columnas nuevas en el listado `/centros/`: **Última entrega** y **Última devolución** (fecha dd/mm/aaaa, `-` si no hay registros).
- Las mismas dos columnas en los exports de la lista: `centros.xlsx` y `centros.pdf`.

## Non-goals

- No se toca el detalle del centro (`/centros/<id>/detail`) ni sus exports.
- No se crean columnas ni tablas: los datos ya existen en `entrega_folios.fechaEntrega` y `devolucion_folios.fechaDevolucion`.
- No cambia el orden de la tabla ni los filtros de DataTables.

## Enfoques considerados

1. **Solo el listado** — más rápido, pero el Excel/PDF dejan de reflejar la tabla en pantalla.
2. **Listado + exports de la lista** *(elegido)* — lo que se ve en pantalla es lo que se exporta.
3. **Listado + exports + detalle del centro** — alcance completo, innecesario: el detalle ya muestra las fechas por folio.

## Diseño

- **Consulta**: dos `GROUP BY` agregados en `centros.index()` y en los dos exports:
  - `db.session.query(EntregaFolio.centroId, func.max(EntregaFolio.fechaEntrega)).group_by(...)` → dict `{centroId: fecha}`
  - igual con `DevolucionFolio.fechaDevolucion`
  - Se calcula una vez por request y se pasa como dict al template/export. Dos consultas ligeras con índice (`idx_entrega_centroId`, `idx_devolucion_centroId`), sin N+1.
- **`app/templates/centros/index.html`**: dos `<th>` entre Dirección y Estado; dos `<td>` con `| dd/mm/aaaa` (filtro `strftime` manual en Jinja o `{{ fecha.strftime('%d/%m/%Y') }}`) y `-` si es `None`. El `colspan` del estado vacío pasa de 5 a 7.
- **Excel (`export_lista_excel`)**: headers `Última entrega` y `Última devolución` después de Dirección; celdas con `fecha.strftime('%d/%m/%Y')` o `''`.
- **PDF (`export_lista_pdf`)**: dos `<th>`/`<td>` en las mismas posiciones; `-` si no hay fecha.

## Fuera de alcance / decisiones abiertas

Ninguna. El formato de fecha sigue el resto del módulo (dd/mm/aaaa).
