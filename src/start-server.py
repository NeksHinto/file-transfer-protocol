"""
start-server: Servidor UDP concurrente de transferencia de archivos.
Protocolo: Stop & Wait.

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

from lib.packet import (  # noqa: E402
    parse_packet,
    create_ack_packet,
    create_error_packet,
    is_handshake,
    MAX_PACKET_SIZE,
)
from lib.protocol import get_protocol  # noqa: E402

logger = logging.getLogger("SERVER")


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
        self.protocol_name = protocol_name  # nuevo atributo
        self.storage_dir = storage_dir
        self.sock = sock
        self.verbose = verbose
        self.finished_q = finished_q
        self.incoming_q = incoming_q

    def _recvfrom_client(self, timeout: float):
        try:
            return self.incoming_q.get(timeout=timeout)
        except queue.Empty as e:
            raise TimeoutError() from e

    def run(self):
        logger.info(f"[{self.addr}] {self.operation} '{self.filename}' ({self.protocol_name})")
        try:
            protocol = get_protocol(self.protocol_name, verbose=self.verbose)
            if self.operation == "UPLOAD":
                self._upload(protocol)
            elif self.operation == "DOWNLOAD":
                self._download(protocol)
            else:
                self.sock.sendto(
                    create_error_packet(f"Operacion desconocida: {self.operation}"),
                    self.addr,
                )
        except Exception as e:
            logger.error(f"[{self.addr}] Error: {e}")
            try:
                self.sock.sendto(create_error_packet(str(e)), self.addr)
            except Exception:
                pass
        finally:
            self.finished_q.put(self.addr)
            logger.info(f"[{self.addr}] Finalizado")

    def _upload(self, protocol):
        filepath = os.path.join(self.storage_dir, self.filename)
        self.sock.sendto(create_ack_packet(0), self.addr)
        protocol.receive_file(
            filepath,
            self.sock,
            self.addr,
            recvfrom_fn=self._recvfrom_client,
        )
        logger.info(f"[{self.addr}] Archivo guardado: {filepath}")

    def _download(self, protocol):
        filepath = os.path.join(self.storage_dir, self.filename)
        if not os.path.isfile(filepath):
            self.sock.sendto(
                create_error_packet(f"Archivo no encontrado: {self.filename}"),
                self.addr,
            )
            logger.warning(f"[{self.addr}] Archivo no encontrado: {self.filename}")
            return
        self.sock.sendto(create_ack_packet(0), self.addr)
        protocol.send_file(
            filepath,
            self.filename,
            self.addr,
            self.sock,
            recvfrom_fn=self._recvfrom_client,
        )
        logger.info(f"[{self.addr}] Archivo enviado: {self.filename}")


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

    def start(self):
        os.makedirs(self.storage_dir, exist_ok=True)
        self.sock.bind((self.host, self.port))
        logger.info(f"Servidor iniciado en {self.host}:{self.port}")
        logger.info(f"Storage: {self.storage_dir}")

        threading.Thread(target=self._cleanup_loop, daemon=True).start()

        self.sock.settimeout(1.0)
        while True:
            try:
                data, addr = self.sock.recvfrom(MAX_PACKET_SIZE + 64)
            except OSError:
                continue

            pkt = parse_packet(data)
            if pkt is None:
                logger.warning(f"Paquete corrupto de {addr}, descartado")
                continue

            with self._lock:
                client = self.clients.get(addr)
                if client is not None:
                    client["incoming_q"].put((data, addr))
                elif is_handshake(pkt):
                    # TODO: Manejo errores lado servidor
                    self._spawn(addr, pkt)

    def _spawn(self, addr, pkt):
        try:
            parts = pkt["payload"].decode().split("|")
            operation = parts[0]
            filename = os.path.basename(parts[1])
            protocol = parts[2] if len(parts) > 2 else "stop_and_wait"
        except Exception:
            self.sock.sendto(create_error_packet("Handshake invalido"), addr)
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
        )
        self.clients[addr] = {
            "handler": handler,
            "incoming_q": incoming_q,
        }
        handler.start()
        logger.info(f"[{addr}] Nuevo cliente: {operation} '{filename}' ({protocol})")

    def _cleanup_loop(self):
        while True:
            addr = self.finished_q.get()
            with self._lock:
                self.clients.pop(addr, None)


# --------------------------------------------------------------- entrypoint --


def main():
    parser = argparse.ArgumentParser(
        description="Servidor Stop & Wait UDP - TP1 Redes 2026"
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
    os.makedirs("logs", exist_ok=True)
    logging.basicConfig(
        level=level,
        format="[%(levelname)s] %(name)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("logs/server.log", mode="a"),
        ],
    )

    server = Server(args.host, args.port, args.storage, args.verbose)
    try:
        server.start()
    except KeyboardInterrupt:
        logger.info("Servidor detenido")


if __name__ == "__main__":
    main()
