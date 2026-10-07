# Módulo de escaneos de folios — diseño

Fecha: 2026-10-07
Estado: aprobado en chat, pendiente revisión de spec

## Objetivo

Nuevo módulo para subir JPGs (folios escaneados) a una carpeta del servidor organizada en subcarpetas por año. Cuando el nombre de un JPG coincide con un folio en la DB, ese folio se marca `escaneado=True`.

## Decisiones del usuario

- **Matching**: carpeta da el año; nombre `<número>.jpg`. Si coincide con folio(s) de ese año → se marcan **todos** los folios con ese número en ese año (cualquier tipo de certificado).
- **Año de la subcarpeta**: selector de año en el form (choices = `anioCert` distinct).
- **JPG sin match**: se guarda igual en la carpeta del año; se reporta "sin coincidencia" sin marcar nada.
- **Archivo repetido**: sobrescribir (el escáner más reciente gana).
- **Ubicación**: env var `SCANS_FOLDER` (default `scans/`), volumen Docker `./scans:/app/scans`, gitignored.
- **Permiso**: nuevo `escaneos.subir` en el catálogo (`'edit'`).
- **Límite**: multi-archivo por request, respeta `MAX_CONTENT_LENGTH = 32 MB` existente.
- **Pantallas**: solo página de subir + reporte de resultado. Sin listado de archivos.

## Alcance

Una ruta `GET/POST /escaneos/subir`, un form, un servicio de guardado/matching, template de resultado, permiso, sidebar, config + volumen Docker, tests.

No incluye: borrado de JPGs, listado de archivos, deshacer marcado, procesamiento asíncrono, preview en dos pasos.

## Arquitectura

```
app/escaneos/
  __init__.py    # Blueprint 'escaneos', url_prefix='/escaneos'
                 #   GET/POST /escaneos/subir  (@permiso_requerido('escaneos.subir'))
  forms.py       # EscaneoForm:
                 #   SelectField 'anio'  — choices desde Folio.anioCert distinct, validado
                 #   MultipleFileField 'archivos' — solo FileRequired; SIN FileAllowed
                 #   (ver "Errores": un no-JPG no debe abortar el lote — el gate
                 #   único es NOMBRE_RE en el servicio)
app/services/escaneos.py   # guardar_y_matchear(archivos, anio) → dict reporte
app/templates/escaneos/subir.html
```

Integración:

- Registro del blueprint en `app/__init__.py` (bloque de imports/registro ~líneas 139-172).
- Permiso `'escaneos.subir': ('Subir escaneos', 'edit')` en `app/services/permisos.py` (catálogo `PERMISOS`).
- Link en `app/templates/components/sidebar.html` con `{% if puede('escaneos.subir') %}`, clase `active` por `'escaneos' in request.endpoint`.
- Config `SCANS_FOLDER` en `app/config.py` (Path del project root + `scans/` por defecto, overridable por env var).
- Volumen `./scans:/app/scans` en `docker-compose.yml` (servicio `app`).
- `scans/` en `.gitignore`.

## Data flow

1. `GET /escaneos/subir` → form con años disponibles (`select(Folio.anioCert).distinct()`).
2. `POST` con año + JPGs:
   - Validación WTForms (año en choices, FileRequired) y `MAX_CONTENT_LENGTH` (handler 413 existente); la validación de extensión vive en el servicio (ver Errores).
   - Por cada archivo:
     - **Parsear nombre**: `^(\d{1,10})\.(jpg|jpeg)$` case-insensitive, **estricto** — sin espacios, sin sufijos (`1234_copia.jpg` es inválido), máximo 10 dígitos porque `folios.folio` es Integer. No matchea → resultado "nombre inválido"; no se escribe.
     - **Guardar**: `<SCANS_FOLDER>/<anio>/<número>.jpg`, `Path.mkdir(parents=True, exist_ok=True)`, sobrescribe si existe. Falla de disco → resultado "error al guardar" para ese archivo; continúa con el resto.
     - **Match**: `Folio.anioCert == año AND Folio.folio == número`. Si hay filas: `escaneado=True` en todas + `log_audit(user_id, 'UPDATE', 'folios', id, antes, después)` por folio. Si no: resultado "sin coincidencia" (archivo ya guardado).
3. Renderiza `subir.html` con el reporte: tabla de archivos (nombre, resultado, folios marcados) + totales (marcados / sin coincidencia / inválidos / errores).

Todo o nada **no**: procesamiento por archivo; un fallo no aborta el lote.

## Errores

| Caso | Comportamiento |
|---|---|
| Extensión no jpg/jpeg | Rechazado, mensaje en reporte, continúa |
| Nombre sin número (`abc.jpg`) | "nombre inválido", no se escribe |
| Año sin folios en DB | Se guarda todo, reporta "sin coincidencia" |
| Error de disco | "error al guardar" por archivo, continúa |
| Request > 32 MB | 413 del handler existente |
| Sin permiso | `permiso_requerido` redirige (patrón existente) |

Auditoría: `log_audit` por folio marcado (patrón `app/folios/__init__.py:111`). Solo se auditan folios que cambian.

## Tests — `tests/test_escaneos.py`

Patrón: `tests/test_importar_centros.py` (multipart con `BytesIO`), fixtures de `tests/conftest.py` (`auth_client`, `make_user`, `make_folio`).

1. Sin login → redirect a `/auth/login`.
2. Sin permiso (`make_user('lectura','lectura')`) → redirect.
3. Subida OK: `SCANS_FOLDER` de test apunta a `tmp_path`; JPG `1234.jpg` con folio `(anio=2026, folio=1234)` → `escaneado=True`, archivo existe en `<tmp>/2026/1234.jpg`.
4. Dos tipos con mismo número en el año → ambos marcados.
5. Sin match → archivo guardado, respuesta contiene "sin coincidencia".
6. Nombre inválido (`abc.jpg`) → no se escribe nada, reporte "inválido".
7. Sobrescritura → segundo upload pisa el contenido del primero.
8. Multi-archivo mixto (2 con match, 1 sin, 1 inválido) → totales correctos.
9. Año distinto del folio → sin match (el año del form manda).

Nota: `TestConfig` necesitará `SCANS_FOLDER` apuntando a un tmp path por test (fixture `tmp_path`).

## Fórmulas / seguridad

- Solo se escriben archivos cuyo nombre matchea `^\d{1,10}\.(jpg|jpeg)$` → no hay path traversal (el nombre se reconstruye desde el número parseado, no se usa el filename original del cliente).
- `NOMBRE_RE` en el servicio es el gate único de extensión/nombre (el form no lleva `FileAllowed`: rechazar ahí abortaría el lote entero por un solo no-JPG, contra la tabla de Errores).
- Carpeta fuera de `app/static/` → no servible por HTTP.
