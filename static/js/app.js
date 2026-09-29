/**
 * Comportements transverses du dashboard.
 *
 * Quatre responsabilités, et pas une de plus : thème, modales, confirmations,
 * notifications. Tout le reste appartient aux pages.
 *
 * Deux fonctions ici (`toast`, `fetchJSON`) remplacent `showToast`/`apiCall`,
 * qui existaient dans base.html et n'étaient appelées nulle part.
 */
(function () {
  'use strict';

  // =========================================================================
  // Thème
  // =========================================================================
  // Trois états : 'light', 'dark', ou absent (= suivre le système). Un simple
  // bouton bascule à deux positions rendrait `prefers-color-scheme`
  // inatteignable dès le premier clic.
  const THEME_KEY = 'tm20-theme';

  function storedTheme() {
    try { return localStorage.getItem(THEME_KEY); } catch (e) { return null; }
  }

  function applyTheme(value) {
    const dark = value === 'dark' ||
      (!value && window.matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.classList.toggle('dark', dark);
    document.querySelectorAll('[data-theme-option]').forEach((el) => {
      el.setAttribute('aria-pressed', String(el.dataset.themeOption === (value || 'system')));
    });
  }

  function setTheme(value) {
    try {
      if (value === 'system') localStorage.removeItem(THEME_KEY);
      else localStorage.setItem(THEME_KEY, value);
    } catch (e) { /* navigation privée : le thème vaut pour la session */ }
    applyTheme(value === 'system' ? null : value);
  }

  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (!storedTheme()) applyTheme(null);
  });

  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-theme-option]');
    if (btn) setTheme(btn.dataset.themeOption);
  });

  // =========================================================================
  // Modales
  // =========================================================================
  // Un seul écouteur délégué pour toute la page. Remplace à la fois le
  // mini-contrôleur dupliqué et les `onclick="...classList.add('hidden')"`
  // écrits en dur dans les gabarits.
  let lastFocused = null;

  function openModal(id) {
    const modal = document.getElementById(id);
    if (!modal) return;
    lastFocused = document.activeElement;
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    const target = modal.querySelector('[data-autofocus]') ||
      modal.querySelector('input, select, textarea, button');
    if (target) target.focus();
  }

  function closeModal(modal) {
    if (!modal) return;
    modal.classList.add('hidden');
    document.body.style.overflow = '';
    // Rendre le focus à son point de départ : sans ça, la navigation au
    // clavier repart du haut du document après chaque fermeture.
    if (lastFocused && document.contains(lastFocused)) lastFocused.focus();
    lastFocused = null;
  }

  document.addEventListener('click', (e) => {
    const opener = e.target.closest('[data-open-modal]');
    if (opener) { e.preventDefault(); openModal(opener.dataset.openModal); return; }

    const closer = e.target.closest('[data-close-modal]');
    if (closer) { e.preventDefault(); closeModal(closer.closest('[data-modal]') ||
      document.getElementById(closer.dataset.closeModal)); return; }

    const backdrop = e.target.closest('[data-modal-backdrop]');
    if (backdrop) closeModal(backdrop.closest('[data-modal]'));
  });

  document.addEventListener('keydown', (e) => {
    const modal = document.querySelector('[data-modal]:not(.hidden)');
    if (!modal) return;

    if (e.key === 'Escape') { closeModal(modal); return; }

    // Piège à focus : sans lui, la tabulation sort de la modale et parcourt
    // la page qui est pourtant masquée par le voile.
    if (e.key !== 'Tab') return;
    const focusable = modal.querySelectorAll(
      'a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });

  // =========================================================================
  // Confirmations
  // =========================================================================
  // `data-confirm` remplace les `confirm()` natifs. `data-confirm-challenge`
  // exige de recopier une valeur (le n° de série d'un terminal) : réservé aux
  // actions dont on ne revient pas.
  document.addEventListener('submit', (e) => {
    const form = e.target;
    const message = form.dataset.confirm;
    if (!message || form.dataset.confirmed === 'true') return;
    e.preventDefault();

    const challenge = form.dataset.confirmChallenge;
    let ok;
    if (challenge) {
      const answer = window.prompt(`${message}\n\nPour confirmer, saisissez : ${challenge}`);
      ok = answer !== null && answer.trim() === challenge;
      if (answer !== null && !ok) toast('La saisie ne correspond pas. Action annulée.', 'warning');
    } else {
      ok = window.confirm(message);
    }
    if (ok) { form.dataset.confirmed = 'true'; form.submit(); }
  });

  // =========================================================================
  // Toasts
  // =========================================================================
  const TONES = {
    success: 'bg-success-subtle text-success-text border-success/30',
    error:   'bg-danger-subtle text-danger-text border-danger/30',
    danger:  'bg-danger-subtle text-danger-text border-danger/30',
    warning: 'bg-warning-subtle text-warning-text border-warning/30',
    info:    'bg-info-subtle text-info-text border-info/30',
  };

  function toast(message, tone = 'info', delay = 4000) {
    const host = document.getElementById('toast-host');
    if (!host) return;

    const el = document.createElement('div');
    el.className =
      'pointer-events-auto max-w-sm rounded-lg border px-4 py-3 text-sm shadow-2 ' +
      'translate-y-2 opacity-0 ' + (TONES[tone] || TONES.info);
    // Transition sur des propriétés composables uniquement, et jamais
    // `transition: all`.
    el.style.transitionProperty = 'opacity, transform';
    el.style.transitionDuration = '200ms';
    el.style.transitionTimingFunction = 'cubic-bezier(0.2, 0, 0, 1)';
    el.textContent = message;
    host.appendChild(el);

    requestAnimationFrame(() => {
      el.classList.remove('translate-y-2', 'opacity-0');
    });

    const remove = () => {
      // La sortie est plus courte que l'entrée : un toast qui s'attarde donne
      // l'impression d'une interface qui traîne.
      el.style.transitionDuration = '140ms';
      el.classList.add('opacity-0', 'translate-y-2');
      el.addEventListener('transitionend', () => el.remove(), { once: true });
    };
    setTimeout(remove, delay);
    el.addEventListener('click', remove);
  }

  // =========================================================================
  // Requêtes JSON
  // =========================================================================
  function csrfToken() {
    const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  async function fetchJSON(url, { method = 'GET', data = null, ...rest } = {}) {
    const response = await fetch(url, {
      method,
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken(),
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: data ? JSON.stringify(data) : null,
      ...rest,
    });

    // Une session expirée renvoie une redirection vers la page de connexion :
    // `response.json()` échouerait sur du HTML. On le traite explicitement.
    if (response.status === 401 || response.redirected) {
      toast('Session expirée, reconnexion nécessaire.', 'warning');
      window.location.href = '/login/?next=' + encodeURIComponent(location.pathname);
      throw new Error('non authentifié');
    }

    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw Object.assign(new Error(payload.error || `Erreur ${response.status}`), { payload });
    }
    return payload;
  }

  window.tm20 = { toast, fetchJSON, setTheme, openModal, closeModal };

  // Synchronise l'état visuel des boutons de thème au chargement.
  applyTheme(storedTheme());
})();
