"""Thread de trabalho. UM download por vez. SPEC 10.4.

Ticket: T5.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass

from ..domain.models import Job


@dataclass(frozen=True)
class Preparacao:
    """O que o worker precisa para chamar o adapter: resolvido pelo pipeline
    (perfil -> opções, projeto + nome -> destino) e injetado como callable."""
    url: str
    opcoes: dict
    destino: str


class Worker:
    """Consome a fila numa única thread daemon.

    Downloader, histórico e `preparar` entram por injeção: os testes usam
    dublês e não tocam a rede.
    """

    def __init__(self, fila, downloader, historico,
                 preparar: Callable[[Job], Preparacao]):
        self._fila = fila
        self._downloader = downloader
        self._historico = historico
        self._preparar = preparar
        self._thread: threading.Thread | None = None
        self._parar = threading.Event()

    @property
    def vivo(self) -> bool:
        raise NotImplementedError("T5")

    def iniciar(self) -> None:
        raise NotImplementedError("T5")

    def parar(self, timeout: float = 5.0) -> None:
        """Sinaliza parada e aguarda. Job em andamento vira `interrompido`."""
        raise NotImplementedError("T5")

    def _laco(self) -> None:
        raise NotImplementedError("T5")
