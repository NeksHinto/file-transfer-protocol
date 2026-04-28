"""
Protocolo Selective Repeat – TP1 Redes 2026
"""

import logging
import time
from collections import OrderedDict

from lib.packet import (
    create_data_packet,
    create_ack_packet,
    create_fin_packet,
    is_ack,
    is_fin,
    is_data,
    parse_packet,
    read_file_chunks,
    MAX_PACKET_SIZE,
    MAX_SEQ,
)
from lib.protocol import BaseProtocol

logger = logging.getLogger("SELECTIVEREPEAT")

# Parámetros del protocolo
WINDOW_SIZE = 4                # tamaño de la ventana de envío/recepción
MAX_RETRIES = 20               # reintentos totales por paquete
INITIAL_TIMEOUT = 0.5
ALPHA = 0.125
BETA = 0.25

class SelectiveRepeat(BaseProtocol):
    def __init__(self, verbose: bool = False):
        super().__init__(verbose)
        self._estimated_rtt = INITIAL_TIMEOUT
        self._dev_rtt = 0.0
        self._timeout = INITIAL_TIMEOUT

    def _log(self, msg):
        if self.verbose:
            logger.debug(msg)

    # ------------------------------------------------------------------ RTO
    def _update_rto(self, sample_rtt: float):
        self._estimated_rtt = (1 - ALPHA) * self._estimated_rtt + ALPHA * sample_rtt
        self._dev_rtt = (1 - BETA) * self._dev_rtt + BETA * abs(
            sample_rtt - self._estimated_rtt
        )
        self._timeout = max(0.05, min(1.0, self._estimated_rtt + 4 * self._dev_rtt))
        self._log(f"Nuevo RTO: {self._timeout:.3f}s (RTT={sample_rtt:.3f}s)")

    # ------------------------------------------------------------------ RECV
    def _recv(self, sock, timeout: float, recvfrom_fn=None):
        if recvfrom_fn is not None:
            return recvfrom_fn(timeout)
        sock.settimeout(timeout)
        return sock.recvfrom(MAX_PACKET_SIZE)

    def _in_window(self, seq: int, base: int, size: int) -> bool:
        return ((seq - base) % MAX_SEQ) < size

    def _is_previous_window(self, seq: int, base: int, size: int) -> bool:
        return ((base - seq) % MAX_SEQ) <= size

    # ================================================================
    #                          SENDER
    # ================================================================
    def send_file(
        self,
        filepath: str,
        filename: str,
        destination: tuple,
        sock,
        chunks=None,
        recvfrom_fn=None,
    ):
        """
        Por implementar: lógica de envío con ventana deslizante y
        retransmisión selectiva.
        """
        self._log("Selective Repeat SENDER: aún no implementado.")
        raise NotImplementedError("send_file de SelectiveRepeat no implementado")
        # ---------------------------------------------------------

    # ================================================================
    #                         RECEIVER
    # ================================================================
    def receive_file(self, filepath: str, sock, sender_addr: tuple, recvfrom_fn=None):
        """
        Por implementar: buffer circular/ordenado, ACKs selectivos,
        escritura ordenada de los datos.
        """
        self._log("Selective Repeat RECEIVER: aún no implementado.")
        raise NotImplementedError("receive_file de SelectiveRepeat no implementado")
        # ---------------------------------------------------------
