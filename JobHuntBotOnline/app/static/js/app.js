(() => {
  'use strict';

  const sidebar = document.querySelector('#sidebar');
  const sidebarToggle = document.querySelector('[data-sidebar-toggle]');
  if (sidebar && sidebarToggle) {
    sidebarToggle.addEventListener('click', () => {
      const open = sidebar.classList.toggle('open');
      sidebarToggle.setAttribute('aria-expanded', String(open));
    });
    document.addEventListener('click', (event) => {
      if (sidebar.classList.contains('open') && !sidebar.contains(event.target) && !sidebarToggle.contains(event.target)) {
        sidebar.classList.remove('open');
        sidebarToggle.setAttribute('aria-expanded', 'false');
      }
    });
  }

  document.querySelectorAll('[data-dismiss]').forEach((button) => {
    button.addEventListener('click', () => button.closest('.flash')?.remove());
  });

  document.querySelectorAll('form[data-confirm]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      const message = form.dataset.confirm || '确定继续吗？';
      if (!window.confirm(message)) event.preventDefault();
    });
  });

  document.querySelectorAll('[data-toggle-target]').forEach((button) => {
    button.addEventListener('click', () => {
      const target = document.querySelector(button.dataset.toggleTarget);
      if (!target) return;
      target.classList.toggle('hidden-panel');
      if (!target.classList.contains('hidden-panel')) target.querySelector('input, textarea, select')?.focus();
    });
  });

  document.querySelectorAll('[data-focus-target]').forEach((button) => {
    button.addEventListener('click', () => {
      const target = document.querySelector(button.dataset.focusTarget);
      target?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      target?.focus({ preventScroll: true });
    });
  });

  document.querySelectorAll('[data-history-back]').forEach((button) => {
    button.addEventListener('click', () => window.history.back());
  });

  document.querySelectorAll('[data-file-zone] input[type=file]').forEach((input) => {
    input.addEventListener('change', () => {
      const name = input.files?.[0]?.name || '点击选择简历';
      input.closest('[data-file-zone]')?.querySelector('[data-file-name]')?.replaceChildren(name);
    });
  });

  const description = document.querySelector('#description');
  const counter = document.querySelector('[data-char-count]');
  if (description && counter) {
    const update = () => { counter.textContent = String(description.value.length); };
    description.addEventListener('input', update);
    update();
  }

  document.querySelectorAll('textarea').forEach((area) => {
    const resize = () => {
      if (area.dataset.fixedHeight === 'true') return;
      area.style.height = 'auto';
      area.style.height = Math.min(Math.max(area.scrollHeight, 88), 520) + 'px';
    };
    area.addEventListener('input', resize);
    resize();
  });
})();
