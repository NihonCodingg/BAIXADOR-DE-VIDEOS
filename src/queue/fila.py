"""Estado da fila, protegido por lock. SPEC 10.

O lock não é precaução: o progress hook pode ser chamado de threads criadas
pelo próprio yt-dlp, sem configuração especial (RESEARCH 3.4, caso 4).

Regra do hook: adquire o lock apenas para SUBSTITUIR o objeto Progresso do
job. Nunca muta campo a campo, nunca faz I/O.

Ticket: T5.
"""

import threading

from ..domain.models import EstadoJob, Job, Progresso


class Fila:
    def __init__(self):
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._pendentes: list[str] = []

    def adicionar(self, job: Job) -> str:
        raise NotImplementedError("T5")

    def proximo(self) -> Job | None:
        """Retira o próximo job pendente. Descarta os já cancelados."""
        raise NotImplementedError("T5")

    def atualizar_progresso(self, job_id: str, progresso: Progresso) -> None:
        """Chamado pelo progress hook, possivelmente de outra thread."""
        raise NotImplementedError("T5")

    def transicionar(self, job_id: str, novo: EstadoJob) -> None:
        raise NotImplementedError("T5")

    def cancelar(self, job_id: str) -> bool:
        """Só cancela job em `na_fila`. SPEC 10.5.

        Devolve False se o job já começou — a API traduz isso em 409.
        """
        raise NotImplementedError("T5")

    def instantaneo(self) -> list[Job]:
        """Cópia consistente do estado de todos os jobs, sob lock."""
        raise NotImplementedError("T5")
