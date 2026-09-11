# Changelog

## v0.1.3 - Workspace multiusuário

- Workspace iniciado com o usuário real da sessão SSH do PIBIC-LAB.
- HOME, UID, shell, terminal e arquivos isolados por integrante.
- Porta loopback dinâmica por instância e Local Port Forward pelo SSH autenticado.
- Encerramento da instância individual ao desconectar ou fechar o Workspace.
- Interface identifica o usuário SSH associado ao Workspace.

## 0.1.1 - 2026-09-09

- Corrige a estrutura dos arquivos estáticos para o comportamento real do `collectstatic` do Vela.
- Remove o namespace duplicado `apps/lab/static/lab/`.
- Corrige o destino de download do xterm.js.
- Adiciona verificação automática de CSS coletado em `scripts/check_environment.py`.
- Adiciona testes de regressão para impedir que o problema de estilos volte a ocorrer.

## 0.1.0 - 2026-09-09

- Entrega inicial do PIBIC LAB.

## 0.1.2

- Corrige a inicialização do JavaScript quando a view é injetada pelo router do Vela depois de `DOMContentLoaded`.
- Adiciona `PIBICBridge` com `get_config`, `get_routes`, `navigate`, `url_for` e `ping` explícitos.
- Adiciona recuperação do bootstrap da shell para a condição de corrida `window.pywebview.api.get_config is not a function` observada em GTK/WebKit.
- Mantém a correção dentro do projeto, sem editar `site-packages` dos colegas.
- Fixa o snapshot do Vela usado pelo projeto no commit `0786ba3` para builds reprodutíveis.

## Proxmox Wizard patch
- Assistente de criação/clonagem de VM.
- Storages/ISOs/bridges carregados da API.
- Download de ISO por URL via API do Proxmox.
- Janela Web do Proxmox via túnel SSH local.
