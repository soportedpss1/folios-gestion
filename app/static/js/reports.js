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
                            : '<span class="badge bg-secondary">' + f.estado + '</span>';

            return '<tr>'
                + '<td class="fw-bold col-folio">' + f.folio + '</td>'
                + '<td><span class="badge" style="background-color:' + f.tipo_color + '">' + f.tipo_nombre + '</span></td>'
                + '<td>' + f.anioCert + '</td>'
                + '<td>' + (f.centro || '<span class="text-muted">-</span>') + '</td>'
                + '<td>' + estadoBadge + '</td>'
                + '<td><i class="fas ' + (f.digitado ? 'fa-check text-success' : 'fa-times text-muted') + '"></i></td>'
                + '<td><i class="fas ' + (f.escaneado ? 'fa-check text-success' : 'fa-times text-muted') + '"></i></td>'
                + '<td><i class="fas ' + (f.nulo ? 'fa-check text-success' : 'fa-times text-muted') + '"></i></td>'
                + '<td>' + (f.fechaEntrega || '<span class="text-muted">-</span>') + '</td>'
                + '<td>' + (f.entregado_por ? '<span class="badge bg-primary">' + f.entregado_por + '</span>' : '<span class="text-muted">-</span>') + '</td>'
                + '<td>' + (f.fechaDevolucion || '<span class="text-muted">-</span>') + '</td>'
                + '<td>' + (f.recibido_por ? '<span class="badge bg-success">' + f.recibido_por + '</span>' : '<span class="text-muted">-</span>') + '</td>'
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

        emptyState.style.display = 'none';
        loadingSpinner.style.display = '';
        tableContainer.style.display = 'none';
        paginationContainer.innerHTML = '';
        tableSearch.value = '';

        fetch('/reportes/api/data?' + params.toString())
            .then(r => r.json())
            .then(data => {
                loadingSpinner.style.display = 'none';
                tableContainer.style.display = '';

                updateStats(data.stats);
                renderRows(data.folios);
                renderPagination(data.pagination, params);
                updateExportLinks(params);
            })
            .catch(() => {
                loadingSpinner.style.display = 'none';
                emptyState.style.display = '';
                reportesBody.innerHTML = '<tr><td colspan="12" class="text-center text-danger py-4">Error al cargar datos</td></tr>';
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
})();
