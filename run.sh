#!/usr/bin/env bash
# Lanzador del MCP para Claude Desktop.
# La primera vez instala las dependencias en .venv (en segundo plano) y deja el registro en install.log.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$DIR/.venv/bin/python"
OK="$DIR/.venv/.ok"
LOCK="$DIR/.installing"

if [ ! -f "$OK" ]; then
  # lanzar la instalación si no hay una en curso (o si la anterior quedó colgada > 10 min)
  if [ ! -f "$LOCK" ] || [ -n "$(find "$LOCK" -mmin +10 2>/dev/null)" ]; then
    touch "$LOCK"
    setsid nohup bash "$DIR/install.sh" >>"$DIR/install.log" 2>&1 </dev/null &
  fi
  for _ in $(seq 1 110); do
    [ -f "$OK" ] && break
    [ -f "$DIR/.install_failed" ] && break
    sleep 1
  done
  if [ ! -f "$OK" ]; then
    echo "olx-aluguel-mcp: instalando dependencias o la instalación falló; revisa $DIR/install.log" >&2
    exit 1
  fi
fi
exec "$PY" -m olx_aluguel_mcp
