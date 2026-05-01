#!/bin/bash
# Iniciar entorno Mininet para TP1 Redes 2026
# Uso: bash mininet.sh [--loss 10] [--source-dir /ruta/proyecto]

set -e

LOSS=10
SOURCE_DIR="$(pwd)"

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        --loss) LOSS="$2"; shift 2 ;;
        --source-dir) SOURCE_DIR="$2"; shift 2 ;;
        *) echo "Argumento desconocido: $1"; exit 1 ;;
    esac
done

echo "=== TP1 Redes 2026 - Mininet ==="
echo "Source dir : $SOURCE_DIR"
echo "Packet loss: $LOSS%"
echo ""

# Limpiar entorno anterior
echo "[1/4] Limpiando entorno Mininet previo..."
sudo pkill -f ovs-testcontroller 2>/dev/null || true
sudo mn -c 2>/dev/null || true

# Preparar logs
echo "[2/4] Preparando directorio de logs..."
sudo rm -rf logs
mkdir -p logs
touch logs/server.log
sudo chmod a+w logs/server.log

# Activar entorno virtual si existe
if [ -f "env/bin/activate" ]; then
    echo "[3/4] Activando entorno virtual..."
    source env/bin/activate
else
    echo "[3/4] Sin entorno virtual, usando Python del sistema"
fi

# Iniciar Mininet
echo "[4/4] Iniciando Mininet..."
sudo python3 mininet_topo.py --source-dir "$SOURCE_DIR" --loss "$LOSS"
