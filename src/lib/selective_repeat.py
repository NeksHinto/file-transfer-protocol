"""
Protocolo Selective Repeat - TP1 Redes 2026
"""

import socket
import time

from lib.chunker import read_file_chunks
from lib.flags import is_ack, is_data, is_error, is_fin
from lib.logging_utils import log_error
from lib.messages import create_ack_packet, create_data_packet, create_fin_packet
from lib.protocol import BaseProtocol
from lib.wire import MAX_PACKET_SIZE, MAX_SEQ, parse_packet

# Parámetros del protocolo
WINDOW_SIZE = 16  # tamaño de la ventana de envío/recepción (control de flujo)
MAX_RETRIES = 20  # reintentos totales por paquete
INITIAL_TIMEOUT = 0.5
ALPHA = 0.125
BETA = 0.25


class SelectiveRepeat(BaseProtocol):
    def __init__(self, verbose: bool = False, logger=None):
        super().__init__(verbose, logger=logger)
        self._estimated_rtt = INITIAL_TIMEOUT
        self._dev_rtt = 0.0
        self._timeout = INITIAL_TIMEOUT

    def _log(self, msg):
        if self.verbose:
            self.logger.debug(msg)

    def _update_rto(self, sample_rtt: float):
        self._estimated_rtt = (1 - ALPHA) * self._estimated_rtt + ALPHA * sample_rtt
        self._dev_rtt = (1 - BETA) * self._dev_rtt + BETA * abs(
            sample_rtt - self._estimated_rtt
        )
        self._timeout = max(0.05, min(1.0, self._estimated_rtt + 4 * self._dev_rtt))
        self._log(f"Nuevo RTO: {self._timeout:.3f}s (RTT={sample_rtt:.3f}s)")

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
        packets = {
            seq: create_data_packet(seq % MAX_SEQ, payload)
            for seq, payload in enumerate(payloads)
        }

        base = 0
        next_seq = 0
        acked = set()
        sent_not_acked = set()
        last_send_ts = {}
        retries = {}

        while base < total:
            while next_seq < total and next_seq < base + WINDOW_SIZE:
                sock.sendto(packets[next_seq], destination)
                sent_not_acked.add(next_seq)
                last_send_ts[next_seq] = time.time()
                retries.setdefault(next_seq, 0)
                self._log(f"SR send seq={next_seq} base={base}")
                next_seq = (next_seq + 1) % MAX_SEQ
                next_seq = (next_seq + 1) % MAX_SEQ

            try:
                data, _ = self._recv(sock, self._timeout, recvfrom_fn)
                pkt = parse_packet(data)
                if pkt is None:
                    self.logger.warning("SR sender: paquete corrupto ignorado")
                elif is_error(pkt):
                    msg = pkt["payload"].decode(errors="replace")
                    self.logger.error(f"SR sender: ERROR del peer: {msg}")
                    raise RuntimeError(f"peer reporto error: {msg}")
                elif is_ack(pkt):
                    ack = pkt["ack"]
                    if 0 <= ack < total and ack not in acked:
                        acked.add(ack)
                        sent_not_acked.discard(ack)
                        sample = time.time() - last_send_ts.get(ack, time.time())
                        self._update_rto(sample)
                        self._log(f"SR ack seq={ack} (base={base})")
                        while base in acked:
                            # sliding the window when the lowest unacknowledged packet is ACKed
                            base = (base + 1) % MAX_SEQ
            except (OSError, socket.timeout, TimeoutError):
                pass

            now = time.time()
            for seq in list(sent_not_acked):
                sent_at = last_send_ts.get(seq, now)
                if now - sent_at >= self._timeout:
                    retries[seq] = retries.get(seq, 0) + 1
                    if retries[seq] > MAX_RETRIES:
                        log_error(
                            self.logger,
                            f"SR sender: no se entregó seq={seq} "
                            f"tras {MAX_RETRIES} reintentos",
                        )
                        raise RuntimeError(
                            "No se pudo entregar el paquete "
                            f"seq: {seq} tras {MAX_RETRIES} intentos"
                        )
                    sock.sendto(packets[seq], destination)
                    last_send_ts[seq] = now
                    self.logger.warning(
                        f"SR sender: timeout seq={seq} "
                        f"-> reenvío ({retries[seq]}/{MAX_RETRIES})"
                    )

        # FIN con reintentos. `next_seq=total` da al receptor un check
        # opcional ("recibí total chunks"); tambien correlaciona el ACK.
        fin = create_fin_packet(next_seq=total % MAX_SEQ)
        fin_acked = False
        for attempt in range(1, MAX_RETRIES + 1):
            self._log(f"FIN enviado (intento {attempt}/{MAX_RETRIES})")
            sock.sendto(fin, destination)
            try:
                data, _ = self._recv(sock, self._timeout, recvfrom_fn)
                pkt = parse_packet(data)
                if pkt and is_ack(pkt):
                    self._log("FIN ACK recibido")
                    fin_acked = True
                    break
            except (OSError, socket.timeout, TimeoutError):
                pass
        if not fin_acked:
            self.logger.warning(
                "SR sender: cerrando sin ACK(FIN); "
                "el receptor probablemente recibió el archivo"
            )

    # ================================================================
    #                         RECEIVER
    # ================================================================
    def receive_file(self, filepath: str, sock, sender_addr: tuple, recvfrom_fn=None):
        self._log(f"Iniciando recepcion en {filepath}")

        received_buffer = {}
        expected_base = 0
        finished = False

        with open(filepath, "wb") as f:
            while not finished:
                try:
                    data, addr = self._recv(sock, self._timeout, recvfrom_fn)
                    packet = parse_packet(data)

                    if packet is None:
                        self.logger.warning("SR receiver: paquete corrupto descartado")
                        continue

                    seq = packet["seq"]

                    if is_fin(packet):
                        self._log("FIN recibido. Enviando ACK para FIN.")
                        ack_pkt = create_ack_packet(seq)
                        sock.sendto(ack_pkt, addr)
                        finished = True
                        break

                    if is_data(packet):
                        if self._in_window(seq, expected_base, WINDOW_SIZE):
                            self._log(f"Paquete {seq} en ventana - ACK + buffer")
                            ack_pkt = create_ack_packet(seq)
                            sock.sendto(ack_pkt, addr)

                            if seq not in received_buffer:
                                received_buffer[seq] = packet["payload"]

                            while expected_base in received_buffer:
                                data_to_write = received_buffer.pop(expected_base)
                                f.write(data_to_write)
                                self._log(f"Entregando paquete {expected_base}")
                                expected_base = (expected_base + 1) % MAX_SEQ
                        elif self._is_previous_window(seq, expected_base, WINDOW_SIZE):
                            self._log(f"Paquete {seq} antiguo (duplicado) - re-ACK")
                            ack_pkt = create_ack_packet(seq)
                            sock.sendto(ack_pkt, addr)
                        else:
                            self.logger.warning(
                                f"SR receiver: seq={seq} fuera de rango "
                                f"(base={expected_base}) - descartado"
                            )
                    else:
                        self.logger.warning(
                            f"SR receiver: paquete con flags inesperadas "
                            f"({packet['flags']:#04x}) descartado"
                        )

                except (TimeoutError, socket.timeout):
                    continue
                except OSError as e:
                    log_error(self.logger, "SR receiver: error de socket", e)
                    break
                except Exception as e:
                    log_error(self.logger, "SR receiver: error inesperado", e)
                    break

        self._log("Recepcion finalizada.")
