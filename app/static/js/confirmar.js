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
        if (resultado.isConfirmed) {
            HTMLFormElement.prototype.submit.call(form);
        }
    });
});
