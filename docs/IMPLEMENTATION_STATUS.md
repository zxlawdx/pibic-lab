# Matriz de implementação

Esta matriz relaciona a especificação original ao código entregue na versão 0.1.2.

| Requisito | Estado | Implementação principal |
|---|---|---|
| RF-01 Conexões sem senha em texto puro | Implementado | SQLite guarda metadados; `CredentialStore` usa keyring. |
| RF-02 Detectar ZeroTier / Node ID | Implementado | `ZeroTierAdapter.status()` e UI de conectividade. |
| RF-03 SSH com host key/fingerprint | Implementado | `SSHSessionManager.probe_host_key()` + `known_hosts`. |
| RF-04 Terminal PTY interativo | Implementado | AsyncSSH PTY + xterm.js local + resize/input/poll. |
| RF-05 Port forwarding | Implementado no core | Forward local e SOCKS disponíveis no `SSHSessionManager`; Proxmox usa SOCKS. |
| RF-06 Consultar API Proxmox | Implementado | HTTPS direto pela API `/api2/json` via `requests` + SOCKS. |
| RF-07 Listar somente VMs permitidas | Implementado | Filtro de `assigned_vmids`; ACL do servidor continua obrigatória. |
| RF-08 Start/Stop/Reboot com confirmação | Implementado | Confirmação na UI + revalidação no backend. |
| RF-09 Detectar SO/serviços | Implementado | `ServiceDetector` + allowlist de comandos. |
| RF-10 Detectar Docker/containers | Implementado | `DockerService` via CLI SSH estruturada. |
| RF-11 Catálogo versionado | Implementado localmente | Manifests YAML com schema v1 e Pydantic. |
| RF-12 Mostrar plano antes de instalar | Implementado | `InstallationPlan` + modal com comandos e privilégio. |
| RF-13 Registrar jobs/resultado/usuário | Implementado | SQLite + audit JSONL sanitizado. |
| RF-14 App e catálogo atualizados separadamente | Parcial e deliberado | O build do app e o catálogo local são separados. Atualização remota automática permanece desabilitada até existir chave institucional de assinatura. |
| RF-15 Exportar logs sem segredos | Implementado | `DiagnosticsExporter` + `redaction.py`. |

## Requisitos não funcionais

Segurança por padrão, disponibilidade degradável do ZeroTier, Windows/Linux, auditabilidade, interfaces separadas e usabilidade de conexão foram incorporados no desenho. Testabilidade é coberta por testes unitários locais e pela separação do core da UI Vela.

## Itens futuros da especificação

Integração PostgreSQL/pgVector autenticada, Jupyter por forwarding temporário, SFTP com sandbox, backups/snapshots, observabilidade agregada e assignment centralizado de VMs permanecem fora do MVP desta versão, como indicado na própria seção de funcionalidades futuras do documento original.
