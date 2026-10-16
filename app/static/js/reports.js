(function () {
    const filterForm = document.getElementById('filterForm');
    const emptyState = document.getElementById('emptyState');
    const loadingSpinner = document.getElementById('loadingSpinner');
    const tableContainer = document.getElementById('tableContainer');
    const reportesBody = document.getElementById('reportesBody');
    const paginationContainer = document.getElementById('paginationContainer');
    const exportExcel = document.getElementById('exportExcel');
    const exportPdf = document.getElementById('exportPdf');
    const tableSearch = document.getElementById('tableSearch');

    let currentParams = '';

    // Todo dato que viene del servidor (nombre de tipo/centro/usuarios)
    // se inserta vía innerHTML: sin escapar sería XSS almacenado.
    function escapeHtml(v) {
        return String(v ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function buildParams(page) {
        const fd = new FormData(filterForm);
        const params = new URLSearchParams();
        if (fd.get('anioCert')) params.set('anioCert', fd.get('anioCert'));
        if (fd.get('tipoCert')) params.set('tipoCert', fd.get('tipoCert'));
        if (fd.get('centroId')) params.set('centroId', fd.get('centroId'));
        if (fd.get('estado')) params.set('estado', fd.get('estado'));
        if (page) params.set('page', page);
        return params;
    }

    function updateExportLinks(params) {
        const qs = params.toString();
        exportExcel.href = '/reportes/export/excel?' + qs;
        exportPdf.href = '/reportes/export/pdf?' + qs;
        exportExcel.style.display = '';
        exportPdf.style.display = '';
    }

    function updateStats(stats) {
        document.getElementById('statTotal').textContent = stats.total;
        document.getElementById('statDisponibles').textContent = stats.disponibles;
        document.getElementById('statEntregados').textContent = stats.entregados;
        document.getElementById('statDevueltos').textContent = stats.devueltos;
    }

    function renderRows(folios) {
        reportesBody.innerHTML = '';
        if (folios.length === 0) {
            reportesBody.innerHTML = '<tr><td colspan="12" class="text-center text-muted py-4">No hay folios para los filtros seleccionados</td></tr>';
            return;
        }
        const rows = folios.map(f => {
            const estadoBadge = f.nulo
                ? '<span class="badge bg-warning">Nulo</span>'
                : f.estado === 'disponible'
                    ? '<span class="badge bg-secondary">Disponible</span>'
                    : f.estado === 'entregado'
                        ? '<span class="badge bg-danger">Entregado</span>'
                        : f.estado === 'devuelto'
                            ? '<span class="badge bg-success">Devuelto</span>'
                            : '<span class="badge bg-secondary">' + escapeHtml(f.estado) + '</span>';
            // Solo #RRGGBB válido (el form lo valida igual); igual se escapa.
            const colorSeguro = /^#[0-9A-Fa-f]{6}$/.test(String(f.tipo_color || ''))
                ? escapeHtml(f.tipo_color) : '#6c757d';

            return '<tr>'
                + '<td class="fw-bold col-folio">' + escapeHtml(f.folio) + '</td>'
                + '<td><span class="badge" style="background-color:' + colorSeguro + '">' + escapeHtml(f.tipo_nombre) + '</span></td>'
                + '<td>' + escapeHtml(f.anioCert) + '</td>'
                + '<td>' + (f.centro ? escapeHtml(f.centro) : '<span class="text-muted">-</span>') + '</td>'
                + '<td>' + estadoBadge + '</td>'
                + '<td><i class="fas ' + (f.digitado ? 'fa-check text-success' : 'fa-times text-muted') + '"></i></td>'
                + '<td><i class="fas ' + (f.escaneado ? 'fa-check text-success' : 'fa-times text-muted') + '"></i></td>'
                + '<td><i class="fas ' + (f.nulo ? 'fa-check text-success' : 'fa-times text-muted') + '"></i></td>'
                + '<td>' + (f.fechaEntrega ? escapeHtml(f.fechaEntrega) : '<span class="text-muted">-</span>') + '</td>'
                + '<td>' + (f.entregado_por ? '<span class="badge bg-primary">' + escapeHtml(f.entregado_por) + '</span>' : '<span class="text-muted">-</span>') + '</td>'
                + '<td>' + (f.fechaDevolucion ? escapeHtml(f.fechaDevolucion) : '<span class="text-muted">-</span>') + '</td>'
                + '<td>' + (f.recibido_por ? '<span class="badge bg-success">' + escapeHtml(f.recibido_por) + '</span>' : '<span class="text-muted">-</span>') + '</td>'
                + '</tr>';
        });
        reportesBody.innerHTML = rows.join('');
    }

    function renderPagination(pag, params) {
        if (pag.pages <= 1) {
            paginationContainer.innerHTML = '';
            return;
        }

        let html = '<nav class="mt-3"><ul class="pagination justify-content-center pagination-sm">';

        html += '<li class="page-item' + (pag.has_prev ? '' : ' disabled') + '">'
            + '<a class="page-link" href="#" data-page="' + (pag.prev_num || 1) + '">'
            + '<i class="fas fa-chevron-left"></i></a></li>';

        const range = 2;
        const start = Math.max(1, pag.page - range);
        const end = Math.min(pag.pages, pag.page + range);

        if (start > 1) {
            html += '<li class="page-item"><a class="page-link" href="#" data-page="1">1</a></li>';
            if (start > 2) html += '<li class="page-item disabled"><span class="page-link">...</span></li>';
        }

        for (let i = start; i <= end; i++) {
            html += '<li class="page-item' + (i === pag.page ? ' active' : '') + '">'
                + '<a class="page-link" href="#" data-page="' + i + '">' + i + '</a></li>';
        }

        if (end < pag.pages) {
            if (end < pag.pages - 1) html += '<li class="page-item disabled"><span class="page-link">...</span></li>';
            html += '<li class="page-item"><a class="page-link" href="#" data-page="' + pag.pages + '">' + pag.pages + '</a></li>';
        }

        html += '<li class="page-item' + (pag.has_next ? '' : ' disabled') + '">'
            + '<a class="page-link" href="#" data-page="' + (pag.next_num || pag.pages) + '">'
            + '<i class="fas fa-chevron-right"></i></a></li>';

        html += '</ul></nav>';
        paginationContainer.innerHTML = html;

        paginationContainer.querySelectorAll('.page-link[data-page]').forEach(link => {
            link.addEventListener('click', function (e) {
                e.preventDefault();
                const page = this.getAttribute('data-page');
                loadData(page);
            });
        });
    }

    function loadData(page) {
        const params = buildParams(page);
        currentParams = params.toString();

        // Dejar los filtros en la URL: F5 y el botón "atrás" conservan lo
        // elegido (el server pinta los selects con selected desde request.args).
        const qs = params.toString();
        history.replaceState(null, '', qs ? '?' + qs : location.pathname);

        emptyState.style.display = 'none';
        loadingSpinner.style.display = '';
        tableContainer.style.display = 'none';
        paginationContainer.innerHTML = '';
        tableSearch.value = '';

        fetch('/reportes/api/data?' + params.toString())
            .then(r => {
                // Sin !r.ok, un 429/500 caía en r.json() y se mostraba el
                // emptyState genérico como si no hubiera resultados.
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.json();
            })
            .then(data => {
                loadingSpinner.style.display = 'none';
                tableContainer.style.display = '';

                updateStats(data.stats);
                renderRows(data.folios);
                renderPagination(data.pagination, params);
                updateExportLinks(params);
            })
            .catch(err => {
                loadingSpinner.style.display = 'none';
                tableContainer.style.display = 'none';
                paginationContainer.innerHTML = '';
                // Error visible en vez del emptyState de "use los filtros",
                // y la fila de error no queda escondida dentro de la tabla.
                emptyState.innerHTML = '<i class="fas fa-exclamation-triangle fa-3x text-danger mb-3"></i>'
                    + '<p class="text-danger mb-1 fw-semibold">Error al cargar los datos</p>'
                    + '<p class="text-muted small mb-0">' + escapeHtml(err && err.message) + '</p>';
                emptyState.style.display = '';
            });
    }

    filterForm.addEventListener('submit', function (e) {
        e.preventDefault();
        loadData(1);
    });

    tableSearch.addEventListener('input', function () {
        const text = this.value.toLowerCase();
        reportesBody.querySelectorAll('tr').forEach(row => {
            row.style.display = row.textContent.toLowerCase().includes(text) ? '' : 'none';
        });
    });

    // F5 / botón atrás con filtros en la URL: los selects ya vienen marcados
    // desde el server; hay que recargar la tabla y los stats.
    if (window.location.search) loadData(1);
})();
