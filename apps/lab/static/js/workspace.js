(() => {
  'use strict';

  let running = false;
  let lastForward = null;

  function getLab() {
    return window.PIBICLab || null;
  }

  function getButton() {
    return document.getElementById('openWorkspaceBtn');
  }

  function getHint() {
    return document.getElementById('workspaceConnectionHint');
  }

  function setHint(text, kind = '') {
    const hint = getHint();

    if (!hint) return;

    hint.textContent = text;

    hint.style.color =
      kind === 'success'
        ? 'var(--success, #62c98d)'
        : kind === 'error'
          ? 'var(--danger, #e06c75)'
          : '';
  }

  async function openWorkspace() {
    if (running) return;

    const lab = getLab();
    const button = getButton();

    if (!lab || !lab.state) {
      return;
    }

    const profileId = Number(
      lab.state.profileId
    );

    const sshConnected = Boolean(
      lab.state.bootstrap
      && lab.state.bootstrap.ssh
      && lab.state.bootstrap.ssh.connected
    );

    if (!sshConnected) {
      lab.toast(
        'Conecte o SSH antes de abrir o PIBIC Workspace.',
        'error',
        'Workspace'
      );

      setHint(
        'SSH desconectado. Faça a conexão primeiro.',
        'error'
      );

      return;
    }

    if (!profileId) {
      lab.toast(
        'Nenhum perfil ativo foi encontrado.',
        'error',
        'Workspace'
      );
      return;
    }

    running = true;

    const oldHTML = button
      ? button.innerHTML
      : '';

    if (button) {
      button.disabled = true;

      button.innerHTML = `
        <span class="global-api-spinner"></span>
        <span>Conectando...</span>
      `;
    }

    setHint(
      'Verificando o serviço em 127.0.0.1:8765...'
    );

    try {
      const status = await lab.api(
        'workspace/status',
        {
          profile_id: profileId
        }
      );

      if (!status.available) {
        throw new Error(
          status.message
          || 'PIBIC Workspace não respondeu na VM.'
        );
      }

      setHint(
        'Workspace encontrado. Criando túnel SSH...'
      );

      const result = await lab.api(
        'workspace/open',
        {
          profile_id: profileId
        }
      );

      lastForward = result;

      setHint(
        `Workspace conectado pela porta local ${result.local_port}.`,
        'success'
      );

      lab.toast(
        `Forward criado: 127.0.0.1:${result.local_port} → VM:8765`,
        'success',
        'PIBIC Workspace'
      );

      /*
       * O backend tenta abrir o navegador padrão através
       * do módulo webbrowser do Python.
       *
       * Caso o ambiente não permita isso, tentamos abrir
       * pelo frontend como fallback.
       */
      if (!result.browser_opened && result.url) {
        const opened = window.open(
          result.url,
          '_blank',
          'noopener,noreferrer'
        );

        if (!opened) {
          lab.openModal({
            title: 'Workspace pronto',
            kicker: 'Forward SSH ativo',

            body: `
              <p>
                O túnel foi criado, mas o navegador
                não abriu automaticamente.
              </p>

              <p>
                Abra este endereço no navegador:
              </p>

              <span class="fingerprint">
                ${lab.escapeHtml(result.url)}
              </span>
            `,

            actions: [
              {
                label: 'Fechar',
                className: 'primary'
              }
            ]
          });
        }
      }

    } catch (error) {
      setHint(
        error.message,
        'error'
      );

      lab.toast(
        error.message,
        'error',
        'Não foi possível abrir o Workspace'
      );

    } finally {
      running = false;

      if (button) {
        button.disabled = false;

        button.innerHTML =
          oldHTML
          || `
            <span data-icon="external"></span>
            <span>Abrir Workspace</span>
          `;

        if (window.renderPibicIcons) {
          window.renderPibicIcons(button);
        }
      }
    }
  }

  async function checkWorkspaceSilently() {
    const lab = getLab();

    if (
      !lab
      || !lab.state
      || !lab.state.profileId
    ) {
      return;
    }

    if (
      !lab.state.bootstrap
      || !lab.state.bootstrap.ssh
      || !lab.state.bootstrap.ssh.connected
    ) {
      setHint(
        'Conecte o SSH para acessar o Workspace.'
      );
      return;
    }

    try {
      const status = await lab.api(
        'workspace/status',
        {
          profile_id: lab.state.profileId
        }
      );

      if (status.available) {
        setHint(
          'Workspace disponível na VM. Clique para abrir.',
          'success'
        );
      } else {
        setHint(
          'Workspace ainda não respondeu em 127.0.0.1:8765.'
        );
      }
    } catch (_) {
      /*
       * Diagnóstico automático não deve gerar toast
       * a cada atualização do dashboard.
       */
    }
  }

  function bind() {
    const button = getButton();

    if (!button) {
      return false;
    }

    if (
      button.dataset.workspaceBound === 'true'
    ) {
      return true;
    }

    button.dataset.workspaceBound = 'true';

    button.addEventListener(
      'click',
      openWorkspace
    );

    window.setTimeout(
      checkWorkspaceSilently,
      1200
    );

    return true;
  }

  function boot() {
    if (bind()) return;

    /*
     * O Vela pode injetar a view depois que o script
     * global já foi carregado. Observamos o DOM apenas
     * até encontrar o botão.
     */
    const observer = new MutationObserver(() => {
      if (bind()) {
        observer.disconnect();
      }
    });

    observer.observe(
      document.documentElement,
      {
        childList: true,
        subtree: true
      }
    );

    window.setTimeout(
      () => observer.disconnect(),
      15000
    );
  }

  if (
    document.readyState === 'loading'
  ) {
    document.addEventListener(
      'DOMContentLoaded',
      boot,
      { once: true }
    );
  } else {
    boot();
  }

  window.PIBICWorkspace = {
    open: openWorkspace,

    get lastForward() {
      return lastForward;
    }
  };
})();
