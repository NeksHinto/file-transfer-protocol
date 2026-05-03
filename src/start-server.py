"""
start-server: Servidor UDP concurrente de transferencia de archivos.
Soporta Stop & Wait y Selective Repeat (elegido por el cliente en el handshake).

Uso:
    python start-server.py [-v | -q] [-H ADDR] [-p PORT] [-s DIRPATH]
"""

import argparse
import logging
import os
import queue
import socket
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.logging_utils import (  # noqa: E402
    ValidationError,
    get_logger,
    log_error,
    setup_logging,
    validate,
)
from lib.packet import (  # noqa: E402
    parse_packet,
    create_ack_packet,
    create_error_packet,
    is_handshake,
    MAX_PACKET_SIZE,
)
from lib.protocol import get_protocol  # noqa: E402

VALID_OPERATIONS = {"UPLOAD", "DOWNLOAD"}
VALID_PROTOCOLS = {"stop_and_wait", "sw", "selective_repeat", "sr"}


# ------------------------------------------------------------------ handler --


class ClientHandler(threading.Thread):
    """Un hilo por cliente. Maneja un UPLOAD o DOWNLOAD completo."""

    def __init__(
        self,
        addr,
        operation,
        filename,
        protocol_name,
        storage_dir,
        sock,
        verbose,
        finished_q,
        incoming_q,
    ):
        super().__init__(daemon=True)
        self.addr = addr
        self.operation = operation
        self.filename = filename
        self.protocol_name = protocol_name
        self.storage_dir = storage_dir
        self.sock = sock
        self.verbose = verbose
        self.finished_q = finished_q
        self.incoming_q = incoming_q
        self.logger = get_logger("SERVER", peer=addr)

    def _recvfrom_client(self, timeout: float):
        try:
            return self.incoming_q.get(timeout=timeout)
        except queue.Empty as e:
            raise TimeoutError() from e

    def run(self):
        self.logger.info(
            f"{self.operation} '{self.filename}' protocolo={self.protocol_name}"
        )
        try:
            protocol = get_protocol(
                self.protocol_name,
                verbose=self.verbose,
                logger=self.logger,
            )
            if self.operation == "UPLOAD":
                self._upload(protocol)
            elif self.operation == "DOWNLOAD":
                self._download(protocol)
            else:
                # FIXME; no deberia llegar; _spawn ya valida
                self._send_error(f"Operacion desconocida: {self.operation}")
        except ValidationError as e:
            log_error(self.logger, "validacion", e)
            self._send_error(str(e))
        except Exception as e:
            log_error(self.logger, "error en sesion", e)
            self._send_error(str(e))
        finally:
            self.finished_q.put(self.addr)
            self.logger.info("sesion finalizada")

    def _send_error(self, msg: str) -> None:
        try:
            self.sock.sendto(create_error_packet(msg), self.addr)
        except OSError as e:
            log_error(self.logger, "no se pudo enviar ERROR", e)

    def _resolve_path(self) -> str:
        """Junta storage + filename y exige que quede DENTRO de storage."""
        storage_abs = os.path.abspath(self.storage_dir)
        # enforce all file access stays inside storage_dir (Path traversal protection)
        candidate = os.path.abspath(os.path.join(storage_abs, self.filename))
        validate(
            candidate.startswith(storage_abs + os.sep) or candidate == storage_abs,
            f"path traversal detectado: {self.filename}",
            self.logger,
        )
        return candidate

    def _upload(self, protocol):
        filepath = self._resolve_path()
        self.sock.sendto(create_ack_packet(0), self.addr)
        protocol.receive_file(
            filepath,
            self.sock,
            self.addr,
            recvfrom_fn=self._recvfrom_client,
        )
        self.logger.info(f"archivo guardado: {filepath}")

    def _download(self, protocol):
        filepath = self._resolve_path()
        if not os.path.isfile(filepath):
            msg = f"Archivo no encontrado: {self.filename}"
            self.logger.warning(msg)
            self._send_error(msg)
            return
        if not os.access(filepath, os.R_OK):
            msg = f"Sin permiso de lectura: {self.filename}"
            self.logger.warning(msg)
            self._send_error(msg)
            return
        self.sock.sendto(create_ack_packet(0), self.addr)
        protocol.send_file(
            filepath,
            self.filename,
            self.addr,
            self.sock,
            recvfrom_fn=self._recvfrom_client,
        )
        self.logger.info(f"archivo enviado: {self.filename}")


