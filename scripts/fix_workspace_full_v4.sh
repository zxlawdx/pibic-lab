#!/bin/sh
set -eu

BASE_URL="https://raw.githubusercontent.com/zxlawdx/pibic-lab/main/scripts/workspace_full_v4"
PAYLOAD="/tmp/pibic-workspace-full-v4.payload"
SCRIPT="/tmp/pibic-workspace-full-v4-real.sh"
EXPECTED_PAYLOAD="ce0fe444c4fed375fa9be52c5ba9c8dbf221ae301c18058a554563b397d521f8"
EXPECTED_SCRIPT="68570aba2c74d88d5dd94d57371af957e8d5e5eb634ce251b3ee4dab1cee59ca"

rm -f "$PAYLOAD" "$SCRIPT"
: > "$PAYLOAD"

echo "=================================================="
echo "PIBIC WORKSPACE v4 - PATCH FUNCIONAL"
echo "=================================================="
echo "Baixando e verificando o patch..."

for n in 00 01 02 03 04; do
    part="/tmp/pibic-workspace-v4.$n"
    rm -f "$part"
    wget -qO "$part" "$BASE_URL/payload.$n"
    cat "$part" >> "$PAYLOAD"
    rm -f "$part"
    echo "  payload.$n: OK"
done

actual_payload="$(sha256sum "$PAYLOAD" | awk '{print $1}')"
if [ "$actual_payload" != "$EXPECTED_PAYLOAD" ]; then
    echo "[ERRO] Payload corrompido."
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
    echo "[ERRO] Script decodificado nao confere."
    echo "Esperado: $EXPECTED_SCRIPT"
    echo "Recebido: $actual_script"
    rm -f "$SCRIPT"
    exit 1
fi

echo "Patch validado. Aplicando..."
exec sh "$SCRIPT"
