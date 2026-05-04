"""
ClientHandler

Maneja una sesión completa (UPLOAD o DOWNLOAD) usando el protocolo
elegido por el cliente en el handshake.
"""

import os
import queue
import threading

from lib.logging_utils import (
    ValidationError,
    get_logger,
    log_error,
    validate,
)
from lib.messages import create_ack_packet, create_error_packet
from lib.protocol import get_protocol


class ClientHandler(threading.Thread):
    """Maneja una sesion (un solo upload/download) contra un peer."""

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

    # ----------------------------------------------------------- recvfrom --
    def _recvfrom_client(self, timeout: float):
        """Bloquea hasta que el dispatcher meta un paquete del peer."""
        try:
            return self.incoming_q.get(timeout=timeout)
        except queue.Empty as e:
            raise TimeoutError() from e

    # ----------------------------------------------------------------- run --
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

    # -------------------------------------------------------------- helpers --
    def _send_error(self, msg: str) -> None:
        try:
            self.sock.sendto(create_error_packet(msg), self.addr)
        except OSError as e:
            log_error(self.logger, "no se pudo enviar ERROR", e)

    def _upload(self, protocol):
        filepath = os.path.join(self.storage_dir, self.filename)
        self.sock.sendto(create_ack_packet(0), self.addr)
        protocol.receive_file(
            filepath,
            self.sock,
            self.addr,
            recvfrom_fn=self._recvfrom_client,
        )
        self.logger.info(f"archivo guardado: {filepath}")

    def _download(self, protocol):
        filepath = os.path.join(self.storage_dir, self.filename)
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
