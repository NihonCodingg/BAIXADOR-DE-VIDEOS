"""Thread de trabalho. UM download por vez. SPEC 10.4.

Ticket: T5.
"""

import threading


class Worker:
    """Consome a fila numa única thread.

    Recebe o downloader por injeção para que os testes usem um dublê e não
    toquem a rede.
    """

    def __init__(self, fila, downloader, historico):
        self._fila = fila
        self._downloader = downloader
        self._historico = historico
        self._thread: threading.Thread | None = None
        self._parar = threading.Event()

    def iniciar(self) -> None:
        raise NotImplementedError("T5")

    def parar(self, timeout: float = 5.0) -> None:
        """Sinaliza parada e aguarda. Job em andamento vira `interrompido`."""
        raise NotImplementedError("T5")

    def _laco(self) -> None:
        raise NotImplementedError("T5")
