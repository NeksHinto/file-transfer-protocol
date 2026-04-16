"""
Protocolo Stop & Wait - TP1 Redes 2026

Sender: envia un paquete, espera ACK antes de enviar el siguiente.
        Si no llega ACK antes del timeout, retransmite.
        Timeout adaptativo basado en RTT (igual al algoritmo de TCP).

Receiver: recibe paquetes en orden, envía ACK por cada uno.
          Descarta duplicados y paquetes corruptos.
"""

import logging
import time

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
)

logger = logging.getLogger("STOPANDWAIT")

MAX_RETRIES = 20
INITIAL_TIMEOUT = 0.5
ALPHA = 0.125  # peso de la nueva muestra de RTT
BETA = 0.25  # peso de la nueva desviación de RTT


class StopAndWait:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._estimated_rtt = INITIAL_TIMEOUT
        self._dev_rtt = 0.0
        self._timeout = INITIAL_TIMEOUT

    def _log(self, msg):
        if self.verbose:
            logger.debug(msg)

    def _update_rto(self, sample_rtt: float):
        self._estimated_rtt = (1 - ALPHA) * self._estimated_rtt + ALPHA * sample_rtt
        self._dev_rtt = (1 - BETA) * self._dev_rtt + BETA * abs(
            sample_rtt - self._estimated_rtt
        )
        self._timeout = max(0.05, min(1.0, self._estimated_rtt + 4 * self._dev_rtt))
        self._log(
            f"Nuevo RTO adaptativo: {self._timeout:.3f}s " f"(RTT={sample_rtt:.3f}s)"
        )

    # ------------------------------------------------------------------ SENDER

    def send_file(
        self,
        filepath: str,
        filename: str,
        destination: tuple,
        sock,
        chunks=None,
    ):
        """Envía un archivo completo al destino usando Stop & Wait."""
        if chunks is None:
            chunks = list(read_file_chunks(filepath))
        else:
            chunks = list(chunks)
        total = len(chunks)
        self._log(
            f"Archivo dividido en {total} chunks de hasta " f"{MAX_PACKET_SIZE} bytes"
        )

        seq_num = 0
        for idx, (_, chunk) in enumerate(chunks):
            packet = create_data_packet(seq_num, chunk)
            retries = 0
            delivered = False

            while retries < MAX_RETRIES:
                self._log(
                    f"Paquete enviado seq: {seq_num} | chunk {idx + 1}/{total}"
                    f" | size: {len(chunk)} bytes"
                )
                send_time = time.time()
                sock.sendto(packet, destination)
                sock.settimeout(self._timeout)

                try:
                    data, _ = sock.recvfrom(MAX_PACKET_SIZE)
                    pkt = parse_packet(data)
                    if pkt and is_ack(pkt) and pkt["ack"] == seq_num:
                        self._log(f"ACK recibido seq: {seq_num}")
                        self._update_rto(time.time() - send_time)
                        delivered = True
                        break
                    # ACK de otro seq o paquete corrupto: ignorar y esperar
                except OSError:
                    retries += 1
                    self._log(
                        f"Timeout esperando ACK seq: {seq_num}, "
                        f"reintentando... (intento {retries}/{MAX_RETRIES})"
                    )

            if not delivered:
                raise RuntimeError(
                    f"No se pudo entregar el paquete seq: {seq_num} "
                    f"tras {MAX_RETRIES} intentos"
                )

            seq_num = 1 - seq_num  # alterna 0 / 1

        # Enviar FIN con reintentos
        fin = create_fin_packet()
        for _ in range(MAX_RETRIES):
            self._log("FIN enviado")
            sock.sendto(fin, destination)
            sock.settimeout(self._timeout)
            try:
                data, _ = sock.recvfrom(MAX_PACKET_SIZE)
                pkt = parse_packet(data)
                if pkt and is_ack(pkt):
                    self._log("FIN ACK recibido")
                    break
            except OSError:
                pass

    # ---------------------------------------------------------------- RECEIVER

    def receive_file(self, filepath: str, sock, sender_addr: tuple):
        """Recibe un archivo y lo escribe en filepath."""
        expected_seq = 0
        sock.settimeout(10.0)

        with open(filepath, "wb") as f:
            while True:
                try:
                    data, addr = sock.recvfrom(MAX_PACKET_SIZE)
                except OSError:
                    logger.error("Timeout esperando datos del emisor")
                    break

                pkt = parse_packet(data)
                if pkt is None:
                    self._log("Paquete corrupto descartado")
                    continue

                if is_fin(pkt):
                    self._log("FIN recibido - transferencia completa")
                    sock.sendto(create_ack_packet(0), sender_addr)
                    break

                if is_data(pkt):
                    if pkt["seq"] == expected_seq:
                        f.write(pkt["payload"])
                        self._log(
                            f"Datos recibidos seq: {pkt['seq']}"
                            f" | size: {len(pkt['payload'])} bytes"
                        )
                        sock.sendto(create_ack_packet(expected_seq), sender_addr)
                        expected_seq = 1 - expected_seq
                    else:
                        # Duplicado: re-ACK del último paquete aceptado
                        self._log(
                            f"Paquete duplicado seq: {pkt['seq']} "
                            f"(esperado: {expected_seq}) - re-ACK"
                        )
                        sock.sendto(create_ack_packet(1 - expected_seq), sender_addr)
