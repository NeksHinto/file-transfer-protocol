# TP1 - Redes 2026 | File Transfer over UDP

```
Grupo 11 | Cátedra Hamelin | Martes | 1C 2026
```

Servidor concurrente y clientes `upload`/`download` sobre UDP, con
implementación de **Stop & Wait** y **Selective Repeat**

---

## Estructura del proyecto

```
file-transfer-protocol/
├── src/
│   ├── start_server.py            
│   ├── upload.py                  
│   ├── download.py                
│   ├── lib/
│   │   ├── __init__.py
│   │   ├── wire.py                
│   │   ├── flags.py               
│   │   ├── messages.py            
│   │   ├── chunker.py             
│   │   ├── logging_utils.py       
│   │   ├── protocol.py            
│   │   ├── stop_and_wait.py       
│   │   └── selective_repeat.py    
│   └── server/
│       ├── __init__.py            
│       ├── dispatcher.py          
│       └── session.py             
├── data/                          
├── storage/                       
├── logs/                          
├── mininet_topo.py                
├── mininet.sh                     
├── requirements.txt               
└── README.md
```

---

## Instalación

```bash
python3 -m venv env
source env/bin/activate     # deactivate para salir
pip install -r requirements.txt
```

---

## Logging y manejo de errores

- Hay un único log de servidor (`logs/server.log`) y la salida estándar.
- Cada línea lleva timestamp, nivel, módulo y, cuando aplica, **`[ip:port]` del peer**:

  ```
  [2026-04-30 22:11:33] [INFO] SERVER - [10.0.0.1:54312] UPLOAD 'foo.bin' protocolo=sr
  ```

- Validaciones de entrada se reportan al cliente como paquete `ERROR` y al log local.

---

## Argumentos de los binarios

Comunes a `upload`, `download` y `start-server`:

| Flag | Descripción | Default |
|---|---|---|
| `-v`, `--verbose` | Log nivel `DEBUG` (ver cada paquete) | – |
| `-q`, `--quiet`   | Log nivel `WARNING` | – |
| `-H`, `--host`    | IP a bindearse / a contactar | server `0.0.0.0`, clientes `127.0.0.1` |
| `-p`, `--port`    | Puerto UDP | `9000` |

Servidor:
| Flag | Descripción | Default |
|---|---|---|
| `-s`, `--storage` | Directorio donde guardar/leer archivos | `./storage` |

Clientes:
| Flag | Descripción |
|---|---|
| `-r`, `--protocol` | `stop_and_wait` (alias `sw`, `snw`) **o** `selective_repeat` (alias `sr`) |
| `-s`, `--src` (upload) | Ruta local del archivo a subir |
| `-d`, `--dst` (download) | Carpeta destino |
| `-n`, `--name` | Nombre con el que se guarda/lee en el servidor |

---

## Pruebas locales (sin Mininet)

### Generar archivos de prueba (todos los tamaños)

```bash
mkdir -p data
echo "hello world" > data/tiny.txt                    # ~12 B (caso mínimo)
dd if=/dev/urandom of=data/small.bin   bs=1K count=10  # 10 KB
dd if=/dev/urandom of=data/medium.bin  bs=1M count=1   # 1 MB
dd if=/dev/urandom of=data/large.bin   bs=1M count=5   # 5 MB (requisito)
dd if=/dev/urandom of=data/huge.bin    bs=1M count=50  # 50 MB (estrés)
```

### Terminal 1 — Servidor

```bash
# Modo normal
python3 src/start-server.py -H 127.0.0.1 -p 9000 -s ./storage

# Modo verbose (ver cada paquete)
python3 src/start-server.py -v -H 127.0.0.1 -p 9000 -s ./storage
```

### Terminal 2 — Upload (cliente -> servidor)

```bash
# Stop & Wait, archivo minimo
python3 src/upload.py -v -r sw -s ./data/tiny.txt   -n tiny.txt

# Stop & Wait, archivo chico
python3 src/upload.py -v -r sw -s ./data/small.bin  -n small.bin

# Selective Repeat, archivo mediano
python3 src/upload.py -v -r sr -s ./data/medium.bin -n medium.bin

# Selective Repeat, archivo grande (caso del enunciado: 5 MB)
python3 src/upload.py -v -r sr -s ./data/large.bin  -n large.bin

# Selective Repeat, archivo enorme (50 MB)
python3 src/upload.py    -r sr -s ./data/huge.bin   -n huge.bin

# Modo silencioso (solo resultado final)
python3 src/upload.py -q -r sw -s ./data/small.bin  -n small.bin
```

