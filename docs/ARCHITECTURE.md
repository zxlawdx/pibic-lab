# Arquitetura do PIBIC LAB

## Visão geral

O projeto usa uma arquitetura em camadas para que Vela seja apenas a casca desktop. A UI não conhece senhas, comandos administrativos livres ou regras de Proxmox. Ela chama endpoints locais de `apps/lab/api.py`, que delegam casos de uso para `AppFacade`.

```text
HTML/CSS/JS + xterm.js
        |
        v
Vela API local / apps.lab.api
        |
        v
Application / AppFacade
   |       |        |        |
   v       v        v        v
 SSH    Detector  Docker   Proxmox
   |                         |
   +---- AsyncSSH -----------+
   |
ZeroTier / gateway

SQLite <---- metadados
Keyring <--- segredos
Audit  <---- eventos sanitizados
Catalog <--- manifests tipados locais
```

## Componentes principais

### `pibic_lab_core/domain`

Modelos Pydantic e permissões locais. Não depende de Vela, rede ou SQLite.

### `pibic_lab_core/application/facade.py`

Coordena os casos de uso expostos à interface: bootstrap, conectividade, SSH, terminal, detecção, catálogo, Docker, Proxmox, logs e diagnóstico. É também o local onde permissões são verificadas antes de chamar a infraestrutura.

### `infrastructure/zerotier.py`

Executa a CLI local com `subprocess.run(..., shell=False)` e argumentos definidos pelo backend. O único valor dinâmico aceito para `join` precisa corresponder a um Network ID hexadecimal de 16 caracteres.

### `infrastructure/ssh_service.py`

Mantém um loop asyncio dedicado para não bloquear a thread da UI. Usa AsyncSSH para host-key probe, autenticação, comandos, PTY e forwarding. Cada terminal recebe um `session_id` aleatório e buffers têm limites de tamanho.

### `infrastructure/proxmox_service.py`

Cria um listener SOCKS5 somente em `127.0.0.1` através da conexão SSH e usa `requests` com `socks5h` para alcançar a API HTTPS interna do Proxmox. O secret da API é lido do keyring somente durante a chamada. A validação TLS é verdadeira por padrão.

### `infrastructure/detector.py`

Executa somente IDs da allowlist em `util/commands.py`. Não concatena texto livre da interface. pgVector é explicitamente marcado como não confirmado quando não existe uma conexão PostgreSQL autorizada.

### `infrastructure/docker_service.py`

Usa `docker ps -a --format '{{json .}}'` para obter dados estruturados sem expor o socket remoto. Ações aceitas são somente `start`, `stop` e `restart`, com validação do ID/nome do container e autorização prévia.

### `infrastructure/catalog.py`

Converte manifests Pydantic em `InstallationPlan`. Ações de manifest são uma enumeração fechada. Os comandos exibidos na confirmação são produzidos pelo próprio backend. A execução registra um `InstallationJob` no SQLite e um evento no audit log.

### `credential_store.py`

Encapsula `keyring`. O banco local guarda apenas preferências; password, passphrase e Proxmox token secret são identificados por categoria + profile ID no cofre do sistema operacional.

### `security/hostkeys.py`

Mantém um `known_hosts` próprio do aplicativo. Primeiro acesso exige confirmação explícita; se a chave mudar, `ssh_connect` bloqueia antes de carregar qualquer senha.

## Fluxo de conexão

```text
1. UI seleciona perfil e ambiente.
2. ZeroTierAdapter verifica serviço/rede.
3. A UI testa o gateway TCP.
4. SSHSessionManager consulta a host key sem credencial.
5. Usuário compara e confirma a fingerprint.
6. O CredentialStore fornece segredo somente se necessário.
7. AsyncSSH autentica usando known_hosts estrito.
8. O Detector coleta dados somente leitura.
9. Terminal PTY, Docker e Proxmox são liberados conforme o perfil.
10. Ao desconectar, terminais e listeners de forwarding são fechados.
```

## Por que SOCKS para Proxmox

Um `local_forward` tradicional normalmente expõe o serviço interno como `https://127.0.0.1:porta`. Isso pode provocar incompatibilidade entre o hostname do certificado e `127.0.0.1`. Com um proxy SOCKS ligado apenas ao localhost, o cliente HTTPS continua requisitando `https://10.99.0.59:8006` e o tráfego é roteado pela sessão SSH. Assim a validação TLS pode continuar ativa quando o certificado/CA estiver corretamente configurado para esse destino.

## Limites intencionais desta versão

Atualização remota automática de catálogo está desativada até que o projeto defina e publique uma chave de assinatura institucional. Os manifests empacotados com a release são o catálogo confiável da versão instalada. O campo para URL de catálogo foi reservado, mas nenhum conteúdo remoto é baixado e executado silenciosamente.

SFTP, Jupyter, PostgreSQL/pgVector autenticado, snapshots/backups e observabilidade agregada pertencem às funcionalidades futuras da especificação e não são habilitados no MVP atual.
