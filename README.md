# PIBIC LAB

Aplicativo desktop em Python + Vela Framework para simplificar o acesso às VMs do laboratório PIBIC/UNIR sem transformar conveniência em privilégio administrativo. A interface esconde a sequência operacional de ZeroTier, validação de host key, SSH, terminal PTY, túnel para a API do Proxmox, detecção de serviços, Docker e instalação assistida, preservando controles explícitos de segurança.

## O que já está implementado

O projeto entregue neste repositório contém uma aplicação única e executável, e não apenas exemplos isolados. O núcleo de negócio fica em `pibic_lab_core/` e não depende do Vela; a pasta `apps/lab/` funciona como adaptador visual/API local.

- Dashboard com sistema operacional, kernel, arquitetura, CPU, RAM, disco, IPs, uptime e serviços detectados.
- Diagnóstico do ZeroTier e gateway SSH.
- Entrada em rede ZeroTier por Network ID validado, sem token administrativo do ZeroTier Central.
- Verificação de fingerprint SSH antes do envio de credenciais e bloqueio quando a host key muda.
- Autenticação por SSH Agent, arquivo de chave ou senha.
- Senhas, passphrases e API Token armazenados somente no keyring nativo do sistema quando o usuário opta por salvar.
- Terminal SSH integrado com PTY, resize, Ctrl+C, programas full-screen e xterm.js local. Existe um terminal básico de contingência caso o asset xterm.js não tenha sido baixado durante o setup.
- API Proxmox através de SOCKS local sobre a sessão SSH, com validação TLS habilitada por padrão.
- Filtro de VMs por perfil e ações Start, Stop e Reboot somente quando a permissão local permite; o Proxmox ainda precisa validar a ACL real.
- Detecção somente leitura de Git, Python, Node.js, Docker, Compose, PostgreSQL, Nginx, Apache, SSH e pgVector como não confirmado quando não houver consulta autorizada ao banco.
- Inspeção de containers Docker via CLI remota, sem expor `/var/run/docker.sock`.
- Catálogo YAML tipado para Git, Python, Docker, Nginx e PostgreSQL.
- Plano de instalação visível antes da execução, confirmação explícita, elevação sob demanda, verificação pós-instalação e histórico de jobs.
- SQLite apenas para metadados não secretos.
- Auditoria local sanitizada e exportação de diagnóstico em ZIP.
- Scripts de setup, execução, teste e build para reduzir o trabalho dos colegas.

## Início rápido no Windows

A forma mais simples para um colega usar o projeto é extrair a pasta e executar `SETUP_WINDOWS.bat` uma vez. O script procura Python 3.13/3.12, cria `.venv`, instala as dependências, baixa o xterm.js para uso local, executa `collectstatic` e faz um diagnóstico do ambiente. Depois disso, `INICIAR_WINDOWS.bat` abre o aplicativo.

Para gerar uma distribuição sem exigir Python no computador de destino, execute `BUILD_WINDOWS.bat` em uma máquina Windows. O build usa PyInstaller + PyQt5/PyQtWebEngine e cria `PIBIC-LAB-Windows.zip`. O PyInstaller não oferece cross-compilation confiável de Linux para Windows, portanto o build do `.exe` deve ser realizado no próprio Windows.

## Início rápido no Linux Mint, Ubuntu ou Debian

No terminal, dentro da pasta do projeto:

```bash
chmod +x setup_linux.sh iniciar_linux.sh
./setup_linux.sh
./iniciar_linux.sh
```

O ambiente virtual é criado com `--system-site-packages`, permitindo que o Vela/pywebview reutilize as bindings GTK/WebKit instaladas pelo sistema. Caso PyGObject/GTK não seja encontrado, o script mostra os pacotes de sistema que normalmente precisam ser instalados.

## Primeiro acesso ao laboratório

1. Abra **Conexão** e escolha o ambiente.
2. Se necessário, informe o `ZeroTier Network ID` em **Configurações** ou use **Entrar na rede**.
3. Execute **Verificar conectividade**.
4. Informe o usuário SSH e o método de autenticação.
5. Clique em **Validar** para obter a fingerprint do gateway.
6. Compare a fingerprint com uma fonte confiável do laboratório e só então marque aquela chave como confiável.
7. Clique em **Conectar via SSH**.
8. Abra **Terminal**, **Serviços**, **Docker** ou **Proxmox** conforme as permissões do perfil.

A topologia inicial cadastrada é:

```text
Gateway ZeroTier / SSH : 10.57.144.217:22
Proxmox interno        : 10.99.0.59:8006
```

Esses valores são editáveis em **Configurações > Ambiente do laboratório**.


### Nota importante sobre arquivos estáticos do Vela

O Vela já adiciona automaticamente o nome do app ao copiar `apps/<app>/static/` para `staticfiles/<app>/`. Por isso, dentro de `apps/lab/static/` **não** deve existir outra pasta `lab/`. O caminho correto é `apps/lab/static/css/app.css`, que é coletado como `staticfiles/lab/css/app.css` e servido em `/__vela__/static/lab/css/app.css`.

Se a interface aparecer como HTML sem estilos, limpe os estáticos antigos e gere novamente:

```bash
rm -rf staticfiles
python manage.py collectstatic --noinput
python manage.py runapp
```

## API Token do Proxmox

O aplicativo não usa automação de navegador para controlar o Proxmox. A aba Proxmox consulta a API HTTPS interna através de um proxy SOCKS criado dinamicamente na sessão AsyncSSH. Isso permite manter o destino TLS como `10.99.0.59:8006`, em vez de transformar o endpoint em `127.0.0.1` e dificultar a validação do certificado.

