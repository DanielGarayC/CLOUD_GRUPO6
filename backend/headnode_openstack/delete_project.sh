#!/bin/bash

PROJECT_NAME="$1"

if [ -z "$PROJECT_NAME" ]; then
    echo "Uso: $0 <project_name>"
    exit 1
fi

echo "🔍 Obteniendo ID del proyecto '$PROJECT_NAME'..."
PROJECT_ID=$(openstack project list --domain Cloud -f value -c ID -c Name | grep " $PROJECT_NAME" | awk '{print $1}')

if [ -z "$PROJECT_ID" ]; then
    echo "❌ Proyecto '$PROJECT_NAME' no encontrado."
    exit 1
fi

echo "✅ Proyecto encontrado: $PROJECT_ID"
echo ""

echo "🛑 Borrando instancias del proyecto..."
for server in $(openstack server list --project $PROJECT_ID -f value -c ID); do
    echo "   → Eliminando instancia $server"
    openstack server delete "$server"
done
echo "✔ Instancias eliminadas."
echo ""

echo "🛑 Borrando puertos..."
for port in $(openstack port list --project $PROJECT_ID -f value -c ID); do
    echo "   → Eliminando puerto $port"
    openstack port delete "$port"
done
echo "✔ Puertos eliminados."
echo ""

echo "🛑 Borrando subredes..."
for subnet in $(openstack subnet list --project $PROJECT_ID -f value -c ID); do
    echo "   → Eliminando subred $subnet"
    openstack subnet delete "$subnet"
done
echo "✔ Subredes eliminadas."
echo ""

echo "🛑 Borrando redes..."
for net in $(openstack network list --project $PROJECT_ID -f value -c ID); do
    echo "   → Eliminando red $net"
    openstack network delete "$net"
done
echo "✔ Redes eliminadas."
echo ""

echo "🛑 Eliminando el proyecto..."
openstack project delete "$PROJECT_ID"

if [ $? -eq 0 ]; then
    echo "🎉 Proyecto '$PROJECT_NAME' eliminado completamente."
else
    echo "⚠ No se pudo eliminar el proyecto."
fi
