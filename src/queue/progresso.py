"""Agregação de progresso por stream. SPEC 10.4.

No caminho DASH multi-formato, vídeo e áudio baixam em threads separadas e
cada uma chama o hook com os SEUS bytes (RESEARCH 3.4, caso 4). Sem somar por
format_id, a barra de progresso pula entre streams.

Ticket: T5.
"""

import threading

from ..domain.models import Progresso


class AgregadorProgresso:
    """Guarda o último Progresso de cada stream e soma. Thread-safe."""

    def __init__(self):
        self._lock = threading.Lock()
        self._por_stream: dict[str, Progresso] = {}

    def atualizar(self, format_id: str | None, progresso: Progresso) -> None:
        raise NotImplementedError("T5")

    def total(self) -> Progresso:
        raise NotImplementedError("T5")
