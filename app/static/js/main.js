// ---------- Toasts (mensajes flash + feedback AJAX) ----------
// Los toasts del servidor llegan en #flash-toasts (components/flash.html);
// este módulo aplica auto-dismiss, pausa al hover/foco y control de cola.
// Uso desde plantillas: AppToast.mostrar('Mensaje', 'success'|'danger'|…).
window.AppToast = (function () {
    'use strict';

    const ICONOS = {
        success: 'fa-check-circle',
        danger: 'fa-exclamation-circle',
        warning: 'fa-exclamation-triangle',
        info: 'fa-info-circle',
    };
    // danger (errores/permisos) queda 10s; el resto 4s.
    const DURACION = { danger: 10000 };
    const DURACION_DEFECTO = 4000;
    const MAX_VISIBLE = 4;
    const RETRASO_CIERRE = 200; // ms de fade-out antes de retirar del DOM

    const estado = new Map(); // toast -> {restante, inicio, id}
    const cola = [];
    const sinMovimiento = window.matchMedia('(prefers-reduced-motion: reduce)');

    function contenedor() {
        let cont = document.getElementById('flash-toasts');
        if (!cont) {
            cont = document.createElement('div');
            cont.className = 'toast-container';
            cont.id = 'flash-toasts';
            document.body.appendChild(cont);
        }
        return cont;
    }

    function visibles() {
        return contenedor().querySelectorAll(
            '.app-toast:not(.en-cola):not(.closing)'
        ).length;
    }

    function duracionDe(toast) {
        const ms = parseInt(toast.dataset.duracion, 10);
        return Number.isFinite(ms) ? ms : DURACION_DEFECTO;
    }

    function programar(toast) {
        const est = estado.get(toast) || {};
        clearTimeout(est.id);
        if (est.restante === undefined || est.restante === null) {
            est.restante = duracionDe(toast);
        }
        est.inicio = Date.now();
        est.id = setTimeout(() => cerrar(toast), est.restante);
        estado.set(toast, est);
    }

    function pausar(toast) {
        const est = estado.get(toast);
        if (!est || !est.id) return;
        clearTimeout(est.id);
        est.id = null;
        est.restante = Math.max(0, est.restante - (Date.now() - est.inicio));
    }

    function reanudar(toast) {
        const est = estado.get(toast);
        if (!est || est.id) return;
        programar(toast); // conserva el tiempo restante
    }

    function cerrar(toast) {
        const est = estado.get(toast);
        if (est) {
            clearTimeout(est.id);
            estado.delete(toast);
        }
        toast.classList.add('closing');
        setTimeout(() => {
            toast.remove();
            drenar();
        }, sinMovimiento.matches ? 0 : RETRASO_CIERRE);
    }

    function encolar(toast) {
        cola.push(toast);
        toast.classList.add('en-cola');
    }

    function drenar() {
        while (cola.length && visibles() < MAX_VISIBLE) {
            const toast = cola.shift();
            if (!toast.isConnected) continue;
            toast.classList.remove('en-cola');
            vigilar(toast);
            programar(toast);
        }
    }

    function vigilar(toast) {
        toast.addEventListener('mouseenter', () => pausar(toast));
        toast.addEventListener('mouseleave', () => reanudar(toast));
        toast.addEventListener('focusin', () => pausar(toast));
        toast.addEventListener('focusout', () => reanudar(toast));
        const btn = toast.querySelector('.app-toast-close');
        if (btn && !btn.dataset.listo) {
            btn.dataset.listo = '1';
            btn.addEventListener('click', () => cerrar(toast));
        }
    }

    function crear(mensaje, categoria) {
        if (!ICONOS[categoria]) categoria = 'info';
        const toast = document.createElement('div');
        toast.className = 'app-toast app-toast-' + categoria;
        toast.setAttribute('role', 'alert');
        toast.setAttribute('aria-live', categoria === 'danger' ? 'assertive' : 'polite');
        toast.dataset.duracion = String(DURACION[categoria] || DURACION_DEFECTO);

        const icono = document.createElement('i');
        icono.className = 'fas ' + ICONOS[categoria] + ' app-toast-icon';
        icono.setAttribute('aria-hidden', 'true');

        const texto = document.createElement('span');
        texto.className = 'app-toast-msg';
        texto.textContent = mensaje;

        const cerrarBtn = document.createElement('button');
        cerrarBtn.type = 'button';
        cerrarBtn.className = 'app-toast-close';
        cerrarBtn.setAttribute('aria-label', 'Cerrar aviso');
        const equis = document.createElement('i');
        equis.className = 'fas fa-xmark';
        equis.setAttribute('aria-hidden', 'true');
        cerrarBtn.appendChild(equis);
        // El listener lo agrega vigilar() (evita duplicados).

        toast.append(icono, texto, cerrarBtn);
        return toast;
    }

    function mostrar(mensaje, categoria) {
        const toast = crear(mensaje, categoria);
        contenedor().appendChild(toast);
        vigilar(toast);
        if (visibles() > MAX_VISIBLE) {
            encolar(toast);
        } else {
            programar(toast);
        }
        return toast;
    }

    // Los toasts renderizados por el servidor (redirect tras POST) se activan aquí.
    function iniciar() {
        const cont = document.getElementById('flash-toasts');
        if (!cont) return;
        cont.querySelectorAll('.app-toast').forEach((toast, indice) => {
            vigilar(toast);
            if (indice >= MAX_VISIBLE) {
                encolar(toast);
            } else {
                programar(toast);
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', iniciar);
    } else {
        iniciar();
    }

    return { mostrar: mostrar, cerrar: cerrar };
})();

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
