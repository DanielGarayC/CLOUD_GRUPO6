#!/bin/bash

# ============================
#  Script para eliminar router
# ============================

if [ -z "$1" ]; then
  echo "Uso: $0 <router_id_o_nombre>"
  exit 1
fi

ROUTER_ID=$1

echo "🔎 Verificando router: $ROUTER_ID"
openstack router show "$ROUTER_ID" >/dev/null 2>&1
if [ $? -ne 0 ]; then
  echo "❌ Router no existe o no se puede consultar."
  exit 1
fi

echo "========================================"
echo "  Eliminando interfaces del router..."
echo "========================================"

PORTS=$(openstack port list --router "$ROUTER_ID" -f value -c ID)

if [ -z "$PORTS" ]; then
  echo "✔ No hay puertos asociados."
else
  for PORT in $PORTS; do
    echo "🔧 Quitando puerto: $PORT"
    openstack router remove port "$ROUTER_ID" "$PORT"
  done
fi

echo "========================================"
echo "  Quitando gateway externo (si existe)..."
echo "========================================"

openstack router unset --external-gateway "$ROUTER_ID" 2>/dev/null
if [ $? -eq 0 ]; then
  echo "✔ Gateway externo removido."
else
  echo "ℹ No tenía gateway externo."
fi

echo "========================================"
echo "  Eliminando router..."
echo "========================================"

openstack router delete "$ROUTER_ID"
if [ $? -eq 0 ]; then
  echo "🎉 Router eliminado correctamente."
else
  echo "❌ Error al eliminar el router."
fi