# ------------------------------------------------------------------- server --


class Server:
    def __init__(self, host, port, storage_dir, verbose):
        self.host = host
        self.port = port
        self.storage_dir = storage_dir
        self.verbose = verbose
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.clients = {}
        self.finished_q = queue.Queue()
        self._lock = threading.Lock()
        self.logger = get_logger("SERVER")

    def start(self):
        os.makedirs(self.storage_dir, exist_ok=True)
        self.sock.bind((self.host, self.port))
        self.logger.info(f"servidor escuchando en {self.host}:{self.port}")
        self.logger.info(f"storage: {os.path.abspath(self.storage_dir)}")

        threading.Thread(target=self._cleanup_loop, daemon=True).start()

        self.sock.settimeout(1.0)
        while True:
            try:
                data, addr = self.sock.recvfrom(
                    MAX_PACKET_SIZE + 64
                )  # Receive all packets from all clients
            except socket.timeout:
                continue
            except OSError as e:
                log_error(self.logger, "recvfrom falló", e)
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
                    # Sin sesión abierta y no es HANDSHAKE: es residual de una
                    # sesión previa o un cliente fuera de protocolo
                    self.logger.debug(
                        f"paquete sin sesión de {addr[0]}:{addr[1]} (flags={pkt['flags']:#04x}) descartado"
                    )

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
            protocol = (parts[2] if len(parts) > 2 else "stop_and_wait").lower()
            file_size = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
            validate(
                operation in VALID_OPERATIONS,
                f"operacion inválida: {operation}",
                peer_logger,
            )
            validate(filename, "filename vacío", peer_logger)
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
        except ValidationError as e:
            self.sock.sendto(create_error_packet(str(e)), addr)
            return
        except Exception as e:
            log_error(peer_logger, "handshake inválido", e)
            self.sock.sendto(create_error_packet("Handshake inválido"), addr)
            return
        # handler creation
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
        )
        self.clients[addr] = {"handler": handler, "incoming_q": incoming_q}
        handler.start()
        peer_logger.info(
            f"nuevo cliente: {operation} '{filename}' ({protocol}) file_size={file_size}"
        )

    # removes finished sessions to prevent memory leaks and stale sessions
    def _cleanup_loop(self):
        while True:
            addr = self.finished_q.get()
            with self._lock:
                self.clients.pop(addr, None)


# --------------------------------------------------------------- entrypoint --


# cli parsin, logging setup, server startup
def main():
    parser = argparse.ArgumentParser(
        description="Servidor UDP RDT (Stop & Wait / Selective Repeat) - TP1 Redes 2026"
    )
    verb = parser.add_mutually_exclusive_group()
    verb.add_argument(
        "-v", "--verbose", action="store_true", help="Aumentar verbosidad"
    )
    verb.add_argument("-q", "--quiet", action="store_true", help="Reducir verbosidad")
    parser.add_argument(
        "-H", "--host", default="0.0.0.0", help="IP del servidor (default: 0.0.0.0)"
    )
    parser.add_argument(
        "-p", "--port", type=int, default=9000, help="Puerto (default: 9000)"
    )
    parser.add_argument(
        "-s",
        "--storage",
        default="./storage",
        help="Directorio de almacenamiento (default: ./storage)",
    )
    args = parser.parse_args()

    level = (
        logging.DEBUG
        if args.verbose
        else (logging.WARNING if args.quiet else logging.INFO)
    )
    setup_logging(level=level, log_file="logs/server.log")
    logger = get_logger("SERVER")

    if not (1 <= args.port <= 65535):
        log_error(logger, f"puerto fuera de rango: {args.port}")
        sys.exit(2)

    server = Server(args.host, args.port, args.storage, args.verbose)
    try:
        server.start()
    except KeyboardInterrupt:
        logger.info("servidor detenido")
    except Exception as e:
        log_error(logger, "fallo del servidor", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
