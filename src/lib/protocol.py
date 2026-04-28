"""Protocolos de transferencia confiable (Stop & Wait, Selective Repeat)."""

from abc import ABC, abstractmethod


class BaseProtocol(ABC):
    """Interfaz común que todo protocolo RDT debe implementar."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    @abstractmethod
    def send_file(
        self,
        filepath: str,
        filename: str,
        destination: tuple,
        sock,
        chunks=None,
        recvfrom_fn=None,
    ):
        """Envía un archivo al destino."""
        ...

    @abstractmethod
    def receive_file(
        self, filepath: str, sock, sender_addr: tuple, recvfrom_fn=None
    ):
        """Recibe un archivo y lo guarda en filepath."""
        ...


def get_protocol(name: str, verbose: bool = False) -> BaseProtocol:
    name = name.lower()
    if name in ("stop_and_wait", "snw", "s&w"):
        from lib.stop_and_wait import StopAndWait
        return StopAndWait(verbose)
    # elif name in ("selective_repeat", "sr"):
    #     from lib.selective_repeat import SelectiveRepeat
    #     return SelectiveRepeat(verbose)
    raise ValueError(f"Protocolo desconocido: {name}")