### Terminal 2 — Download (servidor -> cliente)

```bash
# Descargar un archivo al directorio ./descargas/
mkdir -p descargas

python3 src/download.py -v -r sw -d ./descargas -n tiny.txt
python3 src/download.py -v -r sr -d ./descargas -n large.bin
python3 src/download.py    -r sr -d ./descargas -n huge.bin
```

### Verificar integridad (debe coincidir el hash)

```bash
md5sum data/large.bin descargas/large.bin
md5sum data/huge.bin  descargas/huge.bin
```

### Concurrencia (varios clientes a la vez)

```bash
# En 3 terminales distintas, contra el mismo servidor:
python3 src/upload.py -r sr -s ./data/large.bin -n a.bin &
python3 src/upload.py -r sw -s ./data/medium.bin -n b.bin &
python3 src/download.py -r sr -d ./descargas -n large.bin &
wait
```

En `logs/server.log` cada sesión queda etiquetada con su `[ip:port]` para poder seguirla.

### Reportar errores (validaciones que deberían rechazarse)

```bash
# Archivo inexistente -> validacion del cliente
python3 src/upload.py   -s ./data/no_existe -n x.bin
# Archivo inexistente en server -> server responde ERROR
python3 src/download.py -d ./descargas -n no_existe.bin
# Path traversal -> server rechaza con ERROR
python3 src/download.py -d ./descargas -n ../../etc/passwd
# Protocolo invalido -> validacion del cliente
python3 src/upload.py   -r foo -s ./data/tiny.txt -n tiny.txt
```

### Cerrar el servidor

```bash
# Ctrl-C en la terminal del servidor, o por PID:
sudo lsof -i UDP:9000
sudo kill -9 <PID>
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
mininet> h2 python3 /TP1-Redes-2026/src/start_server.py -v -H 10.0.0.2 -p 9000 -s /tmp/storage > /tmp/server.log 2>&1 &
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

---

## Protocolo de aplicación

Header (9 bytes) seguido del payload (≤ 1400 B; total ≤ 1409 B para evitar
fragmentación IP en MTUs de 1500 B):

```
+--------+--------+--------+-------+--------+--------------------+
|  SEQ   |  ACK   | LENGTH | FLAGS | CKSUM  |      PAYLOAD       |
| 2 bytes| 2 bytes| 2 bytes| 1 byte| 2 bytes|  hasta 1400 bytes  |
+--------+--------+--------+-------+--------+--------------------+
```

Flags (bitmask):

| Valor  | Nombre    | Uso |
|--------|-----------|-----|
| `0x01` | DATA      | Paquete de datos |
| `0x02` | ACK       | Acuse de recibo |
| `0x04` | FIN       | Fin de transferencia |
| `0x08` | HANDSHAKE | Inicio de conexión |
| `0x10` | ERROR     | Error reportado por el servidor |

Checksum: 16-bit one's-complement de Internet (RFC 1071).

### Flujo UPLOAD

```
Cliente                           Servidor
  |---[HANDSHAKE: UPLOAD|nombre|protocolo]--->|
  |<------------------[ACK]-------------------|
  |---[DATA seq=0]--------------------------->|
  |<------------------[ACK ack=0]-------------|
  |---[DATA seq=1]--------------------------->|
  |<------------------[ACK ack=1]-------------|
  |                  ...                      |
  |---[FIN]---------------------------------->|
  |<------------------[ACK]-------------------|
```

### Flujo DOWNLOAD

```
Cliente                           Servidor
  |---[HANDSHAKE: DOWNLOAD|nombre|protocolo]->|
  |<------------------[ACK]-------------------|
  |<------------------[DATA seq=0]------------|
  |---[ACK ack=0]---------------------------->|
  |<------------------[DATA seq=1]------------|
  |---[ACK ack=1]---------------------------->|
  |                  ...                      |
  |<------------------[FIN]-------------------|
  |---[ACK]---------------------------------->|
```

---

## Comandos útiles fuera del proyecto

```bash
netstat -lun # sockets UDP en escucha
netstat -tln # sockets TCP en escucha
sudo lsof -i UDP:9000 # quien tiene UDP/9000 abierto
sudo wireshark & # captura/analisis gáfico
```
