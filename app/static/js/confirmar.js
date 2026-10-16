// Confirmación de acciones destructivas con SweetAlert2.
//
// Uso en plantillas:
//   <form method="POST" action="…" data-confirm data-title="¿…" data-icon="danger">
// `data-icon` es opcional (default 'warning'); el texto original vive en
// `data-title`. `data-text` (opcional) añade una descripción de la acción
// bajo el título. `data-confirm-style="danger"` pinta el botón de confirmar
// de rojo (se infiere también de data-icon="danger"). Al confirmar se envía
// el form con submit() nativo, que no vuelve a disparar este listener.
document.addEventListener('submit', function (evento) {
    const form = evento.target;
    if (!(form instanceof HTMLFormElement) || !form.hasAttribute('data-confirm')) {
        return;
    }
    // SweetAlert2 vino por CDN: si no cargó, no bloquear el envío — el form
    // se envía nativamente sin diálogo (mejor que dejar el botón muerto).
    if (typeof Swal === 'undefined') return;
    evento.preventDefault();
    const icono = form.getAttribute('data-icon') || 'warning';
    const destructiva = icono === 'danger' ||
        form.getAttribute('data-confirm-style') === 'danger';
    Swal.fire({
        title: form.getAttribute('data-title') || '¿Está seguro?',
        text: form.getAttribute('data-text') || undefined,
        icon: icono,
        showCancelButton: true,
        confirmButtonText: 'Confirmar',
        cancelButtonText: 'Cancelar',
        reverseButtons: true,
        focusCancel: true,
        customClass: {
            confirmButton: destructiva ? 'swal-confirm-danger' : '',
        },
    }).then(function (resultado) {
        if (!resultado.isConfirmed) return;
        // Feedback anti doble submit también en forms sin data-loading: el
        // submit nativo no vuelve a disparar listeners de 'submit'.
        const btn = form.querySelector('[type="submit"]');
        if (btn && !btn.disabled) {
            const spin = document.createElement('span');
            spin.className = 'spinner-border spinner-border-sm me-1 spinner-envio';
            spin.setAttribute('role', 'status');
            spin.setAttribute('aria-hidden', 'true');
            if (btn.tagName === 'INPUT') {
                btn.dataset.originalValue = btn.value;
                btn.value = 'Enviando…';
                btn.disabled = true;
                btn.parentNode.insertBefore(spin, btn);
            } else {
                btn.dataset.originalHtml = btn.innerHTML;
                btn.disabled = true;
                btn.insertBefore(spin, btn.firstChild);
            }
            // Back tras el POST (bfcache): devolver el botón a su estado.
            window.addEventListener('pageshow', function restaurar(ev) {
                if (!ev.persisted) return;
                window.removeEventListener('pageshow', restaurar);
                btn.disabled = false;
                if (btn.tagName === 'INPUT' && btn.dataset.originalValue !== undefined) {
                    btn.value = btn.dataset.originalValue;
                } else if (btn.dataset.originalHtml !== undefined) {
                    btn.innerHTML = btn.dataset.originalHtml;
                }
                const viejo = form.querySelector('.spinner-envio');
                if (viejo) viejo.remove();
            });
        }
        HTMLFormElement.prototype.submit.call(form);
    });
});