Configure um usuário técnico e um token de privilégio mínimo, por exemplo com ACL somente nas VMs/pool atribuídos. O secret do token fica no keyring do sistema operacional. Nunca configure `root@pam` com token global no aplicativo.

Se o certificado do Proxmox for emitido por uma CA interna, informe o caminho do arquivo de CA em **Configurações > Proxmox e TLS**. A validação TLS vem habilitada. O modo inseguro precisa ser explicitamente liberado e deve ser usado apenas para diagnóstico controlado.

## Terminal integrado

O terminal remoto usa AsyncSSH com PTY `xterm-256color`. O frontend usa xterm.js quando os assets estiverem disponíveis em:

```text
apps/lab/static/vendor/xterm/
```

`scripts/vendor_frontend.py` baixa versões fixas durante o setup e o build. O aplicativo não depende de CDN em runtime. Se o download falhar, a aplicação continua funcionando com uma interface de terminal básica, útil para comandos simples; execute novamente o script de vendor quando houver internet para habilitar a experiência completa.

## Catálogo e instalação assistida

Os manifests ficam em `catalog/manifests/`. Eles não carregam scripts arbitrários: o backend aceita somente ações tipadas como `apt_update`, `apt_install`, `apk_add`, `systemd_enable`, `openrc_enable` e comandos fixos existentes na allowlist interna.

Antes de um job, a UI mostra os comandos que serão executados. Se o manifest exigir privilégio e a sessão não for root, o instalador aceita `sudo -S` com senha fornecida apenas para aquele job. A senha não é gravada em arquivo ou banco. Em hosts que usam apenas `doas`, a elevação deve ser realizada manualmente pelo terminal até que uma política segura específica seja adicionada.

Os manifests incluídos no pacote são tratados como parte da release instalada. Atualizações remotas de catálogo não são ativadas automaticamente nesta versão: isso evita introduzir um canal de execução remota antes de existir uma política institucional de assinatura/chaves para o projeto. O campo `catalog_url` já existe nas configurações para uma fase posterior com verificação criptográfica.

## Estrutura do projeto

```text
pibic_lab_vela/
├── manage.py
├── launcher.py
├── config/
├── apps/lab/
│   ├── api.py
│   ├── views/
│   ├── templates/
│   └── static/
│       ├── css/
│       ├── js/
│       └── vendor/
├── pibic_lab_core/
│   ├── domain/
│   ├── application/
│   ├── infrastructure/
│   ├── security/
│   ├── audit/
│   └── util/
├── catalog/
│   ├── schema/
│   └── manifests/
├── scripts/
├── tests/
└── docs/
```

A camada `pibic_lab_core` não importa Vela. Isso permite testar SSH, Proxmox, catálogo, detecção e persistência sem abrir uma janela e também preserva a possibilidade de trocar a camada visual futuramente.

## Dados locais

Os caminhos de dados são definidos com `platformdirs`, portanto variam conforme o sistema operacional. O banco `pibic_lab.sqlite3`, `known_hosts` e diagnósticos ficam no diretório de dados do usuário; logs ficam no diretório de logs do usuário. Para testes ou laboratório isolado, é possível sobrescrever tudo com:

```bash
PIBIC_LAB_DATA_DIR=/caminho/temporario
```

Nenhuma senha é salva no SQLite. Os registros de perfil guardam somente nome, role local, usuário SSH padrão, VMIDs atribuídos e flags de interface.

## Testes

Depois de instalar `requirements-dev.txt`:

```bash
python -m pytest -q
python -m compileall -q .
python scripts/check_environment.py
```

Os testes incluídos cobrem autorização local por VM, sanitização de segredos, `known_hosts`, parsing/planejamento dos manifests e persistência SQLite. Testes de integração contra o laboratório real devem ser executados apenas em ambiente autorizado, com credenciais de teste e ACL restrita.

## Segurança importante

O perfil local do aplicativo não é uma fronteira de autenticação. Um usuário com controle do próprio computador pode alterar arquivos e banco local. Portanto, o servidor deve continuar impondo o que realmente importa: usuário Unix separado, `authorized_keys`, permissões de arquivos, política `sudo`/`doas`, ACLs/tokens do Proxmox e autorização da rede ZeroTier.

O aplicativo também evita `shell=True` com entradas da interface. Detectores usam comandos fixos; identificadores dinâmicos passam por validação estrita; senhas administrativas não são colocadas na linha de comando; logs passam por sanitização antes da gravação/exportação.

Leia também [docs/SECURITY.md](docs/SECURITY.md) e [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Estado da validação

A estrutura Python e JavaScript deste pacote foi verificada localmente por compilação/sintaxe e testes unitários que não dependem da rede. Como esta entrega foi montada fora da rede institucional, ela não foi autenticada contra o gateway ZeroTier/SSH nem contra a API Proxmox real. Antes de distribuir amplamente, faça um teste de integração controlado no laboratório e confirme fingerprints, CA TLS, ACLs e VMIDs.

## Compatibilidade Vela no Linux/GTK

A versão 0.1.2 inclui uma camada local de compatibilidade para dois detalhes do ciclo de vida do Vela:

1. A view é inserida no shell depois de `DOMContentLoaded`, portanto o frontend do PIBIC LAB inicializa imediatamente quando o documento já está pronto.
2. Em GTK/WebKit, `window.pywebview.api` pode existir alguns milissegundos antes de `get_config()` e das demais funções do bridge. A janela resiliente espera o bridge completo e repete o bootstrap apenas quando a primeira tentativa não carregou rota alguma.

Não edite arquivos dentro de `.venv/site-packages/vela`. Para inspecionar o ambiente, use:

```bash
python scripts/check_vela_runtime.py
```
# pibic-lab
