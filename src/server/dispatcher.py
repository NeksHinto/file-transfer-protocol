"""
Server: dispatcher UDP concurrente.

Mantiene un único socket bindeado al puerto público y demultiplexa los
datagramas entrantes hacia per-client `incoming_q`s. Cada cliente
nuevo (HANDSHAKE) lanza un `ClientHandler` thread.
"""

import os
import queue
import socket
import threading

from lib.flags import is_handshake
from lib.logging_utils import (
    ValidationError,
    get_logger,
    log_error,
    validate,
)
from lib.messages import create_error_packet
from lib.wire import MAX_PACKET_SIZE, parse_packet
from server.session import ClientHandler

VALID_OPERATIONS = {"UPLOAD", "DOWNLOAD"}
VALID_PROTOCOLS = {"stop_and_wait", "sw", "selective_repeat", "sr"}

MAX_FILE_SIZE = 1 << 30  # 1 GB
DISK_SAFETY_MARGIN = 16 << 20  # 16 MB


class Server:

    def __init__(self, host, port, storage_dir, verbose):
        self.host = host
        self.port = port
        self.storage_dir = storage_dir
        self.verbose = verbose
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Routing table: addr -> {handler, incoming_q}.
        self.clients = {}
        # notifs desde handlers terminados (para limpiar `clients`)
        self.finished_q = queue.Queue()
        # bloquea `clients` entre dispatcher y cleanup thread
        self._lock = threading.Lock()
        self.logger = get_logger("SERVER")

    # ------------------------------------------------------------------ run --
    def start(self):
        os.makedirs(self.storage_dir, exist_ok=True)
        self.sock.bind((self.host, self.port))
        self.logger.info(f"servidor escuchando en {self.host}:{self.port}")
        self.logger.info(f"storage: {os.path.abspath(self.storage_dir)}")

        threading.Thread(target=self._cleanup_loop, daemon=True).start()

        self.sock.settimeout(1.0)  # para Ctrl-C se propagague
        while True:
            try:
                data, addr = self.sock.recvfrom(MAX_PACKET_SIZE + 64)
            except socket.timeout:
                continue
            except OSError as e:
                log_error(self.logger, "recvfrom fallo", e)
                continue

            pkt = parse_packet(data)
            if pkt is None:
                self.logger.warning(
                    f"paquete corrupto de {addr[0]}:{addr[1]} - descartado"
                )
                continue

            with self._lock:
                client = self.clients.get(addr)
                if client is not None:
                    client["incoming_q"].put((data, addr))
                elif is_handshake(pkt):
                    self._spawn(addr, pkt)
                else:
                    # Sin sesión abierta y no es handshake: residual de una
                    # sesión previa o un cliente fuera de protocolo.
                    self.logger.debug(
                        f"paquete sin sesion de {addr[0]}:{addr[1]} "
                        f"(flags={pkt['flags']:#04x}) descartado"
                    )

    # -------------------------------------------------------------- spawn --
    def _spawn(self, addr, pkt):
        peer_logger = get_logger("SERVER", peer=addr)
        try:
            parts = pkt["payload"].decode().split("|")
            validate(
                len(parts) >= 2,
                "handshake con menos de 2 campos",
                peer_logger,
            )
            operation = parts[0].upper()
            filename = os.path.basename(parts[1])
            protocol = (parts[2] if len(parts) > 2 else "").lower() or "stop_and_wait"
            file_size = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0

            validate(
                operation in VALID_OPERATIONS,
                f"operacion inválida: {operation}",
                peer_logger,
            )
            validate(filename, "filename vacio", peer_logger)
            validate(
                "\x00" not in filename and len(filename) <= 255,
                f"filename inválido: {filename!r}",
                peer_logger,
            )
            validate(
                protocol in VALID_PROTOCOLS,
                f"protocolo inválido: {protocol}",
                peer_logger,
            )
            if operation == "UPLOAD" and file_size > 0:
                validate(
                    file_size <= MAX_FILE_SIZE,
                    f"file_size {file_size} excede MAX_FILE_SIZE {MAX_FILE_SIZE}",
                    peer_logger,
                )
                statvfs = os.statvfs(self.storage_dir)
                # f_bavail = free blocks available to non-root
                # f_frsize = fragment size (block size)
                free_bytes = statvfs.f_bavail * statvfs.f_frsize
                validate(
                    free_bytes >= file_size + DISK_SAFETY_MARGIN,
                    (
                        f"Espacio insuficiente: libre={free_bytes} "
                        f"requerido={file_size}+{DISK_SAFETY_MARGIN}"
                    ),
                    peer_logger,
                )
        except ValidationError as e:
            self.sock.sendto(create_error_packet(str(e)), addr)
            return
        except Exception as e:
            log_error(peer_logger, "handshake inválido", e)
            self.sock.sendto(create_error_packet("Handshake inválido"), addr)
            return

        incoming_q = queue.Queue()
        handler = ClientHandler(
            addr=addr,
            operation=operation,
            filename=filename,
            protocol_name=protocol,
            storage_dir=self.storage_dir,
            sock=self.sock,
            verbose=self.verbose,
            finished_q=self.finished_q,
            incoming_q=incoming_q,
            file_size=file_size,
        )
        self.clients[addr] = {"handler": handler, "incoming_q": incoming_q}
        handler.start()
        peer_logger.info(
            f"nuevo cliente: {operation} '{filename}' ({protocol}) file_size={file_size}"
        )

    # -------------------------------------------------------------- cleanup --
    def _cleanup_loop(self):
        """Drena `finished_q` y libera entradas de `clients`."""
        while True:
            addr = self.finished_q.get()
            with self._lock:
                self.clients.pop(addr, None)
