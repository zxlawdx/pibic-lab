#!/bin/sh
set -eu

SRC="/opt/pibic-workspace"
DEST="${1:-$HOME/pibic-workspace-repo}"
REMOTE="${2:-}"
VERSION="4.1.0"

if [ ! -d "$SRC/app" ] || [ ! -d "$SRC/web" ]; then
    echo "[ERRO] PIBIC Workspace nao encontrado em $SRC"
    exit 1
fi

if ! command -v git >/dev/null 2>&1; then
    echo "Git nao encontrado. Tentando instalar..."
    if command -v doas >/dev/null 2>&1; then
        doas apk add --no-cache git
    elif command -v sudo >/dev/null 2>&1; then
        sudo apk add --no-cache git
    elif [ "$(id -u)" -eq 0 ]; then
        apk add --no-cache git
    else
        echo "[ERRO] Instale git antes de continuar."
        exit 1
    fi
fi

if [ -e "$DEST" ] && [ -n "$(ls -A "$DEST" 2>/dev/null || true)" ]; then
    echo "[ERRO] O destino ja existe e nao esta vazio: $DEST"
    echo "Use outro diretorio, por exemplo:"
    echo "  sh $0 $HOME/pibic-workspace-repo-2"
    exit 1
fi

mkdir -p "$DEST" "$DEST/deploy"

copy_tree() {
    name="$1"
    if [ -r "$SRC/$name" ]; then
        tar -C "$SRC" -cf - "$name" | tar -C "$DEST" -xf -
    elif command -v doas >/dev/null 2>&1; then
        doas tar -C "$SRC" -cf - "$name" | tar -C "$DEST" -xf -
    elif command -v sudo >/dev/null 2>&1; then
        sudo tar -C "$SRC" -cf - "$name" | tar -C "$DEST" -xf -
    else
        echo "[ERRO] Sem permissao para copiar $SRC/$name"
        exit 1
    fi
}

copy_root_file() {
    source="$1"
    target="$2"
    if [ ! -f "$source" ]; then
        return 0
    fi
    if [ -r "$source" ]; then
        cat "$source" > "$target"
    elif command -v doas >/dev/null 2>&1; then
        doas cat "$source" > "$target"
    elif command -v sudo >/dev/null 2>&1; then
        sudo cat "$source" > "$target"
    else
        echo "[AVISO] Sem permissao para exportar $source"
        return 0
    fi
}

copy_tree app
copy_tree web

for f in requirements.txt pyproject.toml; do
    if [ -f "$SRC/$f" ]; then
        copy_root_file "$SRC/$f" "$DEST/$f"
    fi
done

printf '%s\n' "$VERSION" > "$DEST/VERSION"

copy_root_file /etc/init.d/pibic-workspace "$DEST/deploy/pibic-workspace.openrc"

# O helper privilegiado usa allowlist. Exportamos o fonte para que o repo
# represente a instalacao real, mas nunca copiamos doas.conf, senhas ou tokens.
for helper in /usr/local/sbin/pibic-workspace-helper /usr/local/libexec/pibic-workspace-priv; do
    if [ -f "$helper" ]; then
        copy_root_file "$helper" "$DEST/deploy/$(basename "$helper")"
    fi
done

find "$DEST" -type d -name __pycache__ -prune -exec rm -rf '{}' + 2>/dev/null || true
find "$DEST" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true

cat > "$DEST/.gitignore" <<'EOF'
.venv/
venv/
__pycache__/
*.py[cod]
*.log
*.pid
.env
.env.*
!.env.example
*.db
*.sqlite
*.sqlite3
backups/
node_modules/
.DS_Store
.vscode/
.idea/
EOF

cat > "$DEST/README.md" <<'EOF'
# PIBIC Workspace

Interface web leve para administracao e desenvolvimento em uma VM Alpine Linux.

## Recursos

- Dashboard com CPU, RAM, disco, uptime e carga reais
- Processos, armazenamento, rede e usuarios
- Terminal PTY real via WebSocket/xterm.js
- Editor de codigo e gerenciador de arquivos
- APK Package Manager
- Servicos OpenRC
- Docker e logs
- Interface responsiva com assets locais e icones SVG

## Arquitetura

- Backend Python no Alpine
- Interface HTML/CSS/JavaScript renderizada no navegador do cliente
- APIs locais para telemetria e administracao controlada
- Camada privilegiada limitada por allowlist

## Seguranca de acesso

O servico deve permanecer restrito ao loopback da VM:

```text
127.0.0.1:8765
```

Para acesso remoto, use um SSH Local Port Forward. Exemplo:

```bash
ssh -N -L 18765:127.0.0.1:8765 usuario@servidor
```

Depois abra `http://127.0.0.1:18765` no navegador local.

O projeto nao deve alterar SSH, porta 22, DNS, interfaces de rede, firewall ou ZeroTier durante uma atualizacao de interface.

## Estrutura

```text
app/      backend e APIs
web/      frontend e assets locais
deploy/   servico OpenRC e helper privilegiado, quando presente
```

## Desenvolvimento

Nao publique senhas, tokens, arquivos `.env`, bancos locais, logs, backups ou configuracoes privadas da VM no repositorio.
EOF

cd "$DEST"

git init -b main >/dev/null 2>&1 || {
    git init >/dev/null
    git branch -M main
}

git add .

if git config user.name >/dev/null 2>&1 && git config user.email >/dev/null 2>&1; then
    git commit -m "Initial PIBIC Workspace v$VERSION export" >/dev/null || true
    COMMITTED=yes
else
    COMMITTED=no
fi

if [ -n "$REMOTE" ]; then
    if git remote get-url origin >/dev/null 2>&1; then
        git remote set-url origin "$REMOTE"
    else
        git remote add origin "$REMOTE"
    fi
fi

echo
echo "=================================================="
echo "REPOSITORIO LOCAL PREPARADO"
echo "=================================================="
echo "Diretorio: $DEST"
echo "Versao: $VERSION"
echo "Branch: main"
echo

if [ "$COMMITTED" = no ]; then
    echo "O Git ainda nao tem nome/e-mail configurados. Rode:"
    echo '  git config --global user.name "Seu Nome"'
    echo '  git config --global user.email "seu-email@example.com"'
    echo "  cd '$DEST'"
    echo "  git commit -m 'Initial PIBIC Workspace v$VERSION export'"
    echo
fi

if [ -n "$REMOTE" ]; then
    echo "Remote origin: $REMOTE"
    echo "Para enviar:"
    echo "  cd '$DEST'"
    echo "  git push -u origin main"
else
    echo "Depois de criar um repositorio remoto, conecte com:"
    echo "  cd '$DEST'"
    echo "  git remote add origin https://github.com/SEU_USUARIO/SEU_REPO.git"
    echo "  git push -u origin main"
fi
