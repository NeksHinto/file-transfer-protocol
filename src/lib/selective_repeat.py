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
        """Envía un archivo completo al destino usando Selective Repeat."""
        if chunks is None:
            chunks = list(read_file_chunks(filepath))
        else:
            chunks = list(chunks)
        total = len(chunks)
        self._log(
            f"Archivo dividido en {total} chunks de hasta " f"{MAX_PACKET_SIZE} bytes"
        )

        payloads = [chunk for _, chunk in chunks]
        packets = {seq: create_data_packet(seq, payload) for seq, payload in enumerate(payloads)}


        base = 0
        next_seq = 0
        acked = set()
        sent_not_acked = set()
        last_send_ts = {}
        retries = {}

        while base < total:
            while next_seq < total and next_seq < base + self.window_size:
                sock.sendto(packets[next_seq], destination)
                sent_not_acked.add(next_seq)
                last_send_ts[next_seq] = time.time()
                retries.setdefault(next_seq, 0)
                self._log(f"SR send seq={next_seq} base={base}")
                next_seq += 1

            try:
                data, _ = self._recv(sock, self._timeout, recvfrom_fn)
                pkt = parse_packet(data)
                if pkt and is_ack(pkt):
                    ack = pkt["ack"]
                    if 0 <= ack < total and ack not in acked:
                        acked.add(ack)
                        sent_not_acked.discard(ack)
                        sample = time.time() - last_send_ts.get(ack, time.time())
                        self._update_rto(sample)
                        self._log(f"SR ack seq={ack} (base={base})")
                        while base in acked:
                            base += 1
            except OSError:
                pass

            now = time.time()
            for seq in list(sent_not_acked):
                sent_at = last_send_ts.get(seq, now)
                if now - sent_at >= self._timeout:
                    retries[seq] = retries.get(seq, 0) + 1
                    if retries[seq] > MAX_RETRIES:
                        raise RuntimeError(
                            "No se pudo entregar el paquete "
                            f"seq: {seq} tras {MAX_RETRIES} intentos"
                        )
                    sock.sendto(packets[seq], destination)
                    last_send_ts[seq] = now
                    self._log(
                        f"SR timeout seq={seq} -> resend ({retries[seq]}/{MAX_RETRIES})"
                    )

        # Enviar FIN con reintentos
        fin = create_fin_packet()
        for _ in range(MAX_RETRIES):
            self._log("FIN enviado")
            sock.sendto(fin, destination)
            try:
                data, _ = self._recv(sock, self._timeout, recvfrom_fn)
                pkt = parse_packet(data)
                if pkt and is_ack(pkt):
                    self._log("FIN ACK recibido")
                    break
            except OSError:
                pass
            except TimeoutError:
                pass

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
