#!/bin/sh
set -eu

BASE_URL="https://raw.githubusercontent.com/zxlawdx/pibic-lab/main/scripts/workspace_alpinews_v3"
PAYLOAD="/tmp/pibic-alpinews-v3.payload"
SCRIPT="/tmp/pibic-alpinews-v3-real.sh"
EXPECTED_PAYLOAD="5d92de07ec9682f1c932268295866814ca101ecab5ca764f346ac850a769f23d"
EXPECTED_SCRIPT="df119a40c92a5d5b99a8870ac53686dd0e0ed330a8f60b4b1d4b97877ef37850"

rm -f "$PAYLOAD" "$SCRIPT"
: > "$PAYLOAD"

echo "=================================================="
echo "ALPINE WORKSPACE v3 - ATUALIZACAO DE INTERFACE"
echo "=================================================="
echo
echo "Baixando pacote visual validado..."

for n in 01 02 03 04 05; do
    part="/tmp/pibic-alpinews-v3.$n"
    rm -f "$part"
    wget -qO "$part" "$BASE_URL/payload.$n"
    cat "$part" >> "$PAYLOAD"
    rm -f "$part"
    echo "  payload.$n: OK"
done

actual_payload="$(sha256sum "$PAYLOAD" | awk '{print $1}')"
if [ "$actual_payload" != "$EXPECTED_PAYLOAD" ]; then
    echo
    echo "[ERRO] O pacote baixado nao passou na verificacao SHA-256."
    echo "Esperado: $EXPECTED_PAYLOAD"
    echo "Recebido: $actual_payload"
    rm -f "$PAYLOAD"
    exit 1
fi

base64 -d "$PAYLOAD" | gzip -d > "$SCRIPT"
rm -f "$PAYLOAD"
chmod +x "$SCRIPT"

actual_script="$(sha256sum "$SCRIPT" | awk '{print $1}')"
if [ "$actual_script" != "$EXPECTED_SCRIPT" ]; then
    echo
    echo "[ERRO] O instalador decodificado nao passou na verificacao SHA-256."
    echo "Esperado: $EXPECTED_SCRIPT"
    echo "Recebido: $actual_script"
    rm -f "$SCRIPT"
    exit 1
fi

echo
echo "Pacote verificado. Aplicando update..."
echo
exec sh "$SCRIPT"
