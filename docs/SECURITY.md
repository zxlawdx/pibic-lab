# Segurança do PIBIC LAB

## Princípio central

O aplicativo deve simplificar a operação sem ampliar os privilégios do usuário. A UI local nunca substitui a autorização do servidor. As barreiras reais continuam sendo a autorização do ZeroTier, a conta SSH, permissões Unix, `sudo`/`doas`, ACLs do Proxmox e privilégios do API Token.

## Segredos

O SQLite não recebe password, passphrase, token secret ou chave privada. Quando o usuário escolhe salvar uma senha SSH ou passphrase, o valor é enviado ao backend local e armazenado com `keyring`. O secret do Proxmox segue a mesma regra. Chaves SSH privadas permanecem como arquivo local/SSH Agent e não são copiadas pelo aplicativo.

Logs e diagnósticos passam por `security/redaction.py`, que remove campos sensíveis conhecidos e padrões textuais de authorization/password/token/secret e credenciais embutidas em URL. Essa sanitização reduz o risco, mas o arquivo exportado ainda deve ser revisado antes de ser compartilhado fora do grupo.

## Host key SSH

A primeira conexão realiza apenas a leitura da chave pública apresentada pelo servidor. Nenhuma senha é enviada nessa fase. A fingerprint SHA256 aparece na interface para comparação por um canal confiável. Depois da confirmação, a chave é adicionada ao `known_hosts` privado do aplicativo.

Se o gateway apresentar uma chave diferente em uma conexão futura, a operação é bloqueada antes do carregamento de credenciais. Não normalize esse evento como uma simples mensagem de erro: confirme primeiro se houve reinstalação ou rotação planejada do servidor.

## Proxmox

Não configure `root@pam` com token global. Crie usuário técnico e API Token com `privilege separation`, aplique ACL na menor árvore possível e atribua somente as operações exigidas. Quando o perfil for somente leitura, prefira uma role de auditoria/read-only.

A validação TLS vem ligada. Para CA própria, informe o arquivo de CA em Configurações. O modo inseguro só funciona quando `verify_proxmox_tls=false` e `allow_unsafe_proxmox_tls=true`, forçando uma decisão explícita. Essa opção existe para diagnóstico e não deve virar padrão de distribuição.

## Terminal

O PTY oferece ao usuário exatamente os privilégios da conta SSH autenticada. Por isso o aplicativo não tenta bloquear comandos digitados no terminal: isso seria uma falsa fronteira de segurança. Contenção deve ocorrer no servidor.

A API local que transporta input/output é criada pelo Vela no computador do usuário; o projeto não abre WebSocket próprio em `0.0.0.0`. Buffers e payloads têm limites para reduzir consumo acidental de memória.

## Comandos automatizados

A aplicação não aceita um campo de texto livre e o repassa a `shell=True`. Detectores usam uma tabela interna de comandos fixos. Docker limita ações e valida identificadores. O catálogo aceita uma enumeração de tipos de operação e valida nomes de pacotes/serviços antes de formar o comando.

A senha de `sudo` é enviada por stdin para `sudo -S`, não aparece como argumento do processo, não entra no job e a referência Python é descartada depois da execução. `doas` automatizado não é implementado nesta versão porque sua política varia entre hosts; use o terminal para elevação interativa quando necessário.

## Docker

Não exponha `/var/run/docker.sock` por TCP e não adicione usuários ao grupo `docker` automaticamente. Em muitos sistemas, acesso ao daemon Docker equivale a alto privilégio no host. O PIBIC LAB apenas chama a CLI através do SSH já autenticado.

## Perfis locais

Roles e VMIDs guardados no SQLite controlam a experiência da interface, não uma autorização resistente a adulteração. Um usuário dono da máquina consegue modificar o próprio banco. Portanto:

- Proxmox deve rejeitar ações fora da ACL mesmo que a UI seja alterada.
- A conta SSH deve enxergar apenas os arquivos/processos permitidos.
- `sudo`/`doas` deve limitar comandos e usuários conforme a política do laboratório.
- ZeroTier deve autorizar cada dispositivo pelo administrador.

## Checklist antes de colocar em produção

1. Confirmar a fingerprint do gateway por um segundo canal.
2. Criar contas SSH individuais, sem senha compartilhada do laboratório.
3. Preferir chaves Ed25519 com passphrase/agent.
4. Revisar `sudoers`/`doas.conf` de cada VM.
5. Criar API Token Proxmox dedicado e ACL mínima.
6. Importar a CA correta do Proxmox e manter TLS verification habilitada.
7. Testar o filtro de VMID com conta sem privilégio administrativo.
8. Revisar os manifests antes de cada release.
9. Executar testes unitários e integração em VM de laboratório não crítica.
10. Revisar ZIP de diagnóstico antes de compartilhar.
