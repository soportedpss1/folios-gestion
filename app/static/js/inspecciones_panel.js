// Panel de corrección desde Inspecciones: modal que reusa los endpoints
// dueños en modo JSON (Accept: application/json). Ver spec:
// docs/superpowers/specs/2026-10-28-inspecciones-correccion-panel-design.md
(function () {
    'use strict';

    const MENSAJE_FALLO = 'No se pudo guardar. Intente de nuevo.';
    const MENSAJE_EXITO = 'Corregido exitosamente.';
    const JSON_HEADERS = { 'Accept': 'application/json' };

    const form = document.getElementById('panel-form');
    if (!form) return; // página sin panel (p. ej. índice)

    const campos = document.getElementById('panel-campos');
    const cajaError = document.getElementById('panel-error');
    const titulo = document.getElementById('panel-titulo');
    const modalEl = document.getElementById('modal-corregir');
    let guardando = false;

    function toast(mensaje, tipo) {
        if (window.AppToast && typeof AppToast.mostrar === 'function') {
            AppToast.mostrar(mensaje, tipo);
        }
    }

    function limpiarErrores() {
        cajaError.textContent = '';
        cajaError.classList.add('d-none');
        campos.querySelectorAll('.is-invalid').forEach(
            (el) => el.classList.remove('is-invalid'));
        campos.querySelectorAll('.invalid-feedback').forEach(
            (el) => el.remove());
    }

    function marcarErrorCampo(campo, mensaje) {
        const input = campos.querySelector('[name="' + campo + '"]');
        if (!input) return;
        input.classList.add('is-invalid');
        const feedback = document.createElement('div');
        feedback.className = 'invalid-feedback';
        feedback.textContent = mensaje;
        input.insertAdjacentElement('afterend', feedback);
    }

    function initFechas() {
        // Los inputs de fecha llegan por fetch: flatpickr ya corrió en la
        // carga de la página, hay que inicializar los nuevos.
        if (typeof flatpickr === 'undefined') return;
        campos.querySelectorAll('.flatpickr:not(.flatpickr-input)').forEach(
            (el) => flatpickr(el, { locale: 'es', dateFormat: 'd/m/Y' }));
    }

    function abrir(url, tituloBtn) {
        limpiarErrores();
        titulo.textContent = tituloBtn || 'Corregir';
        fetch(url, { headers: JSON_HEADERS })
            .then((resp) => {
                if (!resp.ok || !isJson(resp)) throw new Error('get');
                return resp.json();
            })
            .then((data) => {
                campos.innerHTML = data.campos_html;
                form.action = url;
                initFechas();
                bootstrap.Modal.getOrCreateInstance(modalEl).show();
            })
            .catch(() => toast(MENSAJE_FALLO, 'danger'));
    }

    function isJson(resp) {
        return (resp.headers.get('content-type') || '')
            .includes('application/json');
    }

    function manejarErrorRespuesta(resp) {
        if (!isJson(resp)) {
            // p. ej. 302/HTML: la sesión o el permiso no están para esto
            toast(MENSAJE_FALLO, 'danger');
            return;
        }
        resp.json().then((data) => {
            limpiarErrores();
            if (data.errores) {
                Object.keys(data.errores).forEach(
                    (campo) => marcarErrorCampo(campo, data.errores[campo]));
            }
            if (data.error) {
                cajaError.textContent = data.error;
                cajaError.classList.remove('d-none');
            }
            if (!data.errores && !data.error) {
                toast(MENSAJE_FALLO, 'danger');
            }
        }).catch(() => toast(MENSAJE_FALLO, 'danger'));
    }

    document.querySelectorAll('[data-panel]').forEach((btn) => {
        btn.addEventListener('click', () => abrir(btn.dataset.url,
                                                  btn.dataset.titulo));
    });

    form.addEventListener('submit', (ev) => {
        ev.preventDefault();
        if (guardando) return;
        guardando = true;
        fetch(form.action, {
            method: 'POST',
            body: new FormData(form),
            headers: JSON_HEADERS,
        }).then((resp) => {
            guardando = false;
            if (resp.ok && isJson(resp)) {
                bootstrap.Modal.getOrCreateInstance(modalEl).hide();
                toast(MENSAJE_EXITO, 'success');
                location.reload();
                return;
            }
            manejarErrorRespuesta(resp);
        }).catch(() => {
            guardando = false;
            toast(MENSAJE_FALLO, 'danger');
        });
    });
})();
