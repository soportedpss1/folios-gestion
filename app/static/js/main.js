document.addEventListener('DOMContentLoaded', function() {
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
    if (csrfToken) {
        const originalFetch = window.fetch;
        window.fetch = function(url, options = {}) {
            options.headers = options.headers || {};
            if (!(options.body instanceof FormData)) {
                options.headers['X-CSRFToken'] = csrfToken;
            }
            return originalFetch(url, options);
        };
    }

    // Tema claro/oscuro (persistido; el script del <head> evita el destello).
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        const aplicarTema = function(tema) {
            document.documentElement.setAttribute('data-bs-theme', tema);
            try { localStorage.setItem('folios-tema', tema); } catch (e) { /* modo privado */ }
            const oscuro = tema === 'dark';
            themeToggle.setAttribute('aria-pressed', String(oscuro));
            themeToggle.setAttribute('aria-label', oscuro ? 'Cambiar a tema claro' : 'Cambiar a tema oscuro');
            const icono = themeToggle.querySelector('i');
            if (icono) icono.className = oscuro ? 'fas fa-sun' : 'fas fa-moon';
        };
        aplicarTema(document.documentElement.getAttribute('data-bs-theme') || 'light');
        themeToggle.addEventListener('click', function() {
            const oscuroActual = document.documentElement.getAttribute('data-bs-theme') === 'dark';
            aplicarTema(oscuroActual ? 'light' : 'dark');
        });
    }

    const sidebar = document.getElementById('sidebar-wrapper');
    const pageContent = document.getElementById('page-content-wrapper');
    const toggleBtn = document.getElementById('toggle-sidebar');

    if (toggleBtn && sidebar) {
        // Backdrop táctil para cerrar el menú en móvil (inyectado una sola vez).
        const backdrop = document.createElement('div');
        backdrop.className = 'sidebar-backdrop';
        backdrop.addEventListener('click', () => alternarSidebar(false));
        document.body.appendChild(backdrop);

        const esMovil = () => window.innerWidth <= 768;

        function alternarSidebar(abrir) {
            if (esMovil()) {
                sidebar.classList.toggle('show', abrir);
                backdrop.classList.toggle('show', abrir);
            } else {
                sidebar.classList.toggle('collapsed', !abrir);
                pageContent.classList.toggle('expanded', !abrir);
            }
            const abierto = esMovil()
                ? sidebar.classList.contains('show')
                : !sidebar.classList.contains('collapsed');
            toggleBtn.setAttribute('aria-expanded', String(abierto));
        }

        toggleBtn.addEventListener('click', () => {
            if (esMovil()) {
                alternarSidebar(!sidebar.classList.contains('show'));
            } else {
                alternarSidebar(sidebar.classList.contains('collapsed'));
            }
        });

        // Escape cierra el menú móvil.
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && esMovil() && sidebar.classList.contains('show')) {
                alternarSidebar(false);
                toggleBtn.focus();
            }
        });

        // Estado inicial correcto del aria-expanded (sidebar abierto en desktop).
        toggleBtn.setAttribute('aria-expanded', String(
            esMovil() ? sidebar.classList.contains('show') : !sidebar.classList.contains('collapsed')
        ));

        // Al pasar a desktop se limpia el estado móvil.
        window.addEventListener('resize', function() {
            if (!esMovil()) {
                sidebar.classList.remove('show');
                backdrop.classList.remove('show');
                const abierto = !sidebar.classList.contains('collapsed');
                toggleBtn.setAttribute('aria-expanded', String(abierto));
            }
        });
    }

    // Acceso rápido a mostrar/ocultar contraseña (login).
    const togglePw = document.getElementById('toggle-password');
    if (togglePw) {
        togglePw.addEventListener('click', function() {
            const campo = document.getElementById(togglePw.dataset.target);
            if (!campo) return;
            const visible = campo.type === 'text';
            campo.type = visible ? 'password' : 'text';
            togglePw.setAttribute('aria-pressed', String(!visible));
            togglePw.setAttribute('aria-label', visible ? 'Mostrar contraseña' : 'Ocultar contraseña');
            const icono = togglePw.querySelector('i');
            if (icono) icono.className = visible ? 'fas fa-eye' : 'fas fa-eye-slash';
        });
    }

    // Antidoble-submit: <form data-loading> deshabilita el botón y muestra
    // spinner mientras el POST está en vuelo. Soporta <input type="submit">
    // (WTForms) y <button>, y restaura el estado si el navegador restaura la
    // página desde bfcache (Back tras un POST).
    document.querySelectorAll('form[data-loading]').forEach(function(form) {
        const btn = form.querySelector('[type="submit"]');

        function restaurar() {
            form.dataset.loadingBlocked = '0';
            if (!btn) return;
            btn.disabled = false;
            if (btn.tagName === 'INPUT') {
                if (btn.dataset.originalValue !== undefined) btn.value = btn.dataset.originalValue;
            } else if (btn.dataset.originalHtml !== undefined) {
                btn.innerHTML = btn.dataset.originalHtml;
            }
            const spin = form.querySelector('.spinner-envio');
            if (spin) spin.remove();
        }

        form.addEventListener('submit', function(e) {
            if (form.dataset.loadingBlocked === '1') {
                e.preventDefault();
                return;
            }
            form.dataset.loadingBlocked = '1';
            if (!btn) return;
            const spin = document.createElement('span');
            spin.className = 'spinner-border spinner-border-sm me-1 spinner-envio';
            spin.setAttribute('role', 'status');
            spin.setAttribute('aria-hidden', 'true');
            if (btn.tagName === 'INPUT') {
                // Un <input> no tiene innerHTML: texto vía value + spinner al lado.
                btn.dataset.originalValue = btn.value;
                btn.value = 'Enviando…';
                btn.disabled = true;
                btn.parentNode.insertBefore(spin, btn);
            } else {
                btn.dataset.originalHtml = btn.innerHTML;
                btn.disabled = true;
                btn.insertBefore(spin, btn.firstChild);
            }
        });

        // Back/Forward tras enviar: el DOM vuelve con el botón "Enviando…" y
        // bloqueado; hay que destrabar el formulario.
        window.addEventListener('pageshow', function(ev) {
            if (ev.persisted) restaurar();
        });
    });

    // aria-current en el enlace activo del sidebar (evita repetirlo en cada li).
    document.querySelectorAll('.sidebar .nav-link.active').forEach(function(enlace) {
        enlace.setAttribute('aria-current', 'page');
    });

    // Tarjetas KPI: accesibles por teclado (Enter/Espacio = clic).
    document.querySelectorAll('.kpi-card').forEach(function(card) {
        card.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
                e.preventDefault();
                card.click();
            }
        });
    });

    const tooltips = document.querySelectorAll('[title]');
    tooltips.forEach(el => {
        new bootstrap.Tooltip(el);
    });

    // Cuenta atrás de la próxima sincronización automática (navbar).
    const timerText = document.getElementById('sync-timer-text');
    const timerBox = document.getElementById('sync-timer');
    if (timerText) {
        let proximoMs = null;
        let activo = false;
        let atrasado = false;
        let refetchMs = 60000;
        let tickTimer = null;
        let refetchTimer = null;

        function pintar() {
            if (!activo) {
                timerText.textContent = '--:--';
                timerBox.setAttribute('title', 'Sincronización automática desactivada');
                return;
            }
            if (proximoMs === null) {
                timerText.textContent = 'ahora';
                timerBox.setAttribute('title', 'Sincronización automática: pendiente de ejecutar');
                return;
            }
            const rest = proximoMs - Date.now();
            if (rest <= 0) {
                timerText.textContent = atrasado ? 'pendiente' : 'ahora';
                timerBox.setAttribute('title', 'Sincronización automática: pendiente de ejecutar');
                return;
            }
            const seg = Math.floor(rest / 1000);
            const d = Math.floor(seg / 86400);
            const h = Math.floor((seg % 86400) / 3600);
            const m = Math.floor((seg % 3600) / 60);
            const s = seg % 60;
            const hm = String(h).padStart(2, '0') + ':' +
                String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
            timerText.textContent = d > 0 ? d + 'd ' + hm : hm;
            timerBox.setAttribute('title', 'Próxima sincronización automática');
        }

        function programar() {
            clearInterval(tickTimer);
            clearInterval(refetchTimer);
            tickTimer = setInterval(pintar, 1000);
            refetchTimer = setInterval(cargar, refetchMs);
        }

        function cargar() {
            fetch('/sincronizacion/api/proxima')
                .then(r => (r.ok ? r.json() : Promise.reject()))
                .then(data => {
                    activo = data.activo;
                    atrasado = data.atrasado;
                    proximoMs = data.proximo
                        ? Date.parse(data.proximo)
                        : null;
                    // Inmediato/atrasado: el worker puede correr en su próximo
                    // tick (≤60 s); consultar más seguido hasta que se mueva.
                    const eraPendiente = proximoMs === null || atrasado ||
                        (proximoMs !== null && proximoMs - Date.now() <= 0);
                    refetchMs = eraPendiente ? 15000 : 60000;
                    pintar();
                    programar();
                })
                .catch(() => {
                    // Sin red: conservar el último valor y reintentar.
                    refetchMs = 60000;
                    programar();
                });
        }

        cargar();
    }
});
