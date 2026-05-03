# TP1 - Redes 2026 | File Transfer UDP — Stop & Wait

```
Grupo 11 | Cátedra Hamelin | Martes | 2C2026
```

## Integrantes

| Nombre | Padrón | Email |
|---|---|---|
| xxxxx | 10000 | @fi.uba.ar |


---

## Estructura del proyecto

```
TP1-Redes-2026/
├── src/
│   ├── lib/
│   │   ├── __init__.py
│   │   ├── packet.py         ← estructura y parsing de paquetes UDP
│   │   └── stop_and_wait.py  ← protocolo Stop & Wait (sender + receiver)
│   ├── start-server.py       ← servidor concurrente
│   ├── upload.py             ← cliente upload
│   └── download.py           ← cliente download
├── data/                     ← archivos de prueba (archivo.txt, etc.)
├── mininet_topo.py           ← topología Mininet con pérdida configurable
├── mininet.sh                ← script de inicio de Mininet
├── storage/                  ← archivos recibidos por el servidor
├── logs/                     ← logs del servidor
├── requirements.txt
└── README.md
```

---

## Instalación

```bash
# 1. Crear entorno virtual
python3 -m venv env
source env/bin/activate

deactivate --> para salir 

# 2. Instalar dependencias
pip install -r requirements.txt
```

---

## Pruebas locales (sin Mininet)

### Terminal 1 — Iniciar el servidor

```bash
# Modo normal
python3 src/start-server.py -H 127.0.0.1 -p 9000 -s ./storage

# Modo verbose (ver cada paquete)
python3 src/start-server.py -v -H 127.0.0.1 -p 9000 -s ./storage
```

### Terminal 2 — Upload de un archivo

```bash
# Subir un archivo pequeño (modo verbose)
python3 src/upload.py -v -H 127.0.0.1 -p 9000 -s ./data/archivo.txt -n archivo.txt

# Subir un archivo grande
python3 src/upload.py -v -H 127.0.0.1 -p 9000 -s ./data/imagen.jpg -n imagen.jpg

# Modo silencioso (solo resultado final)
python3 src/upload.py -q -H 127.0.0.1 -p 9000 -s ./data/archivo.txt -n archivo.txt
```

### Terminal 2 — Download de un archivo

```bash
# Descargar un archivo al directorio ./descargas/
python3 src/download.py -v -H 127.0.0.1 -p 9000 -d ./descargas -n archivo.txt

# Verificar que el archivo descargado es idéntico al original
md5sum ./data/archivo.txt ./descargas/archivo.txt
```

### Generar un archivo de prueba de 5 MB

```bash
dd if=/dev/urandom of=./data/archivo_5mb.bin bs=1M count=5
```

---

## Pruebas con Mininet

### Requisitos

```bash
sudo apt-get install -y mininet openvswitch-switch openvswitch-testcontroller
sudo mn --test pingall   # verificar instalación
```

### Iniciar la topología

Estos comandos se ejecutan en una terminal normal de Linux (fuera del prompt `mininet>`).

```bash
# Limpiar procesos/estado previo de Mininet (purgar basura)
sudo mn -c && sudo pkill -f mininet_topo.py 2>/dev/null || true && sudo pkill -f start-server.py 2>/dev/null || true && sudo umount /TP1-Redes-2026 2>/dev/null || true && sudo rm -rf /tmp/tp1_shared /tmp/descargas /tmp/captura.pcap /tmp/server.log && rm -f ./data/*.bin

# Crear logs locales y arrancar Mininet
mkdir -p logs
sudo python3 mininet_topo.py --source-dir "$(pwd)"

# Con 20% de pérdida
sudo python3 mininet_topo.py --source-dir "$(pwd)" --loss 20

# Sin pérdida (para baseline)
sudo python3 mininet_topo.py --source-dir "$(pwd)" --loss 0
```

La topología levanta:
- `h1` → `10.0.0.1` (cliente)
- `h2` → `10.0.0.2` (servidor)
- `s1` → switch central con pérdida en el enlace `h1-s1`

### Comandos dentro del prompt de Mininet

