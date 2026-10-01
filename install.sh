#!/usr/bin/env bash
# Crea .venv e instala el paquete. Lo llama run.sh; también se puede ejecutar a mano: bash install.sh
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR" || exit 1
rm -f .install_failed
echo "== $(date '+%F %T') instalando olx-aluguel-mcp =="
PYSYS="$(command -v python3 || command -v python)"
echo "python del sistema: $PYSYS ($("$PYSYS" --version 2>&1))"
ok=1
rm -rf .venv
if command -v uv >/dev/null 2>&1; then
  echo "-> usando uv"
  uv venv --python "$PYSYS" .venv && uv pip install --python .venv/bin/python -e . && ok=0
fi
if [ $ok -ne 0 ]; then
  rm -rf .venv
  echo "-> usando venv + pip"
  if "$PYSYS" -m venv .venv; then
    .venv/bin/python -m pip install -q --upgrade pip && .venv/bin/python -m pip install -q -e . && ok=0
  else
    echo "-> venv sin pip (falta python3-venv); probando pip del sistema con --python"
    rm -rf .venv
    "$PYSYS" -m venv --without-pip .venv && "$PYSYS" -m pip --python .venv/bin/python install -q -e . && ok=0
  fi
fi
if [ $ok -eq 0 ] && .venv/bin/python -c "import olx_aluguel_mcp.server" ; then
  touch .venv/.ok
  echo "OK: instalación completa"
else
  touch .install_failed
  echo "ERROR: la instalación falló. Si ves 'ensurepip is not available', instala: sudo apt install python3-venv  y reinicia Claude Desktop."
fi
rm -f .installing
