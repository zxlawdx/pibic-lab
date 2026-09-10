(() => {
  const svg = (body, size = 20) => `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
  window.PIBIC_ICONS = {
    lab: svg('<path d="M9 3h6"/><path d="M10 3v5l-5.5 9.5A2.2 2.2 0 0 0 6.4 21h11.2a2.2 2.2 0 0 0 1.9-3.5L14 8V3"/><path d="M7.8 15h8.4"/>', 26),
    dashboard: svg('<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>'),
    link: svg('<path d="M10 13a5 5 0 0 0 7.1.1l2-2a5 5 0 0 0-7.1-7.1l-1.1 1.1"/><path d="M14 11a5 5 0 0 0-7.1-.1l-2 2A5 5 0 0 0 12 20l1.1-1.1"/>'),
    unlink: svg('<path d="m18.8 18.8.9-.9a5 5 0 0 0-7.1-7.1l-.6.6"/><path d="m5.2 5.2-.9.9a5 5 0 0 0 7.1 7.1l.6-.6"/><path d="m2 2 20 20"/>'),
    terminal: svg('<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3"/><path d="M13 15h4"/>'),
    server: svg('<rect x="3" y="4" width="18" height="6" rx="2"/><rect x="3" y="14" width="18" height="6" rx="2"/><path d="M7 7h.01M7 17h.01"/>'),
    package: svg('<path d="m21 8-9 5-9-5 9-5 9 5Z"/><path d="m3 8 9 5 9-5v8l-9 5-9-5V8Z"/><path d="M12 13v8"/>'),
    boxes: svg('<path d="m12 2 4.5 2.5L12 7 7.5 4.5 12 2Z"/><path d="M7.5 4.5V10L12 12.5l4.5-2.5V4.5"/><path d="m5 12 4.5 2.5L5 17l-4.5-2.5L5 12Z"/><path d="M.5 14.5V20L5 22.5 9.5 20v-5.5"/><path d="m19 12 4.5 2.5L19 17l-4.5-2.5L19 12Z"/><path d="M14.5 14.5V20l4.5 2.5 4.5-2.5v-5.5"/>'),
    fileText: svg('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6M8 13h8M8 17h8M8 9h2"/>'),
    settings: svg('<path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56V21h-4v-.09A1.7 1.7 0 0 0 9 19.36a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.63 15 1.7 1.7 0 0 0 3.08 14H3v-4h.09A1.7 1.7 0 0 0 4.64 9a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.63 1.7 1.7 0 0 0 10 3.08V3h4v.09A1.7 1.7 0 0 0 15 4.64a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.37 9 1.7 1.7 0 0 0 20.92 10H21v4h-.09A1.7 1.7 0 0 0 19.4 15Z"/>'),
    refresh: svg('<path d="M20 11a8 8 0 1 0-2.34 5.66"/><path d="M20 4v7h-7"/>'),
    network: svg('<circle cx="12" cy="12" r="2"/><path d="M5.6 8.4a9 9 0 0 1 12.8 0M8.5 11.3a5 5 0 0 1 7 0M3 5.8a13 13 0 0 1 18 0"/><path d="M12 14v7"/>'),
    gateway: svg('<rect x="4" y="5" width="16" height="14" rx="2"/><path d="M8 9h8M8 13h3M15 13h1M8 17h8"/>'),
    shield: svg('<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/>'),
    shieldLarge: svg('<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/>', 54),
    activity: svg('<path d="M3 12h4l2-7 4 14 2-7h6"/>'),
    plus: svg('<path d="M12 5v14M5 12h14"/>'),
    x: svg('<path d="m6 6 12 12M18 6 6 18"/>'),
    key: svg('<circle cx="8" cy="15" r="4"/><path d="m11 12 8-8M15 8l3 3M17 6l2 2"/>'),
    search: svg('<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>'),
    download: svg('<path d="M12 3v12M7 10l5 5 5-5"/><path d="M5 21h14"/>'),
    save: svg('<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2Z"/><path d="M17 21v-8H7v8M7 3v5h8"/>'),
    alert: svg('<path d="M10.3 2.9 1.8 17a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 2.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/>'),
    check: svg('<path d="m5 12 4 4L19 6"/>'),
    cpu: svg('<rect x="7" y="7" width="10" height="10" rx="1"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/>'),
    database: svg('<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>'),
    code: svg('<path d="m8 9-4 3 4 3M16 9l4 3-4 3M14 5l-4 14"/>'),
    gitBranch: svg('<circle cx="6" cy="3" r="2"/><circle cx="18" cy="6" r="2"/><circle cx="6" cy="21" r="2"/><path d="M6 5v14M18 8c0 5-12 3-12 8"/>'),
    external: svg('<path d="M15 3h6v6M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>')
  };

  window.renderPibicIcons = (root = document) => {
    root.querySelectorAll('[data-icon]').forEach((node) => {
      const key = node.dataset.icon;
      const normalized = key === 'git-branch' ? 'gitBranch' : key;
      if (window.PIBIC_ICONS[normalized]) node.innerHTML = window.PIBIC_ICONS[normalized];
    });
  };
})();