**1. Levantar el servidor en h2:**
```
mininet> h2 python3 /TP1-Redes-2026/src/start-server.py -v -H 10.0.0.2 -p 9000 -s /tmp/storage > /tmp/server.log 2>&1 &
```

**2. Verificar que el servidor está corriendo:**
```
mininet> h2 ss -lunp | grep 9000
mininet> h2 tail -f /tmp/server.log
```

**3. Upload desde h1 → h2:**
```
mininet> h1 python3 /TP1-Redes-2026/src/upload.py -v -H 10.0.0.2 -p 9000 -s /TP1-Redes-2026/data/archivo.txt -n archivo.txt
```

**4. Download desde h2 → h1:**
```
mininet> h1 python3 /TP1-Redes-2026/src/download.py -v -H 10.0.0.2 -p 9000 -d /tmp/descargas -n archivo.txt
```

**5. Verificar integridad:**
```
mininet> h1 md5sum /TP1-Redes-2026/data/archivo.txt /tmp/descargas/archivo.txt
```

### Cambiar pérdida de paquetes en tiempo real

```
mininet> link h1 s1 loss 10     ← 10% de pérdida
mininet> link h1 s1 loss 0      ← sin pérdida
```

### Capturar tráfico con tcpdump

```
mininet> h1 tcpdump -i h1-eth0 -w /tmp/captura.pcap &
mininet> h1 python3 /TP1-Redes-2026/src/upload.py -H 10.0.0.2 -p 9000 -s /TP1-Redes-2026/data/archivo.txt -n archivo.txt
mininet> h1 kill %1
```

Abrir `captura.pcap` con Wireshark para ver el intercambio de paquetes.

### Otros comandos útiles de Mininet

```
mininet> pingall              ← probar conectividad entre todos los hosts
mininet> h1 ping -c 5 h2     ← ping de h1 a h2
mininet> h1 ifconfig          ← ver IP de h1
mininet> net                  ← ver la topología
mininet> xterm h1             ← abrir terminal gráfica en h1
mininet> xterm h2             ← abrir terminal gráfica en h2
mininet> exit                 ← salir de Mininet
```

---

## Protocolo de aplicación

### Estructura del paquete

```
+--------+--------+--------+-------+--------+--------------------+
|  SEQ   |  ACK   | LENGTH | FLAGS | CKSUM  |      PAYLOAD       |
| 2 bytes| 2 bytes| 2 bytes| 1 byte| 2 bytes|  hasta 1400 bytes  |
+--------+--------+--------+-------+--------+--------------------+
                        total máximo: 1409 bytes
```

### Flags

| Valor  | Nombre    | Uso |
|--------|-----------|-----|
| `0x01` | DATA      | Paquete de datos |
| `0x02` | ACK       | Acuse de recibo |
| `0x04` | FIN       | Fin de transferencia |
| `0x08` | HANDSHAKE | Inicio de conexión |
| `0x10` | ERROR     | Error del servidor |

### Flujo UPLOAD

```
Cliente                           Servidor
  |---[HANDSHAKE: UPLOAD|nombre]--->|
  |<----------[ACK]-----------------|
  |---[DATA seq=0]----------------->|
  |<----------[ACK ack=0]-----------|
  |---[DATA seq=1]----------------->|
  |<----------[ACK ack=1]-----------|
  |           ...                   |
  |---[FIN]------------------------>|
  |<----------[ACK]-----------------|
```

### Flujo DOWNLOAD

```
Cliente                           Servidor
  |---[HANDSHAKE: DOWNLOAD|nombre]->|
  |<----------[ACK]-----------------|
  |<----------[DATA seq=0]----------|
  |---[ACK ack=0]------------------->|
  |<----------[DATA seq=1]----------|
  |---[ACK ack=1]------------------->|
  |           ...                   |
  |<----------[FIN]-----------------|
  |---[ACK]------------------------->|
```

---

## Cerrar el servidor

```bash
# Buscar el proceso
sudo lsof -i UDP:9000

# Matar por PID
sudo kill -9 <PID>
```

---

## Formato de código

```bash
# Formatear
black src/

# Verificar PEP8
flake8 src/ --max-line-length=100
```
netstat -tuna

netstat -lun ---> para udp

netstat -tln ---> para tcp

sh wireshark &