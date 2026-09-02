"""Estado da fila, protegido por lock. SPEC 10.

O lock não é precaução: o progress hook pode ser chamado de threads criadas
pelo próprio yt-dlp, sem configuração especial (RESEARCH 3.4, caso 4).

Regra do hook: adquire o lock apenas para SUBSTITUIR o objeto Progresso do
job. Nunca muta campo a campo, nunca faz I/O.

Ticket: T5.
"""

import queue
import threading

from ..domain.models import EstadoJob, Job, Progresso


class Fila:
    def __init__(self):
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._ordem: list[str] = []
        self._pendentes: queue.Queue[str] = queue.Queue()

    def adicionar(self, job: Job) -> str:
        """Levanta ValueError se o id já existe."""
        raise NotImplementedError("T5")

    def proximo(self, timeout: float | None = None) -> Job | None:
        """Retira o próximo job pendente e o coloca em BAIXANDO, sob o mesmo
        lock — para um cancelar() não entrar na fresta. Descarta os
        cancelados. None se nada chegar dentro do timeout."""
        raise NotImplementedError("T5")

    def atualizar_progresso(self, job_id: str, progresso: Progresso) -> None:
        """Chamado pelo progress hook, possivelmente de outra thread.
        NUNCA levanta: uma exceção aqui derruba o download. Ignora job
        inexistente ou terminal."""
        raise NotImplementedError("T5")

    def transicionar(self, job_id: str, novo: EstadoJob) -> None:
        """KeyError se o job não existe; TransicaoIlegal se a regra proíbe."""
        raise NotImplementedError("T5")

    def concluir(self, job_id: str, caminho: str) -> None:
        raise NotImplementedError("T5")

    def falhar(self, job_id: str, *, motivo: str, mensagem: str) -> None:
        raise NotImplementedError("T5")

    def cancelar(self, job_id: str) -> bool:
        """Só cancela job em `na_fila`. SPEC 10.5.

        Devolve False se o job já começou, é terminal ou não existe — a API
        traduz isso em 409/404.
        """
        raise NotImplementedError("T5")

    def interromper_em_andamento(self) -> list[str]:
        """Todo job em BAIXANDO vira INTERROMPIDO. Devolve os ids."""
        raise NotImplementedError("T5")

    def obter(self, job_id: str) -> Job | None:
        """Cópia do job, ou None."""
        raise NotImplementedError("T5")

    def instantaneo(self) -> list[Job]:
        """Cópias de todos os jobs, na ordem de chegada, sob lock."""
        raise NotImplementedError("T5")
