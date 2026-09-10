(() => {
  'use strict';

  const wait = () => {
    if (!window.PIBICLab) {
      window.setTimeout(wait, 30);
      return;
    }
    install(window.PIBICLab);
  };

  function install(Lab) {
    const $ = (selector, root = document) => root.querySelector(selector);
    const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
    const esc = Lab.escapeHtml;
    const state = Lab.state;
    let installed = false;

    function bind() {
      if (installed) return;
      const createBtn = $('#createProxmoxVmBtn');
      const webBtn = $('#openProxmoxWebBtn');
      if (!createBtn || !webBtn) {
        window.setTimeout(bind, 50);
        return;
      }
      installed = true;

      // Captura o clique antes do listener antigo do primeiro formulário.
      createBtn.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopImmediatePropagation();
        openWizard().catch((error) => Lab.toast(error.message, 'error'));
      }, true);

      webBtn.addEventListener('click', (event) => {
        event.preventDefault();
        openWebPanel().catch((error) => Lab.toast(error.message, 'error'));
      });
    }

    function profileIsAdmin() {
      const profile = Lab.currentProfile();
      return profile && profile.role === 'admin';
    }

    async function openWebPanel() {
      if (!state.bootstrap || !state.bootstrap.ssh.connected) {
        throw new Error('Conecte o SSH antes de abrir o painel Web do Proxmox.');
      }
      const data = await Lab.api('proxmox/web/open', {
        profile_id: state.profileId,
        environment_id: state.environmentId
      });

      Lab.openModal({
        title: 'Abrir Proxmox Web',
        kicker: 'Túnel SSH local',
        body: `<div class="form-stack">
          <div class="notice warning"><span>${Lab.icon('shield')}</span><p>O API Token autentica as chamadas nativas do PIBIC LAB, mas não cria uma sessão da Web UI. A interface Web do Proxmox usa login/ticket próprio.</p></div>
          <label class="field"><span>Endereço local do túnel</span><input id="pveWebUrl" value="${esc(data.url)}" readonly></label>
          <p>${esc(data.note || '')}</p>
          <p>Se o certificado próprio do Proxmox for bloqueado pelo WebView, use “Abrir no navegador” e aceite o certificado somente se você reconhecer o servidor.</p>
        </div>`,
        actions: [
          { label: 'Fechar', className: 'secondary' },
          { label: 'Abrir no navegador', className: 'secondary', close: false, onClick: async () => {
            const result = await window.pywebview.api.open_external_browser(data.url);
            if (!result || result.ok === false) throw new Error((result && result.error) || 'Não foi possível abrir o navegador.');
          }},
          { label: 'Abrir dentro do app', className: 'primary', close: false, onClick: async () => {
            const result = await window.pywebview.api.open_proxmox_window(data.url);
            if (!result || result.ok === false) throw new Error((result && result.error) || 'Não foi possível abrir a janela Proxmox.');
          }}
        ]
      });
    }

    async function openWizard() {
      if (!state.bootstrap || !state.bootstrap.ssh.connected) {
        throw new Error('Conecte o SSH antes de provisionar uma VM.');
      }
      if (!profileIsAdmin()) {
        throw new Error('Troque o perfil local para Administrador do laboratório.');
      }

      Lab.openModal({
        title: 'Assistente de máquina virtual',
        kicker: 'Proxmox VE · provisionamento pela API oficial',
        body: busyHtml('Preparando o assistente', 'Consultando nodes, VMIDs, VMs e storages no Proxmox...'),
        actions: [{ label: 'Fechar', className: 'secondary' }]
      });

      const modal = $('#modalBackdrop .modal');
      if (modal) modal.classList.add('pve-wizard-modal');

      try {
        const options = await Lab.api('proxmox/install/options', {
          profile_id: state.profileId,
          environment_id: state.environmentId
        });

        const nodes = options.nodes || [];
        const vms = options.vms || [];
        if (!nodes.length) throw new Error('O token não retornou nenhum node do Proxmox.');

        const body = wizardHtml(options, vms);
        Lab.openModal({
          title: 'Assistente de máquina virtual',
          kicker: 'Proxmox VE · provisionamento pela API oficial',
          body,
          actions: [{ label: 'Fechar', className: 'secondary' }]
        });
        const wizardModal = $('#modalBackdrop .modal');
        if (wizardModal) wizardModal.classList.add('pve-wizard-modal');
        attachWizardHandlers(options, vms);
        await refreshNodeOptions(options.default_node || nodes[0]);
        updateModeUi();
        updateSummary();
      } catch (error) {
        Lab.closeModal();
        throw error;
      }
    }

    function option(value, label, selected = false) {
      return `<option value="${esc(value)}" ${selected ? 'selected' : ''}>${esc(label)}</option>`;
    }

    function wizardHtml(options, vms) {
      const nodeOptions = (options.nodes || []).map((node) => option(node, node, node === options.default_node)).join('');
      const vmOptions = [option('', 'Selecione uma VM/template')].concat(
        vms.map((vm) => option(
          `${vm.node}|${vm.vmid}`,
          `${vm.vmid} · ${vm.name} · ${vm.node}${vm.template ? ' · TEMPLATE' : ''}`
        ))
      ).join('');

      return `<div class="pve-wizard" id="pveWizard">
        <div class="pve-wizard-tabs">
          ${['Geral','SO','Sistema','Disco','CPU','Memória','Rede','Confirmar'].map((name, i) => `<button type="button" class="pve-wizard-tab ${i === 0 ? 'active' : ''}" data-step="${i}">${i + 1}. ${name}</button>`).join('')}
        </div>

        <section class="pve-wizard-step active" data-step-panel="0">
          <div class="pve-wizard-grid-2">
            <label class="field"><span>Modo de provisionamento</span><select id="pveMode"><option value="iso">Nova VM / instalação por ISO</option><option value="clone">Clonar VM ou template existente</option></select></label>
            <label class="field"><span>Node de destino</span><select id="pveNode">${nodeOptions}</select></label>
            <label class="field"><span>VMID</span><input id="pveVmid" type="number" min="100" value="${Number(options.next_vmid) || 100}"></label>
            <label class="field"><span>Nome</span><input id="pveName" type="text" maxlength="63" placeholder="pesquisa-law"></label>
          </div>
          <div class="pve-source-panel hidden" id="pveClonePanel">
            <label class="field"><span>VM/template de origem</span><select id="pveSourceVm">${vmOptions}</select><small>O combobox é carregado de /cluster/resources?type=vm.</small></label>
          </div>
        </section>

        <section class="pve-wizard-step" data-step-panel="1">
          <div id="pveIsoInstallPanel" class="form-stack">
            <label class="field"><span>ISO disponível no Proxmox</span><select id="pveIso"><option value="">Sem ISO / instalar depois</option></select><small>Lista carregada diretamente dos storages que suportam conteúdo ISO.</small></label>
            <div class="pve-url-panel">
              <div class="card-header"><div><p class="card-kicker">Download from URL</p><h3>Baixar ISO diretamente pelo node</h3></div></div>
              <div class="pve-wizard-grid-2">
                <label class="field"><span>URL</span><input id="pveIsoUrl" type="url" placeholder="https://.../debian.iso" spellcheck="false"></label>
                <label class="field"><span>Storage para ISO</span><select id="pveIsoStorage"></select></label>
              </div>
              <div class="pve-url-actions">
                <button type="button" class="button secondary" id="pveQueryUrlBtn">Consultar URL</button>
                <label class="check-row"><input type="checkbox" id="pveUrlVerify" checked><span>Validar certificado HTTPS da URL</span></label>
              </div>
              <div class="pve-url-meta"><div><strong id="pveUrlFilename">--</strong><span>arquivo</span></div><div><strong id="pveUrlSize">--</strong><span>tamanho</span></div><div><strong id="pveUrlMime">--</strong><span>MIME</span></div></div>
              <div class="pve-wizard-grid-2">
                <label class="field"><span>Nome do arquivo</span><input id="pveDownloadFilename" type="text" placeholder="arquivo.iso"></label>
                <label class="field"><span>Algoritmo de checksum</span><select id="pveChecksumAlg"><option value="">Sem checksum</option><option value="sha256">SHA-256</option><option value="sha512">SHA-512</option><option value="sha1">SHA-1</option><option value="md5">MD5</option></select></label>
              </div>
              <label class="field"><span>Checksum</span><input id="pveChecksum" type="text" spellcheck="false" placeholder="Opcional, mas recomendado"></label>
              <div class="pve-url-actions"><button type="button" class="button primary" id="pveDownloadIsoBtn">Baixar ISO no Proxmox</button><span class="pve-download-progress" id="pveDownloadStatus"></span></div>
            </div>
          </div>
          <div id="pveCloneHint" class="notice hidden"><span>${Lab.icon('gitBranch')}</span><p>No modo clone, a mídia/OS vem da VM ou template de origem. As opções de ISO são ignoradas.</p></div>
        </section>

        <section class="pve-wizard-step" data-step-panel="2">
          <div class="pve-wizard-grid-2">
            <label class="field"><span>Tipo de sistema</span><select id="pveOsType"><option value="l26">Linux 2.6+ / atual</option><option value="win11">Windows 11 / 2022</option><option value="win10">Windows 10 / 2016 / 2019</option><option value="other">Outro</option></select></label>
            <label class="field"><span>Machine</span><select id="pveMachine"><option value="q35">q35</option><option value="pc">i440fx / pc</option></select></label>
            <label class="field"><span>BIOS</span><select id="pveBios"><option value="seabios">SeaBIOS</option><option value="ovmf">OVMF (UEFI)</option></select></label>
            <label class="check-row"><input id="pveAgent" type="checkbox" checked><span>Habilitar QEMU Guest Agent</span></label>
            <label class="check-row"><input id="pveOnBoot" type="checkbox"><span>Iniciar junto com o node</span></label>
          </div>
        </section>

        <section class="pve-wizard-step" data-step-panel="3">
          <div class="pve-wizard-grid-3">
            <label class="field"><span>Storage do disco</span><select id="pveDiskStorage"></select><small>Somente storages que suportam images.</small></label>
            <label class="field"><span>Tamanho (GB)</span><input id="pveDiskGb" type="number" min="4" value="20"></label>
            <label class="field"><span>Barramento</span><select id="pveDiskBus"><option value="scsi">SCSI</option><option value="virtio">VirtIO Block</option><option value="sata">SATA</option></select></label>
          </div>
        </section>

        <section class="pve-wizard-step" data-step-panel="4">
          <div class="pve-wizard-grid-3">
            <label class="field"><span>Sockets</span><input id="pveSockets" type="number" min="1" max="8" value="1"></label>
            <label class="field"><span>Cores</span><input id="pveCores" type="number" min="1" max="128" value="2"></label>
            <label class="field"><span>Tipo de CPU</span><select id="pveCpuType"><option value="x86-64-v2-AES">x86-64-v2-AES</option><option value="host">host</option><option value="kvm64">kvm64</option></select></label>
          </div>
        </section>

        <section class="pve-wizard-step" data-step-panel="5">
          <div class="pve-wizard-grid-2">
            <label class="field"><span>Memória (MB)</span><input id="pveMemory" type="number" min="512" step="256" value="2048"></label>
            <label class="field"><span>Balloon mínimo (MB)</span><input id="pveBalloon" type="number" min="0" step="256" value="0"><small>0 desativa ballooning dinâmico.</small></label>
          </div>
        </section>

        <section class="pve-wizard-step" data-step-panel="6">
          <div class="pve-wizard-grid-3">
            <label class="field"><span>Bridge</span><select id="pveBridge"></select></label>
            <label class="field"><span>Modelo da NIC</span><select id="pveNetModel"><option value="virtio">VirtIO</option><option value="e1000">Intel E1000</option><option value="vmxnet3">VMware vmxnet3</option><option value="rtl8139">Realtek RTL8139</option></select></label>
            <label class="field"><span>VLAN tag</span><input id="pveVlan" type="number" min="1" max="4094" placeholder="Sem VLAN"></label>
            <label class="check-row"><input id="pveFirewall" type="checkbox" checked><span>Firewall na interface da VM</span></label>
          </div>
        </section>

        <section class="pve-wizard-step" data-step-panel="7">
          <div class="notice warning"><span>${Lab.icon('shield')}</span><p>Revise antes de executar. A criação/clonagem acontece no Proxmox e gera uma task auditável.</p></div>
          <div class="pve-summary"><div class="pve-summary-grid" id="pveSummary"></div></div>
        </section>

        <div class="pve-wizard-nav">
          <button type="button" class="button secondary" id="pvePrevBtn" disabled>Anterior</button>
          <div class="right"><button type="button" class="button secondary" id="pveNextBtn">Próximo</button><button type="button" class="button primary hidden" id="pveCreateBtn">Executar</button></div>
        </div>
      </div>`;
    }

    let currentStep = 0;
    let nodeOptions = null;
    let baseOptions = null;
    let activeRequestController = null;
    let activeTask = null;
    let operationTimer = null;
    let operationStartedAt = 0;
    let cancelRevealTimer = null;

    async function apiAbortable(path, payload, signal) {
      const response = await fetch(`/api/lab/${path}/`, {
        method: 'POST',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload),
        signal
      });
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
    }

    function setButtonBusy(button, busy, text = 'Aguarde...') {
      if (!button) return;
      if (busy) {
        if (!button.dataset.originalHtml) button.dataset.originalHtml = button.innerHTML;
        button.disabled = true;
        button.classList.add('is-busy');
        button.innerHTML = `<span class="pve-mini-spinner"></span>${esc(text)}`;
      } else {
        button.disabled = false;
        button.classList.remove('is-busy');
        if (button.dataset.originalHtml) {
          button.innerHTML = button.dataset.originalHtml;
          delete button.dataset.originalHtml;
        }
      }
    }

    function busyHtml(title, message) {
      return `<div class="pve-busy-panel">
        <span class="pve-busy-spinner"></span>
        <div><strong>${esc(title)}</strong><p>${esc(message)}</p></div>
      </div>`;
    }

    function clearOperationTimers() {
      if (operationTimer) window.clearInterval(operationTimer);
      if (cancelRevealTimer) window.clearTimeout(cancelRevealTimer);
      operationTimer = null;
      cancelRevealTimer = null;
    }

    function beginOperation(title, detail) {
      clearOperationTimers();
      operationStartedAt = Date.now();
      activeTask = null;
      const step = $('[data-step-panel="7"]');
      if (!step) return;
      step.innerHTML = `<div class="pve-operation" id="pveOperationPanel">
        <div class="pve-operation-head">
          <span class="pve-busy-spinner" id="pveOperationSpinner"></span>
          <div class="pve-operation-copy">
            <strong id="pveOperationTitle">${esc(title)}</strong>
            <span id="pveOperationDetail">${esc(detail)}</span>
          </div>
        </div>
        <div class="pve-operation-track"><div class="pve-operation-bar"></div></div>
        <div class="pve-operation-meta">
          <span>Tempo: <strong id="pveOperationElapsed">0 s</strong></span>
          <span class="hidden" id="pveOperationTaskRow">Task: <code id="pveOperationTask"></code></span>
        </div>
        <p class="pve-operation-note" id="pveOperationNote">Não feche o aplicativo durante uma alteração administrativa. Quando o Proxmox devolver um UPID, o cancelamento poderá interromper a task remotamente.</p>
        <div class="pve-operation-actions">
          <button type="button" class="button danger hidden" id="pveCancelOperationBtn">Cancelar operação</button>
          <button type="button" class="button secondary hidden" id="pveOperationCloseBtn">Fechar</button>
        </div>
      </div>`;
      $('#pvePrevBtn').classList.add('hidden');
      $('#pveNextBtn').classList.add('hidden');
      $('#pveCreateBtn').classList.add('hidden');
      $$('.pve-wizard-tab').forEach((button) => { button.disabled = true; });
      operationTimer = window.setInterval(() => {
        const elapsed = $('#pveOperationElapsed');
        if (elapsed) elapsed.textContent = `${Math.floor((Date.now() - operationStartedAt) / 1000)} s`;
      }, 500);
      cancelRevealTimer = window.setTimeout(() => {
        const btn = $('#pveCancelOperationBtn');
        if (btn) btn.classList.remove('hidden');
      }, 3000);
      $('#pveCancelOperationBtn').addEventListener('click', cancelActiveOperation);
      $('#pveOperationCloseBtn').addEventListener('click', () => Lab.closeModal());
    }

    function setOperationTask(node, upid) {
      activeTask = { node, upid };
      const row = $('#pveOperationTaskRow');
      const value = $('#pveOperationTask');
      if (row) row.classList.remove('hidden');
      if (value) value.textContent = upid;
      const btn = $('#pveCancelOperationBtn');
      if (btn) btn.classList.remove('hidden');
    }

    function updateOperation(title, detail) {
      const titleEl = $('#pveOperationTitle');
      const detailEl = $('#pveOperationDetail');
      if (titleEl) titleEl.textContent = title;
      if (detailEl) detailEl.textContent = detail;
    }

    function finishOperation(kind, title, detail) {
      clearOperationTimers();
      const panel = $('#pveOperationPanel');
      if (panel) panel.classList.add(kind);
      const spinner = $('#pveOperationSpinner');
      if (spinner) spinner.classList.add('hidden');
      updateOperation(title, detail);
      const cancel = $('#pveCancelOperationBtn');
      if (cancel) cancel.classList.add('hidden');
      const close = $('#pveOperationCloseBtn');
      if (close) close.classList.remove('hidden');
      const note = $('#pveOperationNote');
      if (note && kind === 'done') note.textContent = 'A task foi confirmada pelo Proxmox. A lista de VMs será atualizada automaticamente.';
    }

    async function cancelActiveOperation() {
      const btn = $('#pveCancelOperationBtn');
      setButtonBusy(btn, true, 'Cancelando...');
      try {
        if (activeTask) {
          updateOperation('Solicitando cancelamento', 'Enviando DELETE da task ao Proxmox...');
          await Lab.api('proxmox/task/cancel', {
            profile_id: state.profileId,
            environment_id: state.environmentId,
            node: activeTask.node,
            upid: activeTask.upid
          });
          updateOperation('Cancelamento solicitado', 'Aguardando o Proxmox encerrar a task...');
          return;
        }
        if (activeRequestController) {
          activeRequestController.abort();
          activeRequestController = null;
          finishOperation(
            'cancelled',
            'Espera local cancelada',
            'O app parou de aguardar a resposta. Como ainda não havia UPID, não é possível garantir que o Proxmox não tenha recebido a solicitação. Confira a lista de VMs/Tasks antes de repetir.'
          );
        }
      } catch (error) {
        updateOperation('Não foi possível cancelar', error.message);
        setButtonBusy(btn, false);
      }
    }

    async function waitForProvisionTask(node, upid) {
      for (let i = 0; i < 900; i += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        const task = await Lab.api('proxmox/task/status', {
          profile_id: state.profileId,
          environment_id: state.environmentId,
          node,
          upid
        });
        if (task.status === 'running') {
          updateOperation('Proxmox executando a task', task.type ? `Etapa: ${task.type}` : 'Aguardando conclusão...');
          continue;
        }
        const exit = task.exitstatus || task.status || 'finalizado';
        if (exit !== 'OK') {
          if (/abort|cancel|interrupted/i.test(exit)) {
            finishOperation('cancelled', 'Operação cancelada', `Proxmox finalizou a task com status: ${exit}`);
          } else {
            finishOperation('error', 'A task terminou com erro', `Status retornado pelo Proxmox: ${exit}`);
          }
          return task;
        }
        finishOperation('done', 'Operação concluída', 'O Proxmox confirmou a conclusão da task com status OK.');
        window.setTimeout(() => Lab.loadProxmox(false), 500);
        return task;
      }
      finishOperation('error', 'Tempo de acompanhamento excedido', 'A task continua sem confirmação após 15 minutos. Ela pode continuar rodando no Proxmox; use o botão de cancelar ou confira Tasks no painel Web.');
      const btn = $('#pveCancelOperationBtn');
      if (btn) btn.classList.remove('hidden');
      return null;
    }

    function attachWizardHandlers(options) {
      currentStep = 0;
      baseOptions = options;
      $$('.pve-wizard-tab').forEach((button) => button.addEventListener('click', () => showStep(Number(button.dataset.step))));
      $('#pvePrevBtn').addEventListener('click', () => showStep(currentStep - 1));
      $('#pveNextBtn').addEventListener('click', () => showStep(currentStep + 1));
      $('#pveCreateBtn').addEventListener('click', executeProvision);
      $('#pveMode').addEventListener('change', () => { updateModeUi(); updateSummary(); });
      $('#pveNode').addEventListener('change', async () => { await refreshNodeOptions($('#pveNode').value); updateSummary(); });
      $('#pveQueryUrlBtn').addEventListener('click', queryUrlMetadata);
      $('#pveDownloadIsoBtn').addEventListener('click', downloadIso);
      $('#pveWizard').addEventListener('input', updateSummary);
      $('#pveWizard').addEventListener('change', updateSummary);
    }

    function showStep(step) {
      currentStep = Math.max(0, Math.min(7, step));
      $$('.pve-wizard-step').forEach((panel) => panel.classList.toggle('active', Number(panel.dataset.stepPanel) === currentStep));
      $$('.pve-wizard-tab').forEach((button) => {
        const n = Number(button.dataset.step);
        button.classList.toggle('active', n === currentStep);
        button.classList.toggle('done', n < currentStep);
      });
      $('#pvePrevBtn').disabled = currentStep === 0;
      $('#pveNextBtn').classList.toggle('hidden', currentStep === 7);
      $('#pveCreateBtn').classList.toggle('hidden', currentStep !== 7);
      if (currentStep === 7) updateSummary();
    }

    function updateModeUi() {
      const clone = $('#pveMode').value === 'clone';
      $('#pveClonePanel').classList.toggle('hidden', !clone);
      $('#pveIsoInstallPanel').classList.toggle('hidden', clone);
      $('#pveCloneHint').classList.toggle('hidden', !clone);
    }

    async function refreshNodeOptions(node) {
      if (!node) return;
      nodeOptions = await Lab.api('proxmox/install/node-options', {
        profile_id: state.profileId,
        environment_id: state.environmentId,
        node
      });
      const disk = $('#pveDiskStorage');
      const isoStorage = $('#pveIsoStorage');
      const iso = $('#pveIso');
      const bridge = $('#pveBridge');

      disk.innerHTML = (nodeOptions.image_storages || []).map((item) => option(item.storage, `${item.storage} · ${item.type || 'storage'}${item.avail ? ' · ' + Lab.bytes(item.avail) + ' livres' : ''}`)).join('');
      isoStorage.innerHTML = (nodeOptions.iso_storages || []).map((item) => option(item.storage, `${item.storage} · ${item.type || 'storage'}`)).join('');
      iso.innerHTML = option('', 'Sem ISO / instalar depois') + (nodeOptions.isos || []).map((item) => option(item.volid, item.volid)).join('');
      bridge.innerHTML = (nodeOptions.bridges || ['vmbr0']).map((item) => option(item, item)).join('');

      if (!disk.value) Lab.toast('Nenhum storage com suporte a images foi retornado para este node.', 'error');
      updateSummary();
    }

    async function queryUrlMetadata() {
      const url = $('#pveIsoUrl').value.trim();
      if (!url) throw new Error('Informe a URL da ISO.');
      const button = $('#pveQueryUrlBtn');
      setButtonBusy(button, true, 'Consultando...');
      try {
        const meta = await Lab.api('proxmox/iso/query', {
          profile_id: state.profileId,
          environment_id: state.environmentId,
          node: $('#pveNode').value,
          url,
          verify_certificates: $('#pveUrlVerify').checked
        });
        $('#pveUrlFilename').textContent = meta.filename || '--';
        $('#pveUrlSize').textContent = meta.size ? Lab.bytes(meta.size) : '--';
        $('#pveUrlMime').textContent = meta.mimetype || '--';
        if (meta.filename) $('#pveDownloadFilename').value = meta.filename;
      } finally {
        setButtonBusy(button, false);
      }
    }

    async function downloadIso() {
      const url = $('#pveIsoUrl').value.trim();
      const filename = $('#pveDownloadFilename').value.trim();
      const storage = $('#pveIsoStorage').value;
      if (!url || !filename || !storage) throw new Error('Informe URL, nome do arquivo e storage de ISO.');
      const button = $('#pveDownloadIsoBtn');
      const status = $('#pveDownloadStatus');
      button.disabled = true;
      status.textContent = 'Iniciando download no node Proxmox...';
      try {
        const result = await Lab.api('proxmox/iso/download', {
          profile_id: state.profileId,
          environment_id: state.environmentId,
          node: $('#pveNode').value,
          storage,
          url,
          filename,
          verify_certificates: $('#pveUrlVerify').checked,
          checksum_algorithm: $('#pveChecksumAlg').value,
          checksum: $('#pveChecksum').value.trim(),
          confirmed: true
        });
        status.textContent = result.task_id ? `Task: ${result.task_id}` : 'Download solicitado.';
        if (result.task_id) await waitForTask($('#pveNode').value, result.task_id, status);
        await refreshNodeOptions($('#pveNode').value);
        const wanted = result.volid;
        if ([...$('#pveIso').options].some((o) => o.value === wanted)) $('#pveIso').value = wanted;
        Lab.toast('ISO disponível no Proxmox.', 'success');
      } finally {
        button.disabled = false;
      }
    }

    async function waitForTask(node, upid, statusEl) {
      for (let i = 0; i < 300; i += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        const task = await Lab.api('proxmox/task/status', {
          profile_id: state.profileId,
          environment_id: state.environmentId,
          node,
          upid
        });
        const running = task.status === 'running';
        statusEl.textContent = running ? 'Download em andamento...' : `Download: ${task.exitstatus || task.status || 'finalizado'}`;
        if (!running) {
          if (task.exitstatus && task.exitstatus !== 'OK') throw new Error(`Download falhou: ${task.exitstatus}`);
          return task;
        }
      }
      throw new Error('O download ainda não terminou após 5 minutos. Verifique Tasks no Proxmox.');
    }

    function value(id, fallback = '') {
      const el = $(id);
      return el ? el.value : fallback;
    }

    function checked(id) {
      const el = $(id);
      return Boolean(el && el.checked);
    }

    function buildPayload() {
      const clone = value('#pveMode') === 'clone';
      const source = value('#pveSourceVm').split('|');
      return {
        mode: clone ? 'clone' : 'iso',
        profile_id: state.profileId,
        environment_id: state.environmentId,
        vmid: Number(value('#pveVmid')),
        name: value('#pveName').trim(),
        node: value('#pveNode'),
        storage: value('#pveDiskStorage'),
        iso: value('#pveIso'),
        ostype: value('#pveOsType'),
        machine: value('#pveMachine'),
        bios: value('#pveBios'),
        agent: checked('#pveAgent'),
        onboot: checked('#pveOnBoot'),
        disk_gb: Number(value('#pveDiskGb')),
        disk_bus: value('#pveDiskBus'),
        sockets: Number(value('#pveSockets')),
        cores: Number(value('#pveCores')),
        cpu_type: value('#pveCpuType'),
        memory_mb: Number(value('#pveMemory')),
        balloon_mb: Number(value('#pveBalloon')),
        bridge: value('#pveBridge'),
        net_model: value('#pveNetModel'),
        vlan_tag: value('#pveVlan') ? Number(value('#pveVlan')) : 0,
        firewall: checked('#pveFirewall'),
        source_node: clone ? (source[0] || '') : '',
        source_vmid: clone ? Number(source[1] || 0) : 0,
        confirmed: true
      };
    }

    function updateSummary() {
      const host = $('#pveSummary');
      if (!host) return;
      const p = buildPayload();
      const items = p.mode === 'clone'
        ? [
            ['Modo','Clone completo'], ['Origem', p.source_vmid ? `${p.source_vmid} @ ${p.source_node}` : 'Não selecionada'], ['Destino', `${p.vmid || '--'} · ${p.name || '--'}`],
            ['Node', p.node || '--'], ['Storage', p.storage || '--']
          ]
        : [
            ['Modo','Instalação por ISO'], ['VM', `${p.vmid || '--'} · ${p.name || '--'}`], ['Node', p.node || '--'], ['ISO', p.iso || 'Sem ISO'],
            ['Disco', `${p.disk_gb || '--'} GB · ${p.storage || '--'} · ${p.disk_bus}`], ['CPU', `${p.sockets} socket(s) × ${p.cores} core(s) · ${p.cpu_type}`],
            ['Memória', `${p.memory_mb || '--'} MB`], ['Sistema', `${p.ostype} · ${p.machine} · ${p.bios}`], ['Rede', `${p.net_model} · ${p.bridge || '--'}${p.vlan_tag ? ' · VLAN ' + p.vlan_tag : ''}`]
          ];
      host.innerHTML = items.map(([k, v]) => `<div class="pve-summary-item"><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`).join('');
    }

    async function executeProvision() {
      const p = buildPayload();
      if (!p.name) throw new Error('Informe o nome da VM.');
      if (!p.vmid) throw new Error('Informe o VMID.');
      if (!p.storage) throw new Error('Nenhum storage de disco válido foi selecionado.');
      if (p.mode === 'clone' && (!p.source_vmid || !p.source_node)) throw new Error('Selecione a VM/template de origem.');

      beginOperation(
        p.mode === 'clone' ? 'Solicitando clonagem' : 'Solicitando criação da VM',
        'Enviando a configuração para a API do Proxmox...'
      );

      activeRequestController = new AbortController();
      try {
        const result = await apiAbortable(
          p.mode === 'clone' ? 'proxmox/clone' : 'proxmox/create',
          p,
          activeRequestController.signal
        );
        activeRequestController = null;

        if (!result.task_id) {
          finishOperation('done', 'Solicitação aceita', `VM ${result.vmid || p.vmid} criada sem UPID retornado.`);
          window.setTimeout(() => Lab.loadProxmox(false), 500);
          return;
        }

        setOperationTask(result.node || p.node, result.task_id);
        updateOperation('Task criada no Proxmox', 'Aguardando a confirmação de conclusão...');
        await waitForProvisionTask(result.node || p.node, result.task_id);
      } catch (error) {
        activeRequestController = null;
        if (error && error.name === 'AbortError') return;
        finishOperation('error', 'Não foi possível concluir', error.message || 'Falha inesperada.');
      }
    }

    bind();
  }

  wait();
})();
