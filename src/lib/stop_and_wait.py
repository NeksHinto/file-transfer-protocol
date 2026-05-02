"""
Protocolo Stop & Wait - TP1 Redes 2026

Sender: envia un paquete, espera ACK antes de enviar el siguiente.
        Si no llega ACK antes del timeout, retransmite.
        Timeout adaptativo basado en RTT (igual al algoritmo de TCP).

Receiver: recibe paquetes en orden, envía ACK por cada uno.
          Descarta duplicados y paquetes corruptos.
"""

import time

from lib.logging_utils import log_error
from lib.packet import (
    create_data_packet,
    create_ack_packet,
    create_fin_packet,
    is_ack,
    is_fin,
    is_data,
    is_error,
    parse_packet,
    read_file_chunks,
    MAX_PACKET_SIZE,
)
from lib.protocol import BaseProtocol

MAX_RETRIES = 20
INITIAL_TIMEOUT = 0.5  # RFC 6298 2.1 recommends 1s?
# RFC 6298 TCP timeout calculation parameters:
ALPHA = 0.125  # peso de la nueva muestra de RTT
BETA = 0.25  # peso de la nueva desviación de RTT


class StopAndWait(BaseProtocol):

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
        self._log(
            f"Nuevo RTO adaptativo: {self._timeout:.3f}s " f"(RTT={sample_rtt:.3f}s)"
        )

    def _recv(self, sock, timeout: float, recvfrom_fn=None):
        # ASK: recvfrom_fn ?
        if recvfrom_fn is not None:
            return recvfrom_fn(timeout)
        sock.settimeout(
            timeout
        )  # sets the timeout for blocking socket operations (like recvfrom)
        return sock.recvfrom(
            MAX_PACKET_SIZE
        )  # waits for a packet to arrive and returns the data and sender's address

    # ------------------------------------------------------------------ SENDER
    # kurose stop-&-wait state machine
    def send_file(
        self,
        filepath: str,
        filename: str,
        destination: tuple,
        sock,
        chunks=None,
        recvfrom_fn=None,
    ):
        """Envia un archivo completo al destino usando Stop & Wait."""
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
                send_time = time.time()  # sample rtt
                sock.sendto(packet, destination)

                try:
                    data, _ = self._recv(sock, self._timeout, recvfrom_fn)
                    pkt = parse_packet(data)
                    # corrupted packets are ignored
                    if pkt is None:
                        self.logger.warning(
                            f"SW sender: paquete corrupto ignorado seq={seq_num}"
                        )
                        continue
                    if is_error(pkt):
                        msg = pkt["payload"].decode(errors="replace")
                        self.logger.error(f"SW sender: ERROR del peer: {msg}")
                        raise RuntimeError(f"peer reporto error: {msg}")
                    # old ACKs, duplicates, or out-of-order are ignored
                    if is_ack(pkt) and pkt["ack"] == seq_num:
                        self._log(f"ACK recibido seq: {seq_num}")
                        self._update_rto(time.time() - send_time)
                        delivered = True
                        break
                    # ACK de otro seq: ignorar y esperar
                except (OSError, TimeoutError):  # no ACK received within RTO
                    retries += 1 # packet is retransmitted
                    self.logger.warning(
                        f"SW sender: timeout esperando ACK seq={seq_num}, "
                        f"reintento {retries}/{MAX_RETRIES}"
                    )

            if not delivered:
                log_error(
                    self.logger,
                    f"SW sender: no se entrego seq={seq_num} "
                    f"tras {MAX_RETRIES} reintentos",
                )
                raise RuntimeError(
                    f"No se pudo entregar el paquete seq: {seq_num} "
                    f"tras {MAX_RETRIES} intentos"
                )
            # alternating bit protocol: only one packet is “in flight”
            # Sequence space is just {0, 1}. Kurose 3.4.2 (RDT 3.0) flow control
            seq_num = 1 - seq_num

        # ASK: FIN retransmission loop (no seq validation? any ACK is accepted?)
        # sender assumes receiver likely got everything, but not confirmation?
        fin = create_fin_packet()
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
            except (OSError, TimeoutError):
                pass
        if not fin_acked:
            self.logger.warning(
                "SW sender: cerrando sin ACK(FIN); "
                "el receptor probablemente recibio el archivo"
            )

    # ---------------------------------------------------------------- RECEIVER

    def receive_file(self, filepath: str, sock, sender_addr: tuple, recvfrom_fn=None):
        """Recibe un archivo y lo escribe en filepath."""
        expected_seq = 0

        with open(filepath, "wb") as f:
            while True:
                try:
                    data, addr = self._recv(sock, 10.0, recvfrom_fn)
                except (TimeoutError, OSError) as e:
                    log_error(
                        self.logger,
                        "SW receiver: timeout esperando datos del emisor",
                        e,
                    )
                    break

                pkt = parse_packet(data)
                if pkt is None:
                    self.logger.warning("SW receiver: paquete corrupto descartado")
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
                        # mismatch -> re-ACK the previous (so the sender unblocks if its ACK was lost)
                        # kurose duplicate-detection rule 3.4.2
                        self._log(
                            f"Paquete duplicado seq: {pkt['seq']} "
                            f"(esperado: {expected_seq}) - re-ACK"
                        )
                        sock.sendto(create_ack_packet(1 - expected_seq), sender_addr)
                else:
                    self.logger.warning(
                        f"SW receiver: paquete con flags inesperadas "
                        f"({pkt['flags']:#04x}) descartado"
                    )
