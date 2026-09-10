(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const VIEW_META = {
    dashboard: ['Visão geral', 'Laboratório PIBIC / UNIR'],
    connection: ['Conexão', 'ZeroTier, host key e SSH'],
    terminal: ['Terminal', 'Sessão SSH interativa'],
    proxmox: ['Proxmox', 'Recursos autorizados'],
    services: ['Serviços', 'Catálogo e detecção'],
    docker: ['Docker', 'Containers da VM'],
    logs: ['Logs', 'Auditoria e diagnóstico'],
    settings: ['Configurações', 'Perfil, ambiente e segurança']
  };

  const state = {
    bootstrap: null,
    profileId: null,
    environmentId: null,
    currentView: 'dashboard',
    connectivity: null,
    hostKey: null,
    dashboard: null,
    detectedServices: [],
    catalog: [],
    logs: [],
    proxmoxVms: [],
    terminal: {
      sessionId: null,
      xterm: null,
      fitAddon: null,
      pollTimer: null,
      startedAt: null,
      fallback: false
    }
  };

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function icon(name) {
    const normalized = name === 'git-branch' ? 'gitBranch' : name;
    return (window.PIBIC_ICONS && window.PIBIC_ICONS[normalized]) || (window.PIBIC_ICONS && window.PIBIC_ICONS.package) || '';
  }

  function setLoading(element, loading) {
    if (!element) return;
    element.classList.toggle('loading', Boolean(loading));
    if ('disabled' in element) element.disabled = Boolean(loading);
  }

  let apiPending = 0;

  function updateApiActivity(delta) {
    apiPending = Math.max(0, apiPending + delta);
    let indicator = document.getElementById('globalApiActivity');
    if (!indicator) {
      indicator = document.createElement('div');
      indicator.id = 'globalApiActivity';
      indicator.className = 'global-api-activity';
      indicator.innerHTML = '<span class="global-api-spinner"></span><span>Processando...</span>';
      document.body.appendChild(indicator);
    }
    indicator.classList.toggle('visible', apiPending > 0);
  }

  async function api(path, payload = null, method = 'POST') {
    const options = {
      method,
      headers: { 'Accept': 'application/json' }
    };
    if (payload !== null && method !== 'GET') {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(payload);
    }
    updateApiActivity(1);
    try {
      let response;
      try {
        response = await fetch(`/api/lab/${path}/`, options);
      } catch (error) {
        throw new Error(`Não foi possível acessar a API local do Vela: ${error.message}`);
      }
      let body;
      try {
        body = await response.json();
      } catch (_) {
        throw new Error(`A API local retornou uma resposta inválida (HTTP ${response.status}).`);
      }
      if (!response.ok) throw new Error(body.error || `Falha HTTP ${response.status}.`);
      if (!body || body.ok !== true) {
        const detail = body && body.details ? ` ${JSON.stringify(body.details)}` : '';
        throw new Error((body && body.error ? body.error : 'A operação falhou.') + detail);
      }
      return body.data;
    } finally {
      updateApiActivity(-1);
    }
  }

  function toast(message, type = 'info', title = null, timeout = 4300) {
    const region = $('#toastRegion');
    const item = document.createElement('div');
    item.className = `toast ${type}`;
    const iconName = type === 'error' ? 'alert' : type === 'success' ? 'check' : 'activity';
    item.innerHTML = `<span class="toast-icon">${icon(iconName)}</span><div><strong>${escapeHtml(title || (type === 'error' ? 'Não foi possível concluir' : type === 'success' ? 'Operação concluída' : 'PIBIC LAB'))}</strong><p>${escapeHtml(message)}</p></div>`;
    region.appendChild(item);
    window.setTimeout(() => item.remove(), timeout);
  }

  function closeModal() {
    $('#modalBackdrop').classList.add('hidden');
    $('#modalBody').innerHTML = '';
    $('#modalFooter').innerHTML = '';
  }

  function openModal({ title, kicker = 'Confirmação', body = '', actions = [] }) {
    $('#modalKicker').textContent = kicker;
    $('#modalTitle').textContent = title;
    $('#modalBody').innerHTML = body;
    const footer = $('#modalFooter');
    footer.innerHTML = '';
    actions.forEach((action) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = `button ${action.className || 'secondary'}`;
      btn.textContent = action.label;
      btn.addEventListener('click', async () => {
        try {
          if (action.close !== false) closeModal();
          if (action.onClick) await action.onClick();
        } catch (error) {
          toast(error.message, 'error');
        }
      });
      footer.appendChild(btn);
    });
    $('#modalBackdrop').classList.remove('hidden');
  }

  function currentProfile() {
    return state.bootstrap && state.bootstrap.profile ? state.bootstrap.profile : null;
  }

  function currentEnvironment() {
    return state.bootstrap && state.bootstrap.environment ? state.bootstrap.environment : null;
  }

  function permissions() {
    return (state.bootstrap && state.bootstrap.permissions) || {};
  }

  function bytes(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return 'Não disponível';
    let n = Number(value);
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0;
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i += 1; }
    return `${n >= 10 || i === 0 ? n.toFixed(0) : n.toFixed(1)} ${units[i]}`;
  }

  function duration(seconds) {
    if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return 'Não disponível';
    const total = Math.max(0, Math.floor(Number(seconds)));
    const days = Math.floor(total / 86400);
    const hours = Math.floor((total % 86400) / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    if (days) return `${days}d ${hours}h`;
    if (hours) return `${hours}h ${minutes}min`;
    return `${minutes}min`;
  }

  function percentRatio(value, max) {
    if (!max || value === null || value === undefined) return 'Não disponível';
    return `${Math.max(0, Math.min(100, (Number(value) / Number(max)) * 100)).toFixed(1)}%`;
  }

  function setBadge(element, text, kind = 'muted') {
    if (!element) return;
    element.textContent = text;
    element.className = `badge ${kind}`;
  }

  function setDot(element, kind = 'neutral') {
    if (!element) return;
    element.className = `status-dot ${kind}`;
  }

  function updateSidebarConnection(connected, subtitle = '') {
    const pill = $('#sidebarConnectionPill');
    const dot = $('.status-dot', pill);
    $('#sidebarConnectionTitle').textContent = connected ? 'SSH conectado' : 'Não conectado';
    $('#sidebarConnectionSubtitle').textContent = subtitle || (connected ? 'Sessão ativa' : 'SSH inativo');
    setDot(dot, connected ? 'ok' : 'neutral');
    $('#terminalStatusDot') && setDot($('#terminalStatusDot'), connected ? 'ok' : 'neutral');
  }

  function showView(name) {
    if (!VIEW_META[name]) return;
    state.currentView = name;
    $$('.view').forEach((panel) => panel.classList.toggle('active', panel.dataset.viewPanel === name));
    $$('.nav-item').forEach((button) => button.classList.toggle('active', button.dataset.view === name));
    $('#pageTitle').textContent = VIEW_META[name][0];
    $('#pageEyebrow').textContent = VIEW_META[name][1];
    if (name === 'terminal') ensureTerminalSizing();
    if (name === 'proxmox') loadProxmox(false);
    if (name === 'services') { loadCatalog(false); loadJobs(false); }
    if (name === 'docker') loadDocker(false);
    if (name === 'logs') loadLogs(false);
  }

  async function refreshCurrent() {
    const handlers = {
      dashboard: () => loadDashboard(true),
      connection: () => refreshConnectivity(true),
      terminal: () => ensureTerminalSizing(),
      proxmox: () => loadProxmox(true),
      services: async () => { await detectServices(true); await loadCatalog(true); await loadJobs(true); },
      docker: () => loadDocker(true),
      logs: () => loadLogs(true),
      settings: () => loadBootstrap(state.profileId, state.environmentId)
    };
    await handlers[state.currentView]();
  }

  function populateBootstrap(data) {
    state.bootstrap = data;
    state.profileId = Number(data.profile.id);
    state.environmentId = Number(data.environment.id);
    $('#appVersion').textContent = data.app.version || '0.1.2';

    const profileSelect = $('#profileSelect');
    profileSelect.innerHTML = data.profiles.map((profile) => `<option value="${profile.id}">${escapeHtml(profile.display_name)}</option>`).join('');
    profileSelect.value = String(state.profileId);

    const envSelect = $('#environmentSelect');
    envSelect.innerHTML = data.environments.map((env) => `<option value="${env.id}">${escapeHtml(env.name)}</option>`).join('');
    envSelect.value = String(state.environmentId);

    $('#sshUsername').value = data.profile.ssh_username || '';
    $('#sshAuthMethod').value = data.ssh_preferences.auth_method || 'agent';
    $('#sshKeyPath').value = data.ssh_preferences.key_path || '';
    $('#saveSshPassword').checked = Boolean(data.ssh_preferences.save_password);
    updateAuthFields();

    fillSettingsForms();
    updateSshUi(data.ssh || { connected: false });
    renderInitialZeroTier(data.zerotier);
    applyPermissionUi();
  }

  async function loadBootstrap(profileId = null, environmentId = null) {
    try {
      const data = profileId || environmentId
        ? await api('bootstrap', { profile_id: profileId, environment_id: environmentId })
        : await api('bootstrap', null, 'GET');
      populateBootstrap(data);
      await refreshConnectivity(false);
      await loadCatalog(false);
      await loadDashboard(false);
    } catch (error) {
      toast(error.message, 'error', 'Falha ao iniciar');
    }
  }

  function fillSettingsForms() {
    const p = currentProfile();
    const e = currentEnvironment();
    const settings = state.bootstrap.settings || {};
    if (p) {
      $('#profileId').value = p.id ?? '';
      $('#profileDisplayName').value = p.display_name || '';
      $('#profileSshUsername').value = p.ssh_username || '';
      $('#profileRole').value = p.role || 'student';
      $('#profileVmids').value = (p.assigned_vmids || []).join(', ');
      $('#profileCanPower').checked = Boolean(p.can_proxmox_power);
      $('#profileCanInstall').checked = Boolean(p.can_install_services);
    }
    if (e) {
      $('#environmentId').value = e.id ?? '';
      $('#environmentName').value = e.name || '';
      $('#environmentGateway').value = e.gateway_host || '';
      $('#environmentSshPort').value = e.ssh_port || 22;
      $('#environmentProxmoxHost').value = e.proxmox_internal_host || '';
      $('#environmentProxmoxPort').value = e.proxmox_port || 8006;
      $('#environmentNetworkId').value = e.zerotier_network_id || '';
    }
    $('#verifyProxmoxTls').checked = settings.verify_proxmox_tls !== false;
    $('#proxmoxCaPath').value = settings.proxmox_ca_path || '';
    $('#allowUnsafeTls').checked = Boolean(settings.allow_unsafe_proxmox_tls);
  }

  function applyPermissionUi() {
    const perms = permissions();
    const p = currentProfile();
    $$('[data-go-view="terminal"]').forEach((node) => { node.disabled = !perms.terminal; });
    $('#terminalNewBtn').disabled = !perms.terminal;
    $('#proxmoxCredentialBtn').disabled = !perms.proxmox_read;
    $('#refreshProxmoxBtn').disabled = !perms.proxmox_read;
    $('#createProxmoxVmBtn').classList.toggle('hidden', !p || p.role !== 'admin');
    $('#detectServicesBtn').disabled = !perms.services_read;
    $('#refreshDockerBtn').disabled = !perms.docker_read;
  }

  function updateAuthFields() {
    const value = $('#sshAuthMethod').value;
    $('#sshKeyFields').classList.toggle('hidden', value !== 'key');
    $('#sshPasswordFields').classList.toggle('hidden', value !== 'password');
  }

  function ztKind(zt) {
    if (!zt) return ['Não verificado', 'muted'];
    const mapping = {
      ok_private: ['OK', 'ok'],
      tunneled: ['TUNNELED', 'warn'],
      access_denied: ['ACESSO PENDENTE', 'warn'],
      online: ['ONLINE', 'warn'],
      offline: ['OFFLINE', 'error'],
      not_installed: ['NÃO INSTALADO', 'error'],
      unknown: ['INDEFINIDO', 'warn']
    };
    return mapping[zt.state] || [String(zt.state || '--').toUpperCase(), 'muted'];
  }

  function renderInitialZeroTier(zt) {
    const [label, kind] = ztKind(zt);
    setBadge($('#dashZtBadge'), label, kind);
    $('#dashZtStatus').textContent = zt && zt.message ? zt.message : 'Aguardando verificação';
    $('#ztState').textContent = zt && zt.message ? zt.message : 'Não verificado';
    $('#ztNodeId').textContent = zt && zt.node_id ? zt.node_id : '--';
    $('#ztAssignedIp').textContent = zt && zt.local_addresses && zt.local_addresses.length ? zt.local_addresses.join(', ') : '--';
  }

  async function refreshConnectivity(showToast = false) {
    if (!state.environmentId) return;
    const button = $('#checkConnectivityBtn');
    setLoading(button, true);
    try {
      const data = await api('connectivity', { environment_id: state.environmentId });
      state.connectivity = data;
      renderConnectivity(data);
      if (showToast) toast('Diagnóstico de conectividade atualizado.', 'success');
      return data;
    } catch (error) {
      if (showToast) toast(error.message, 'error');
      throw error;
    } finally {
      setLoading(button, false);
    }
  }

  function renderConnectivity(data) {
    const zt = data.zerotier || {};
    renderInitialZeroTier(zt);
    const [ztLabel, ztBadgeKind] = ztKind(zt);
    setBadge($('#dashZtBadge'), ztLabel, ztBadgeKind);
    $('#dashZtStatus').textContent = zt.message || 'Estado indisponível';

    const gateway = data.gateway || {};
    $('#gatewayState').textContent = gateway.available ? `Disponível em ${gateway.host}:${gateway.port}` : `Indisponível em ${gateway.host}:${gateway.port}`;
    $('#dashGatewayStatus').textContent = gateway.available ? `${gateway.host}:${gateway.port} respondeu` : (gateway.error || `${gateway.host}:${gateway.port}`);
    setBadge($('#dashGatewayBadge'), gateway.available ? 'DISPONÍVEL' : 'INDISPONÍVEL', gateway.available ? 'ok' : 'error');

    const overallGood = ['ok_private', 'tunneled'].includes(zt.state) && gateway.available;
    setBadge($('#connectionOverallBadge'), overallGood ? 'PRONTO' : 'VERIFIQUE', overallGood ? 'ok' : 'warn');
    setDot($('#heroStatusDot'), overallGood ? 'ok' : 'warn');
    if (!state.bootstrap.ssh.connected) {
      $('#heroStatusText').textContent = overallGood ? 'Rede pronta para conexão SSH' : 'Conectividade precisa de atenção';
    }
  }

  async function probeHostKey({ promptTrust = true } = {}) {
    const button = $('#probeHostKeyBtn');
    setLoading(button, true);
    try {
      const keyInfo = await api('ssh/probe', { environment_id: state.environmentId });
      state.hostKey = keyInfo;
      renderHostKey(keyInfo);
      if (keyInfo.changed) {
        openModal({
          title: 'Host key alterada',
          kicker: 'Bloqueio de segurança',
          body: `<p>A chave apresentada pelo gateway não corresponde à que foi aceita anteriormente. A conexão foi bloqueada por padrão.</p><span class="fingerprint">${escapeHtml(keyInfo.fingerprint_sha256)}</span><p>Confirme a alteração por um canal confiável com o responsável pelo servidor antes de substituir a chave conhecida.</p>`,
          actions: [{ label: 'Fechar', className: 'secondary' }]
        });
        return keyInfo;
      }
      if (!keyInfo.trusted && promptTrust) {
        openTrustHostKeyModal(keyInfo);
      } else if (keyInfo.trusted) {
        toast('Host key corresponde à chave já confiada.', 'success');
      }
      return keyInfo;
    } catch (error) {
      toast(error.message, 'error');
      throw error;
    } finally {
      setLoading(button, false);
    }
  }

  function renderHostKey(keyInfo) {
    if (!keyInfo) return;
    if (keyInfo.changed) {
      $('#hostKeyText').textContent = `Chave alterada: ${keyInfo.fingerprint_sha256}`;
      $('#dashHostKeyStatus').textContent = 'A chave do servidor mudou. Conexão bloqueada.';
      setBadge($('#dashHostKeyBadge'), 'ALTERADA', 'error');
    } else if (keyInfo.trusted) {
      $('#hostKeyText').textContent = `${keyInfo.algorithm} · ${keyInfo.fingerprint_sha256}`;
      $('#dashHostKeyStatus').textContent = 'Fingerprint validada e registrada localmente.';
      setBadge($('#dashHostKeyBadge'), 'CONFIÁVEL', 'ok');
    } else {
      $('#hostKeyText').textContent = `${keyInfo.algorithm} · ${keyInfo.fingerprint_sha256}`;
      $('#dashHostKeyStatus').textContent = 'Aguardando confirmação do primeiro acesso.';
      setBadge($('#dashHostKeyBadge'), 'CONFIRMAR', 'warn');
    }
  }

  function openTrustHostKeyModal(keyInfo) {
    openModal({
      title: 'Confirmar identidade do gateway',
      kicker: 'Primeiro acesso',
      body: `<p>Antes de enviar qualquer credencial, compare esta fingerprint SHA256 com a informação fornecida pelo administrador do laboratório.</p><span class="fingerprint">${escapeHtml(keyInfo.fingerprint_sha256)}</span><p>Algoritmo: <strong>${escapeHtml(keyInfo.algorithm)}</strong><br>Destino: <strong>${escapeHtml(keyInfo.host)}:${keyInfo.port}</strong></p><p>Confirme somente se a fingerprint estiver correta.</p>`,
      actions: [
        { label: 'Cancelar', className: 'secondary' },
        { label: 'Confiar nesta chave', className: 'primary', onClick: async () => {
          await api('ssh/trust', { profile_id: state.profileId, host_key: keyInfo });
          keyInfo.trusted = true;
          keyInfo.changed = false;
          state.hostKey = keyInfo;
          renderHostKey(keyInfo);
          toast('Host key salva no arquivo known_hosts do aplicativo.', 'success');
        }}
      ]
    });
  }

  async function connectSsh(event = null) {
    if (event) event.preventDefault();
    const button = $('#connectSshBtn');
    setLoading(button, true);
    try {
      let keyInfo = state.hostKey;
      if (!keyInfo || keyInfo.host !== currentEnvironment().gateway_host || keyInfo.port !== currentEnvironment().ssh_port) {
        keyInfo = await probeHostKey({ promptTrust: false });
      }
      if (keyInfo.changed) throw new Error('A host key mudou. A conexão permanece bloqueada.');
      if (!keyInfo.trusted) {
        openTrustHostKeyModal(keyInfo);
        throw new Error('Confirme a fingerprint do gateway antes de conectar.');
      }

      const authMethod = $('#sshAuthMethod').value;
      const payload = {
        profile_id: state.profileId,
        environment_id: state.environmentId,
        username: $('#sshUsername').value.trim(),
        auth_method: authMethod,
        key_path: $('#sshKeyPath').value.trim(),
        key_passphrase: $('#sshKeyPassphrase').value,
        save_key_passphrase: $('#saveKeyPassphrase').checked,
        password: $('#sshPassword').value,
        save_password: $('#saveSshPassword').checked
      };
      const result = await api('ssh/connect', payload);
      state.bootstrap.ssh = result;
      updateSshUi(result);
      $('#sshPassword').value = '';
      $('#sshKeyPassphrase').value = '';
      toast(`Conectado a ${result.host}:${result.port} como ${result.username}.`, 'success');
      await loadDashboard(false);
      showView('dashboard');
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      setLoading(button, false);
    }
  }

  async function disconnectSsh() {
    try {
      if (state.terminal.sessionId) await closeTerminal(false);
      await api('ssh/disconnect', { profile_id: state.profileId });
      state.bootstrap.ssh = { connected: false, profile_id: state.profileId };
      updateSshUi(state.bootstrap.ssh);
      clearDashboard();
      toast('Sessão SSH encerrada.', 'success');
    } catch (error) {
      toast(error.message, 'error');
    }
  }

  function updateSshUi(ssh) {
    const connected = Boolean(ssh && ssh.connected);
    updateSidebarConnection(connected, connected ? `${ssh.username || ''}@${ssh.host || ''}` : 'SSH inativo');
    setBadge($('#sshConnectionBadge'), connected ? 'CONECTADO' : 'DESCONECTADO', connected ? 'ok' : 'muted');
    $('#connectSshBtn').disabled = connected;
    $('#disconnectSshBtn').disabled = !connected;
    $('#terminalNewBtn').disabled = !connected || !permissions().terminal;
    if (connected) {
      setDot($('#heroStatusDot'), 'ok');
      $('#heroStatusText').textContent = `SSH conectado como ${ssh.username || currentProfile().ssh_username || 'usuário'}`;
      $('#heroConnectBtn').innerHTML = `${icon('terminal')}<span>Abrir terminal</span>`;
    } else {
      $('#heroConnectBtn').innerHTML = `${icon('link')}<span>Conectar</span>`;
    }
  }

  function clearDashboard() {
    state.dashboard = null;
    $('#heroHostname').textContent = 'Sua VM em um só lugar';
    $('#heroDescription').textContent = 'Conecte-se ao gateway do laboratório para consultar sistema, serviços e recursos permitidos.';
    ['metricCpu', 'metricRam', 'metricDisk', 'metricUptime', 'infoOs', 'infoKernel', 'infoArch', 'infoCpu', 'infoIps'].forEach((id) => { $(`#${id}`).textContent = 'Não disponível'; });
    $('#serviceSummaryGrid').innerHTML = '<div class="empty-state compact">Conecte-se para detectar os serviços da VM.</div>';
  }

  async function loadDashboard(showToast = false) {
    if (!state.profileId) return;
    const button = $('#dashboardRefreshBtn');
    setLoading(button, true);
    try {
      const data = await api('dashboard', { profile_id: state.profileId });
      state.dashboard = data;
      renderDashboard(data);
      if (showToast) toast('Dados da VM atualizados.', 'success');
      return data;
    } catch (error) {
      clearDashboard();
      if (showToast) toast(error.message, 'error');
    } finally {
      setLoading(button, false);
    }
  }

  function renderDashboard(data) {
    if (!data || !data.connected) {
      clearDashboard();
      updateSshUi({ connected: false, profile_id: state.profileId });
      return;
    }
    updateSshUi(data.ssh);
    const sys = data.system || {};
    const profile = data.profile || currentProfile();
    $('#heroHostname').textContent = sys.hostname || 'VM conectada';
    $('#heroDescription').textContent = `${sys.os_name || 'Sistema não identificado'} · ${profile.display_name || 'Perfil local'} · ${data.privilege && data.privilege.is_root ? 'sessão root' : 'sessão sem root'}`;
    $('#metricCpu').textContent = sys.cpu_count ? `${sys.cpu_count} vCPU` : 'Não disponível';
    $('#metricRam').textContent = sys.ram_total ? `${bytes(sys.ram_used)} / ${bytes(sys.ram_total)}` : 'Não disponível';
    $('#metricDisk').textContent = sys.disk_total ? `${bytes(sys.disk_used)} / ${bytes(sys.disk_total)}` : 'Não disponível';
    $('#metricUptime').textContent = duration(sys.uptime_seconds);
    $('#infoOs').textContent = sys.os_name || 'Não disponível';
    $('#infoKernel').textContent = sys.kernel || 'Não disponível';
    $('#infoArch').textContent = sys.architecture || 'Não disponível';
    $('#infoCpu').textContent = [sys.cpu_count ? `${sys.cpu_count} vCPU` : null, sys.cpu_model].filter(Boolean).join(' · ') || 'Não disponível';
    $('#infoIps').textContent = sys.ip_addresses && sys.ip_addresses.length ? sys.ip_addresses.join(', ') : 'Não disponível';
    state.detectedServices = data.services || [];
    renderServiceSummary(state.detectedServices);
  }

  function renderServiceSummary(services) {
    const host = $('#serviceSummaryGrid');
    if (!services || !services.length) {
      host.innerHTML = '<div class="empty-state compact">Nenhum serviço detectado.</div>';
      return;
    }
    host.innerHTML = services.slice(0, 8).map((service) => {
      const status = service.id === 'pgvector' && service.status === 'não confirmado'
        ? 'Não confirmado'
        : service.installed ? (service.version || 'Instalado') : 'Não encontrado';
      return `<div class="service-mini"><strong>${escapeHtml(service.name)}</strong><span>${escapeHtml(status)}</span></div>`;
    }).join('');
  }

  async function detectServices(showToast = true) {
    const button = $('#detectServicesBtn');
    setLoading(button, true);
    try {
      const services = await api('services/detect', { profile_id: state.profileId });
      state.detectedServices = services;
      renderServiceSummary(services);
      renderCatalog();
      if (showToast) toast('Detecção somente leitura concluída.', 'success');
      return services;
    } catch (error) {
      if (showToast) toast(error.message, 'error');
      return [];
    } finally {
      setLoading(button, false);
    }
  }

  async function openTerminal() {
    if (!state.bootstrap || !state.bootstrap.ssh.connected) {
      toast('Conecte-se via SSH antes de abrir o terminal.', 'error');
      showView('connection');
      return;
    }
    if (state.terminal.sessionId) {
      showView('terminal');
      ensureTerminalSizing();
      return;
    }
    try {
      initTerminalRenderer();
      const geometry = terminalGeometry();
      const result = await api('terminal/open', { profile_id: state.profileId, cols: geometry.cols, rows: geometry.rows });
      state.terminal.sessionId = result.session_id;
      state.terminal.startedAt = Date.now();
      $('#terminalSessionLabel').textContent = `Sessão: ${result.session_id.slice(0, 10)}`;
      $('#terminalSubtitle').textContent = `${currentProfile().ssh_username || $('#sshUsername').value || 'usuário'}@${currentEnvironment().gateway_host}`;
      setDot($('#terminalStatusDot'), 'ok');
      startTerminalPolling();
      showView('terminal');
      ensureTerminalSizing();
    } catch (error) {
      toast(error.message, 'error');
    }
  }

  function initTerminalRenderer() {
    if (state.terminal.xterm || state.terminal.fallback) return;
    const host = $('#terminalHost');
    if (typeof window.Terminal === 'function') {
      const xterm = new window.Terminal({
        cursorBlink: true,
        convertEol: false,
        scrollback: (state.bootstrap.settings && state.bootstrap.settings.terminal_scrollback) || 5000,
        fontFamily: 'Cascadia Code, Consolas, monospace',
        fontSize: 13,
        lineHeight: 1.16,
        theme: {
          background: '#080c12', foreground: '#dce4ee', cursor: '#8cbcff',
          selectionBackground: '#294d78', black: '#10151d', brightBlack: '#5d6878',
          red: '#df7979', brightRed: '#f59696', green: '#70c78e', brightGreen: '#8ad9a5',
          yellow: '#ddb96a', brightYellow: '#eed088', blue: '#6fa7ee', brightBlue: '#8dbaf5',
          magenta: '#b696df', brightMagenta: '#c8aaed', cyan: '#6cc0c4', brightCyan: '#8ed4d7',
          white: '#dbe2ea', brightWhite: '#ffffff'
        }
      });
      let fitAddon = null;
      if (window.FitAddon && typeof window.FitAddon.FitAddon === 'function') {
        fitAddon = new window.FitAddon.FitAddon();
        xterm.loadAddon(fitAddon);
      }
      xterm.open(host);
      xterm.onData((data) => sendTerminalText(data));
      state.terminal.xterm = xterm;
      state.terminal.fitAddon = fitAddon;
      $('#terminalFallback').classList.add('hidden');
      host.classList.remove('hidden');
      $('#terminalEngineLabel').textContent = 'xterm.js local · PTY remoto';
    } else {
      state.terminal.fallback = true;
      host.classList.add('hidden');
      $('#terminalFallback').classList.remove('hidden');
      $('#terminalEngineLabel').textContent = 'Terminal básico · execute scripts/vendor_frontend.py para xterm.js completo';
    }
  }

  function terminalGeometry() {
    if (state.terminal.xterm) return { cols: state.terminal.xterm.cols || 100, rows: state.terminal.xterm.rows || 30 };
    return { cols: 110, rows: 32 };
  }

  async function sendTerminalText(text) {
    if (!state.terminal.sessionId || !text) return;
    const encoded = bytesToBase64(new TextEncoder().encode(text));
    try {
      await api('terminal/input', { profile_id: state.profileId, session_id: state.terminal.sessionId, data_b64: encoded });
    } catch (error) {
      toast(error.message, 'error');
    }
  }

  function bytesToBase64(bytesArray) {
    let binary = '';
    const chunkSize = 0x8000;
    for (let i = 0; i < bytesArray.length; i += chunkSize) {
      binary += String.fromCharCode(...bytesArray.subarray(i, i + chunkSize));
    }
    return btoa(binary);
  }

  function base64ToBytes(value) {
    const binary = atob(value || '');
    const bytesArray = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytesArray[i] = binary.charCodeAt(i);
    return bytesArray;
  }

  function startTerminalPolling() {
    stopTerminalPolling();
    const interval = (state.bootstrap.settings && state.bootstrap.settings.poll_interval_ms) || 120;
    state.terminal.pollTimer = window.setInterval(pollTerminal, interval);
  }

  function stopTerminalPolling() {
    if (state.terminal.pollTimer) window.clearInterval(state.terminal.pollTimer);
    state.terminal.pollTimer = null;
  }

  async function pollTerminal() {
    if (!state.terminal.sessionId) return;
    try {
      const result = await api('terminal/poll', { profile_id: state.profileId, session_id: state.terminal.sessionId });
      if (result.data_b64) {
        const decoded = new TextDecoder('utf-8', { fatal: false }).decode(base64ToBytes(result.data_b64));
        if (state.terminal.xterm) state.terminal.xterm.write(decoded);
        else appendFallbackTerminal(decoded);
      }
      if (result.closed) {
        stopTerminalPolling();
        setDot($('#terminalStatusDot'), 'neutral');
        $('#terminalSubtitle').textContent = `Sessão encerrada · código ${result.exit_status ?? '--'}`;
        state.terminal.sessionId = null;
      }
    } catch (error) {
      stopTerminalPolling();
      setDot($('#terminalStatusDot'), 'error');
      toast(error.message, 'error');
    }
  }

  function appendFallbackTerminal(text) {
    const output = $('#terminalFallbackOutput');
    const stripped = text.replace(/\x1B\[[0-?]*[ -\/]*[@-~]/g, '').replace(/\x1B\][^\x07]*(?:\x07|\x1B\\)/g, '');
    output.textContent += stripped;
    if (output.textContent.length > 500000) output.textContent = output.textContent.slice(-400000);
    output.scrollTop = output.scrollHeight;
  }

  async function closeTerminal(showToast = true) {
    const id = state.terminal.sessionId;
    stopTerminalPolling();
    if (id) {
      try {
        await api('terminal/close', { profile_id: state.profileId, session_id: id });
      } catch (error) {
        if (showToast) toast(error.message, 'error');
      }
    }
    state.terminal.sessionId = null;
    state.terminal.startedAt = null;
    if (state.terminal.xterm) {
      state.terminal.xterm.dispose();
      state.terminal.xterm = null;
      state.terminal.fitAddon = null;
      $('#terminalHost').innerHTML = '';
    }
    state.terminal.fallback = false;
    $('#terminalFallbackOutput').textContent = '';
    $('#terminalFallback').classList.add('hidden');
    $('#terminalHost').classList.remove('hidden');
    $('#terminalSessionLabel').textContent = 'Sessão: --';
    $('#terminalSubtitle').textContent = 'Nenhuma sessão aberta';
    $('#terminalEngineLabel').textContent = 'Terminal aguardando conexão';
    setDot($('#terminalStatusDot'), state.bootstrap && state.bootstrap.ssh.connected ? 'ok' : 'neutral');
    if (showToast) toast('Terminal encerrado.', 'success');
  }

  async function ensureTerminalSizing() {
    window.setTimeout(async () => {
      if (!state.terminal.xterm || !state.terminal.sessionId) return;
      try {
        if (state.terminal.fitAddon) state.terminal.fitAddon.fit();
        const geometry = terminalGeometry();
        await api('terminal/resize', { profile_id: state.profileId, session_id: state.terminal.sessionId, cols: geometry.cols, rows: geometry.rows });
      } catch (_) { /* resize não deve interromper a sessão */ }
    }, 70);
  }

  async function loadCatalog(showToast = false) {
    const button = $('#refreshCatalogBtn');
    setLoading(button, true);
    try {
      state.catalog = await api('catalog', null, 'GET');
      renderCatalog();
      if (showToast) toast('Catálogo local recarregado.', 'success');
    } catch (error) {
      $('#catalogGrid').innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
      if (showToast) toast(error.message, 'error');
    } finally {
      setLoading(button, false);
    }
  }

  function detectedServiceFor(manifest) {
    const aliases = { python: 'python', postgresql: 'postgresql', docker: 'docker', nginx: 'nginx', git: 'git' };
    return state.detectedServices.find((service) => service.id === aliases[manifest.id]);
  }

  function renderCatalog() {
    const grid = $('#catalogGrid');
    if (!state.catalog.length) {
      grid.innerHTML = '<div class="empty-state">Nenhum manifest encontrado em catalog/manifests.</div>';
      return;
    }
    grid.innerHTML = state.catalog.map((manifest) => {
      const detected = detectedServiceFor(manifest);
      const statusText = detected ? (detected.installed ? (detected.version || 'Instalado') : 'Não instalado') : 'Ainda não detectado';
      const statusKind = detected ? (detected.installed ? 'ok' : 'muted') : 'muted';
      return `<article class="catalog-card" data-manifest-id="${escapeHtml(manifest.id)}">
        <div class="catalog-card-head"><span class="catalog-icon">${icon(manifest.icon || 'package')}</span><span class="badge ${statusKind}">${escapeHtml(statusText)}</span></div>
        <h3>${escapeHtml(manifest.name)}</h3><p>${escapeHtml(manifest.description || '')}</p>
        <div class="catalog-meta"><span>${escapeHtml(manifest.category)}</span><span>Manifest v${escapeHtml(manifest.manifest_version)}</span></div>
        <div class="button-row"><button class="button secondary small catalog-plan-btn" data-id="${escapeHtml(manifest.id)}">Ver plano</button>${permissions().services_install ? `<button class="button primary small catalog-install-btn" data-id="${escapeHtml(manifest.id)}">Instalar</button>` : ''}</div>
      </article>`;
    }).join('');
    $$('.catalog-plan-btn', grid).forEach((button) => button.addEventListener('click', () => showInstallPlan(button.dataset.id, false)));
    $$('.catalog-install-btn', grid).forEach((button) => button.addEventListener('click', () => showInstallPlan(button.dataset.id, true)));
  }

  async function showInstallPlan(manifestId, installMode) {
    try {
      const plan = await api('catalog/plan', { profile_id: state.profileId, manifest_id: manifestId });
      const commands = plan.commands_preview && plan.commands_preview.length
        ? `<pre class="modal-code">${escapeHtml(plan.commands_preview.join('\n'))}</pre>`
        : '<p>Nenhum comando de instalação disponível para este sistema.</p>';
      const compatible = plan.compatible;
      const body = `<p><strong>${escapeHtml(plan.manifest_name)}</strong> para ${escapeHtml(plan.os_id || 'SO desconhecido')} ${escapeHtml(plan.os_version || '')}.</p>
        <p>${compatible ? 'O manifest declarou compatibilidade com este ambiente.' : escapeHtml(plan.reason || 'Manifest incompatível.')}</p>
        ${commands}
        ${plan.requires_admin ? '<div class="notice warning"><span>' + icon('shield') + '</span><p>Este plano exige privilégios administrativos. A senha de elevação é usada apenas durante o job e não é persistida.</p></div>' : ''}
        ${installMode && compatible && plan.requires_admin ? '<label class="field" style="margin-top:14px"><span>Senha de elevação (sudo/doas) para este job</span><input id="modalElevationPassword" type="password" autocomplete="off" placeholder="Deixe vazio se a sessão já for root"></label>' : ''}`;
      const actions = [{ label: 'Fechar', className: 'secondary' }];
      if (installMode && compatible) {
        actions.push({ label: 'Confirmar e executar', className: 'primary', close: false, onClick: async () => {
          const passwordInput = $('#modalElevationPassword');
          const password = passwordInput ? passwordInput.value : '';
          await api('catalog/install', { profile_id: state.profileId, manifest_id: manifestId, confirmed: true, elevation_password: password });
          if (passwordInput) passwordInput.value = '';
          closeModal();
          toast('Job de instalação criado. Acompanhe o progresso na seção de jobs.', 'success');
          await loadJobs(false);
        }});
      }
      openModal({ title: installMode ? 'Confirmar instalação assistida' : 'Plano de instalação', kicker: 'Manifest declarativo', body, actions });
    } catch (error) {
      toast(error.message, 'error');
    }
  }

  async function loadJobs(showToast = false) {
    try {
      const jobs = await api('jobs', null, 'GET');
      renderJobs(jobs);
      if (showToast) toast('Lista de jobs atualizada.', 'success');
    } catch (error) {
      if (showToast) toast(error.message, 'error');
    }
  }

  function renderJobs(jobs) {
    const host = $('#jobsList');
    if (!jobs || !jobs.length) {
      host.innerHTML = '<div class="empty-state compact">Nenhum job executado.</div>';
      return;
    }
    const labels = { queued: ['Na fila', 'muted'], running: ['Executando', 'warn'], success: ['Concluído', 'ok'], failed: ['Falhou', 'error'], cancelled: ['Cancelado', 'muted'] };
    host.innerHTML = jobs.map((job) => {
      const [label, kind] = labels[job.state] || [job.state, 'muted'];
      const lastOutput = (job.output || []).slice(-1)[0] || job.error || 'Sem saída';
      return `<div class="job-row"><div><strong>${escapeHtml(job.manifest_id)}</strong><span class="job-id">${escapeHtml(job.id.slice(0, 14))}</span></div><span class="badge ${kind}">${escapeHtml(label)}</span><span class="job-output" title="${escapeHtml(lastOutput)}">${escapeHtml(lastOutput)}</span></div>`;
    }).join('');
  }

  async function loadDocker(showToast = false) {
    if (!state.bootstrap || !state.bootstrap.ssh.connected) {
      renderDocker({ available: false, containers: [], stderr: 'Sessão SSH não conectada.' });
      return;
    }
    const button = $('#refreshDockerBtn');
    setLoading(button, true);
    try {
      const data = await api('docker/list', { profile_id: state.profileId });
      renderDocker(data);
      if (showToast) toast('Containers atualizados.', 'success');
    } catch (error) {
      renderDocker({ available: false, containers: [], stderr: error.message });
      if (showToast) toast(error.message, 'error');
    } finally {
      setLoading(button, false);
    }
  }

  function renderDocker(data) {
    const body = $('#dockerTableBody');
    if (!data.available) {
      body.innerHTML = `<tr><td colspan="6"><div class="empty-state">${escapeHtml(data.stderr || 'Docker indisponível nesta sessão.')}</div></td></tr>`;
      return;
    }
    if (!data.containers || !data.containers.length) {
      body.innerHTML = '<tr><td colspan="6"><div class="empty-state">Docker disponível, mas nenhum container foi encontrado.</div></td></tr>';
      return;
    }
    body.innerHTML = data.containers.map((container) => {
      const stateKind = container.state === 'running' ? 'ok' : container.state === 'exited' ? 'muted' : 'warn';
      const controls = permissions().docker_power ? `<div class="button-row"><button class="button secondary small docker-action" data-id="${escapeHtml(container.id)}" data-action="start">Start</button><button class="button secondary small docker-action" data-id="${escapeHtml(container.id)}" data-action="restart">Restart</button><button class="button danger subtle small docker-action" data-id="${escapeHtml(container.id)}" data-action="stop">Stop</button></div>` : '<span class="badge muted">SOMENTE LEITURA</span>';
      return `<tr><td><strong>${escapeHtml(container.name || container.id)}</strong></td><td>${escapeHtml(container.image)}</td><td><span class="badge ${stateKind}">${escapeHtml(container.state)}</span></td><td>${escapeHtml(container.ports || '--')}</td><td>${escapeHtml(container.compose_project || '--')}</td><td class="actions-col">${controls}</td></tr>`;
    }).join('');
    $$('.docker-action', body).forEach((button) => button.addEventListener('click', () => confirmDockerAction(button.dataset.id, button.dataset.action)));
  }

  function confirmDockerAction(containerId, action) {
    openModal({
      title: `Docker ${action}`,
      kicker: 'Ação administrativa',
      body: `<p>Você está prestes a executar <strong>docker ${escapeHtml(action)} ${escapeHtml(containerId)}</strong> na VM conectada.</p><p>Confirme o alvo antes de continuar.</p>`,
      actions: [
        { label: 'Cancelar', className: 'secondary' },
        { label: 'Confirmar ação', className: action === 'stop' ? 'danger' : 'primary', onClick: async () => {
          await api('docker/action', { profile_id: state.profileId, container_id: containerId, action, confirmed: true });
          toast(`Ação Docker ${action} enviada.`, 'success');
          await loadDocker(false);
        }}
      ]
    });
  }

  async function loadProxmox(showToast = false) {
    if (!state.bootstrap || !state.bootstrap.ssh.connected) {
      $('#proxmoxTableBody').innerHTML = '<tr><td colspan="7"><div class="empty-state">Conecte o SSH antes de acessar a API interna do Proxmox.</div></td></tr>';
      return;
    }
    const button = $('#refreshProxmoxBtn');
    setLoading(button, true);
    try {
      const vms = await api('proxmox/list', { profile_id: state.profileId, environment_id: state.environmentId });
      state.proxmoxVms = Array.isArray(vms) ? vms : [];
      renderProxmox(vms);
      if (showToast) toast('Recursos do Proxmox atualizados.', 'success');
    } catch (error) {
      $('#proxmoxTableBody').innerHTML = `<tr><td colspan="7"><div class="empty-state">${escapeHtml(error.message)}</div></td></tr>`;
      if (showToast) toast(error.message, 'error');
    } finally {
      setLoading(button, false);
    }
  }

  function renderProxmox(vms) {
    const body = $('#proxmoxTableBody');
    if (!vms || !vms.length) {
      body.innerHTML = '<tr><td colspan="7"><div class="empty-state">Nenhuma VM autorizada foi retornada para este perfil.</div></td></tr>';
      return;
    }
    body.innerHTML = vms.map((vm) => {
      const running = vm.status === 'running';
      const controls = permissions().proxmox_power
        ? `<div class="button-row"><button class="button secondary small proxmox-action" data-vm='${escapeHtml(JSON.stringify(vm))}' data-action="start" ${running ? 'disabled' : ''}>Start</button><button class="button secondary small proxmox-action" data-vm='${escapeHtml(JSON.stringify(vm))}' data-action="reboot" ${!running ? 'disabled' : ''}>Reboot</button><button class="button danger subtle small proxmox-action" data-vm='${escapeHtml(JSON.stringify(vm))}' data-action="stop" ${!running ? 'disabled' : ''}>Stop</button></div>`
        : '<span class="badge muted">SOMENTE LEITURA</span>';
      return `<tr><td><code>${vm.vmid}</code></td><td><strong>${escapeHtml(vm.name)}</strong><br><span class="log-time">${escapeHtml(vm.node || '--')} · ${escapeHtml(vm.vm_type || 'qemu')}</span></td><td><span class="badge ${running ? 'ok' : 'muted'}">${escapeHtml((vm.status || 'unknown').toUpperCase())}</span></td><td>${vm.cpu === null || vm.cpu === undefined ? '--' : `${(vm.cpu * 100).toFixed(1)}%`}</td><td>${vm.maxmem ? `${bytes(vm.mem)} / ${bytes(vm.maxmem)}` : bytes(vm.mem)}</td><td>${duration(vm.uptime)}</td><td class="actions-col">${controls}</td></tr>`;
    }).join('');
    $$('.proxmox-action', body).forEach((button) => button.addEventListener('click', () => {
      let vm;
      try { vm = JSON.parse(button.dataset.vm); } catch (_) { return; }
      confirmProxmoxAction(vm, button.dataset.action);
    }));
  }

  function confirmProxmoxAction(vm, action) {
    openModal({
      title: `${action.toUpperCase()} na VM ${vm.vmid}`,
      kicker: 'Proxmox VE',
      body: `<p>Alvo: <strong>${escapeHtml(vm.name)}</strong> (VMID ${vm.vmid}) no node <strong>${escapeHtml(vm.node || '--')}</strong>.</p><p>A API Token configurada também precisa possuir a ACL correspondente. A interface local não concede privilégios no servidor.</p>`,
      actions: [
        { label: 'Cancelar', className: 'secondary' },
        { label: 'Confirmar ação', className: action === 'stop' ? 'danger' : 'primary', onClick: async () => {
          const result = await api('proxmox/action', { profile_id: state.profileId, environment_id: state.environmentId, vmid: vm.vmid, node: vm.node, vm_type: vm.vm_type || 'qemu', action, confirmed: true });
          toast(result.task_id ? `Task criada: ${result.task_id}` : 'Ação enviada ao Proxmox.', 'success');
          window.setTimeout(() => loadProxmox(false), 900);
        }}
      ]
    });
  }

  async function openCreateProxmoxVm() {

    if (
      !state.bootstrap ||
      !state.bootstrap.ssh.connected
    ) {
      toast(
        'Conecte o SSH antes de criar uma VM.',
        'error'
      );
      return;
    }

    if (
      !currentProfile() ||
      currentProfile().role !== 'admin'
    ) {
      toast(
        'Somente o perfil Administrador do laboratório pode criar VMs.',
        'error'
      );
      return;
    }

    let options;

    try {
      options = await api(
        'proxmox/create/options',
        {
          profile_id: state.profileId,
          environment_id: state.environmentId
        }
      );
    } catch (error) {
      toast(
        error.message,
        'error'
      );
      return;
    }

    const nodes =
      Array.isArray(options.nodes)
        ? options.nodes
        : [];

    const storages =
      Array.isArray(options.storages)
        ? options.storages
        : [];

    const nodeOptions =
      nodes.length
        ? nodes.map(
            (value) =>
              `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`
          ).join('')
        : '<option value="">Nenhum node detectado</option>';

    const storageOptions =
      storages.length
        ? storages.map(
            (value) =>
              `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`
          ).join('')
        : '<option value="local-lvm">local-lvm</option>';

    openModal({
      title: 'Criar máquina virtual',

      kicker:
        'Proxmox VE · operação administrativa',

      body: `
        <div class="form-stack">

          <div class="notice warning">
            <span>${icon('shield')}</span>

            <p>
              A VM será criada pela API oficial.
              O token precisa possuir permissão
              para criação de VMs e alocação no
              storage escolhido.
            </p>
          </div>

          <div class="field-row">

            <label class="field">
              <span>VMID</span>

              <input
                id="createVmId"
                type="number"
                min="100"
                value="${Number(options.next_vmid) || 100}"
              >
            </label>

            <label class="field">
              <span>Nome</span>

              <input
                id="createVmName"
                type="text"
                maxlength="63"
                placeholder="pesquisa-law"
              >
            </label>

          </div>

          <div class="field-row">

            <label class="field">
              <span>Node</span>

              <select id="createVmNode">
                ${nodeOptions}
              </select>
            </label>

            <label class="field">
              <span>Storage</span>

              <select id="createVmStorage">
                ${storageOptions}
              </select>
            </label>

          </div>

          <div class="field-row">

            <label class="field">
              <span>CPU (cores)</span>

              <input
                id="createVmCores"
                type="number"
                min="1"
                max="64"
                value="2"
              >
            </label>

            <label class="field">
              <span>Memória (MB)</span>

              <input
                id="createVmMemory"
                type="number"
                min="512"
                step="256"
                value="2048"
              >
            </label>

            <label class="field">
              <span>Disco (GB)</span>

              <input
                id="createVmDisk"
                type="number"
                min="4"
                value="20"
              >
            </label>

          </div>

          <label class="field">

            <span>Bridge de rede</span>

            <input
              id="createVmBridge"
              type="text"
              value="${escapeHtml(options.default_bridge || 'vmbr0')}"
              spellcheck="false"
            >

          </label>

          <label class="field">

            <span>ISO opcional</span>

            <input
              id="createVmIso"
              type="text"
              placeholder="local:iso/debian-13.iso"
              spellcheck="false"
            >

            <small>
              Se ficar vazio, será criada
              uma VM sem mídia de instalação.
            </small>

          </label>

        </div>
      `,

      actions: [

        {
          label: 'Cancelar',
          className: 'secondary'
        },

        {
          label: 'Criar VM',
          className: 'primary',
          close: false,

          onClick: async () => {

            const payload = {

              profile_id:
                state.profileId,

              environment_id:
                state.environmentId,

              vmid:
                Number(
                  $('#createVmId').value
                ),

              name:
                $('#createVmName')
                  .value
                  .trim(),

              node:
                $('#createVmNode')
                  .value
                  .trim(),

              storage:
                $('#createVmStorage')
                  .value
                  .trim(),

              cores:
                Number(
                  $('#createVmCores').value
                ),

              memory_mb:
                Number(
                  $('#createVmMemory').value
                ),

              disk_gb:
                Number(
                  $('#createVmDisk').value
                ),

              bridge:
                $('#createVmBridge')
                  .value
                  .trim()
                  || 'vmbr0',

              iso:
                $('#createVmIso')
                  .value
                  .trim(),

              confirmed: true
            };

            if (!payload.name) {
              throw new Error(
                'Informe o nome da VM.'
              );
            }

            const result =
              await api(
                'proxmox/create',
                payload
              );

            closeModal();

            toast(
              `VM ${result.vmid} (${result.name}) criada no node ${result.node}.`,
              'success'
            );

            window.setTimeout(
              () => loadProxmox(false),
              1000
            );
          }
        }
      ]
    });
  }


  function openProxmoxCredentials() {
    const prefs = state.bootstrap.proxmox_preferences || {};
    openModal({
      title: 'API Token do Proxmox',
      kicker: 'Credenciais de privilégio mínimo',
      body: `<div class="form-stack">
        <label class="field"><span>Usuário da API</span><input id="modalPveUser" type="text" spellcheck="false" value="${escapeHtml(prefs.api_user || '')}" placeholder="ex.: pibic-app@pve"></label>
        <label class="field"><span>Nome do token</span><input id="modalPveTokenName" type="text" spellcheck="false" value="${escapeHtml(prefs.token_name || '')}" placeholder="ex.: pibic-lab"></label>
        <label class="field"><span>Secret do token</span><input id="modalPveTokenSecret" type="password" autocomplete="off" placeholder="${prefs.has_token_secret ? 'Já existe um secret salvo; deixe vazio para manter' : 'Armazenado apenas no keyring do sistema'}"></label>
        <div class="notice warning"><span>${icon('shield')}</span><p>Use um usuário técnico e um API Token com privilege separation e ACL mínima. Não use root@pam com acesso global.</p></div>
      </div>`,
      actions: [
        { label: 'Cancelar', className: 'secondary' },
        { label: 'Salvar no keyring', className: 'primary', close: false, onClick: async () => {
          const data = await api('proxmox/credentials', { profile_id: state.profileId, api_user: $('#modalPveUser').value.trim(), token_name: $('#modalPveTokenName').value.trim(), token_secret: $('#modalPveTokenSecret').value });
          $('#modalPveTokenSecret').value = '';
          state.bootstrap.proxmox_preferences = data;
          closeModal();
          toast('Credenciais do Proxmox atualizadas.', 'success');
        }}
      ]
    });
  }

  async function loadLogs(showToast = false) {
    try {
      state.logs = await api('logs', { profile_id: state.profileId, limit: 250 });
      renderLogs();
      if (showToast) toast('Logs atualizados.', 'success');
    } catch (error) {
      $('#logsList').innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
      if (showToast) toast(error.message, 'error');
    }
  }

  function renderLogs() {
    const filter = ($('#logFilter').value || '').trim().toLowerCase();
    const items = state.logs.filter((item) => !filter || [item.category, item.action, item.actor, item.target, JSON.stringify(item.details || {})].some((value) => String(value || '').toLowerCase().includes(filter)));
    if (!items.length) {
      $('#logsList').innerHTML = '<div class="empty-state">Nenhum evento corresponde ao filtro atual.</div>';
      return;
    }
    $('#logsList').innerHTML = items.map((item) => `<div class="log-row"><span class="log-time">${escapeHtml(formatTimestamp(item.timestamp))}</span><span class="log-category">${escapeHtml(item.category)}</span><span class="log-action">${escapeHtml(item.action)}</span><span class="log-target" title="${escapeHtml(item.target || item.actor || '')}">${escapeHtml(item.target || item.actor || '--')}</span></div>`).join('');
  }

  function formatTimestamp(value) {
    try { return new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'medium' }).format(new Date(value)); }
    catch (_) { return value || '--'; }
  }

  async function exportDiagnostics() {
    const button = $('#exportDiagnosticsBtn');
    setLoading(button, true);
    try {
      const result = await api('diagnostics/export', { profile_id: state.profileId, environment_id: state.environmentId });
      openModal({
        title: 'Diagnóstico exportado',
        kicker: 'Arquivo local sanitizado',
        body: `<p>O pacote foi criado no diretório de dados do aplicativo.</p><span class="fingerprint">${escapeHtml(result.path)}</span><p>Revise o conteúdo antes de compartilhar externamente, mesmo com a sanitização automática.</p>`,
        actions: [{ label: 'Fechar', className: 'primary' }]
      });
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      setLoading(button, false);
    }
  }

  async function saveProfile(event) {
    event.preventDefault();
    const vmids = $('#profileVmids').value.split(',').map((item) => item.trim()).filter(Boolean).map(Number);
    if (vmids.some((item) => !Number.isInteger(item) || item < 0)) {
      toast('VMIDs devem ser números inteiros separados por vírgula.', 'error');
      return;
    }
    try {
      const current = currentProfile();
      const saved = await api('profile/save', {
        id: Number($('#profileId').value) || null,
        display_name: $('#profileDisplayName').value.trim(),
        role: $('#profileRole').value,
        ssh_username: $('#profileSshUsername').value.trim(),
        assigned_vmids: vmids,
        can_proxmox_power: $('#profileCanPower').checked,
        can_install_services: $('#profileCanInstall').checked,
        created_at: current.created_at
      });
      toast('Perfil local salvo.', 'success');
      await loadBootstrap(saved.id, state.environmentId);
    } catch (error) {
      toast(error.message, 'error');
    }
  }

  async function saveEnvironment(event) {
    event.preventDefault();
    try {
      const saved = await api('environment/save', {
        id: Number($('#environmentId').value) || null,
        name: $('#environmentName').value.trim(),
        gateway_host: $('#environmentGateway').value.trim(),
        ssh_port: Number($('#environmentSshPort').value),
        proxmox_internal_host: $('#environmentProxmoxHost').value.trim(),
        proxmox_port: Number($('#environmentProxmoxPort').value),
        zerotier_network_id: $('#environmentNetworkId').value.trim(),
        enabled: true
      });
      state.hostKey = null;
      toast('Ambiente salvo. Revalide a conectividade e a host key.', 'success');
      await loadBootstrap(state.profileId, saved.id);
    } catch (error) {
      toast(error.message, 'error');
    }
  }

  async function saveAppSettings(event) {
    event.preventDefault();
    const current = state.bootstrap.settings || {};
    const verify = $('#verifyProxmoxTls').checked;
    const unsafe = $('#allowUnsafeTls').checked;
    if (!verify && !unsafe) {
      toast('Se a validação TLS for desativada, o modo inseguro precisa ser explicitamente autorizado.', 'error');
      return;
    }
    try {
      const saved = await api('settings', {
        ...current,
        verify_proxmox_tls: verify,
        proxmox_ca_path: $('#proxmoxCaPath').value.trim(),
        allow_unsafe_proxmox_tls: unsafe
      });
      state.bootstrap.settings = saved;
      toast('Configurações de segurança salvas.', 'success');
    } catch (error) {
      toast(error.message, 'error');
    }
  }

  function openZeroTierJoin() {
    const env = currentEnvironment();
    openModal({
      title: 'Entrar em uma rede ZeroTier',
      kicker: 'Conectividade local',
      body: `<div class="form-stack"><label class="field"><span>Network ID</span><input id="modalNetworkId" type="text" maxlength="16" spellcheck="false" value="${escapeHtml(env.zerotier_network_id || '')}" placeholder="16 caracteres hexadecimais"></label><p>O aplicativo chama somente o comando local de entrada na rede. A autorização do dispositivo continua sob controle do administrador e nenhum token do ZeroTier Central é embutido no cliente.</p></div>`,
      actions: [
        { label: 'Cancelar', className: 'secondary' },
        { label: 'Entrar na rede', className: 'primary', close: false, onClick: async () => {
          const networkId = $('#modalNetworkId').value.trim();
          const result = await api('zerotier/join', { environment_id: state.environmentId, network_id: networkId });
          closeModal();
          toast(result.output || 'Solicitação enviada ao ZeroTier.', 'success');
          await loadBootstrap(state.profileId, state.environmentId);
        }}
      ]
    });
  }

  async function onProfileChanged() {
    const newId = Number($('#profileSelect').value);
    if (newId === state.profileId) return;
    if (state.terminal.sessionId) await closeTerminal(false);
    if (state.bootstrap && state.bootstrap.ssh.connected) {
      try { await api('ssh/disconnect', { profile_id: state.profileId }); } catch (_) { /* melhor esforço */ }
    }
    state.hostKey = null;
    state.dashboard = null;
    await loadBootstrap(newId, state.environmentId);
  }

  async function onEnvironmentChanged() {
    const newId = Number($('#environmentSelect').value);
    if (newId === state.environmentId) return;
    if (state.terminal.sessionId) await closeTerminal(false);
    if (state.bootstrap && state.bootstrap.ssh.connected) {
      try { await api('ssh/disconnect', { profile_id: state.profileId }); } catch (_) { /* melhor esforço */ }
    }
    state.hostKey = null;
    await loadBootstrap(state.profileId, newId);
  }

  function bindEvents() {
    $('#mainNav').addEventListener('click', (event) => {
      const button = event.target.closest('[data-view]');
      if (button) showView(button.dataset.view);
    });
    document.addEventListener('click', (event) => {
      const target = event.target.closest('[data-go-view]');
      if (!target) return;
      const view = target.dataset.goView;
      if (view === 'terminal') openTerminal(); else showView(view);
    });
    $('#refreshCurrentBtn').addEventListener('click', refreshCurrent);
    $('#profileSelect').addEventListener('change', onProfileChanged);
    $('#environmentSelect').addEventListener('change', onEnvironmentChanged);
    $('#sshAuthMethod').addEventListener('change', updateAuthFields);
    $('#checkConnectivityBtn').addEventListener('click', () => refreshConnectivity(true));
    $('#dashboardConnectivityBtn').addEventListener('click', () => { showView('connection'); refreshConnectivity(false); });
    $('#openZtJoinBtn').addEventListener('click', openZeroTierJoin);
    $('#probeHostKeyBtn').addEventListener('click', () => probeHostKey({ promptTrust: true }));
    $('#sshForm').addEventListener('submit', connectSsh);
    $('#disconnectSshBtn').addEventListener('click', disconnectSsh);
    $('#heroConnectBtn').addEventListener('click', () => state.bootstrap && state.bootstrap.ssh.connected ? openTerminal() : showView('connection'));
    $('#dashboardRefreshBtn').addEventListener('click', () => loadDashboard(true));
    $('#terminalNewBtn').addEventListener('click', async () => { if (state.terminal.sessionId) await closeTerminal(false); await openTerminal(); });
    $('#terminalCloseBtn').addEventListener('click', () => closeTerminal(true));
    $('#detectServicesBtn').addEventListener('click', () => detectServices(true));
    $('#refreshCatalogBtn').addEventListener('click', () => loadCatalog(true));
    $('#refreshJobsBtn').addEventListener('click', () => loadJobs(true));
    $('#refreshDockerBtn').addEventListener('click', () => loadDocker(true));
    $('#createProxmoxVmBtn').addEventListener('click', openCreateProxmoxVm);
    $('#proxmoxCredentialBtn').addEventListener('click', openProxmoxCredentials);
    $('#refreshProxmoxBtn').addEventListener('click', () => loadProxmox(true));
    $('#refreshLogsBtn').addEventListener('click', () => loadLogs(true));
    $('#logFilter').addEventListener('input', renderLogs);
    $('#exportDiagnosticsBtn').addEventListener('click', exportDiagnostics);
    $('#profileForm').addEventListener('submit', saveProfile);
    $('#environmentForm').addEventListener('submit', saveEnvironment);
    $('#appSettingsForm').addEventListener('submit', saveAppSettings);
    $('#modalCloseBtn').addEventListener('click', closeModal);
    $('#modalBackdrop').addEventListener('click', (event) => { if (event.target === $('#modalBackdrop')) closeModal(); });
    document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && !$('#modalBackdrop').classList.contains('hidden')) closeModal(); });
    $('#terminalFallbackInput').addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        const input = event.currentTarget;
        sendTerminalText(input.value + '\r');
        input.value = '';
      } else if (event.ctrlKey && event.key.toLowerCase() === 'c') {
        event.preventDefault();
        sendTerminalText('\x03');
      }
    });
    window.addEventListener('resize', ensureTerminalSizing);
    window.addEventListener('beforeunload', () => { stopTerminalPolling(); });
  }

  async function init() {
    const root = $('#appShell');
    if (!root) return;

    // O Vela injeta esta página depois do DOMContentLoaded do shell. Usamos a
    // identidade do elemento raiz para inicializar exatamente uma vez por view
    // renderizada, inclusive após uma navegação/reload do próprio Vela.
    if (window.__PIBIC_LAB_ACTIVE_ROOT__ === root) return;
    window.__PIBIC_LAB_ACTIVE_ROOT__ = root;

    if (window.renderPibicIcons) window.renderPibicIcons(root);
    bindEvents();
    $('#terminalEngineLabel').textContent = typeof window.Terminal === 'function' ? 'xterm.js disponível' : 'Terminal básico disponível';
    await loadBootstrap();
  }

  window.PIBICLab = {
    state,
    api,
    openModal,
    closeModal,
    toast,
    escapeHtml,
    icon,
    bytes,
    currentProfile,
    currentEnvironment,
    permissions,
    loadProxmox
  };

  function boot() {
    Promise.resolve(init()).catch((error) => {
      console.error('[PIBIC LAB] Erro ao inicializar a interface:', error);
      const region = $('#toastRegion');
      if (region) toast(error.message || String(error), 'error', 'Falha ao iniciar a interface');
    });
  }

  // Em uma página HTML normal, aguarda DOMContentLoaded. Quando o HTML é
  // carregado pelo router do Vela, esse evento já aconteceu e inicializamos na
  // hora. Esse era o motivo de os botões aparecerem, mas não responderem.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
