"""Modelos do domínio.

Fronteira anticorrupção contra o info_dict do yt-dlp, que tem centenas de
campos, não é garantidamente um dict e muda entre versões (SPEC 5.5).

Ticket: T2.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class EstadoJob(str, Enum):
    NA_FILA = "na_fila"
    BAIXANDO = "baixando"
    CONCLUIDO = "concluido"
    FALHOU = "falhou"
    CANCELADO = "cancelado"
    INTERROMPIDO = "interrompido"


ESTADOS_TERMINAIS = frozenset({
    EstadoJob.CONCLUIDO,
    EstadoJob.FALHOU,
    EstadoJob.CANCELADO,
    EstadoJob.INTERROMPIDO,
})

# Transições legais. SPEC 10.2.
TRANSICOES = {
    EstadoJob.NA_FILA: {EstadoJob.BAIXANDO, EstadoJob.CANCELADO},
    EstadoJob.BAIXANDO: {EstadoJob.CONCLUIDO, EstadoJob.FALHOU, EstadoJob.INTERROMPIDO},
    EstadoJob.CONCLUIDO: set(),
    EstadoJob.FALHOU: set(),
    EstadoJob.CANCELADO: set(),
    EstadoJob.INTERROMPIDO: set(),
}


@dataclass(frozen=True)
class Formato:
    """Um stream disponível. Subconjunto do que o yt-dlp devolve."""
    format_id: str
    ext: str
    resolucao: str | None
    fps: float | None
    vcodec: str | None
    acodec: str | None
    tbr: float | None
    tamanho_bytes: int | None


@dataclass(frozen=True)
class Video:
    """Metadados de um vídeo, obtidos sem baixar."""
    video_id: str
    extractor: str
    url_canonica: str
    titulo: str
    canal: str | None
    duracao_s: int | None
    thumbnail_url: str | None
    data_upload: str | None          # AAAAMMDD
    formatos: tuple[Formato, ...]

    @classmethod
    def de_info_dict(cls, info: dict) -> "Video":
        """Converte o info_dict do yt-dlp neste modelo.

        Puro: recebe um dict já pronto, não chama o yt-dlp.
        """
        raise NotImplementedError("T2")


@dataclass(frozen=True)
class Progresso:
    """Instantâneo de progresso.

    Imutável de propósito: o hook SUBSTITUI o objeto sob lock, nunca muta campo
    a campo (SPEC 10.4).
    """
    baixados: int
    total: int | None
    velocidade_bps: float | None
    eta_s: int | None

    @property
    def percentual(self) -> float | None:
        raise NotImplementedError("T5")


@dataclass
class Job:
    """Um trabalho na fila."""
    id: str
    video: Video
    perfil: str
    projeto: str
    estado: EstadoJob
    criado_em: datetime
    progresso: Progresso | None = None
    caminho_final: str | None = None
    motivo_falha: str | None = None
    mensagem_falha: str | None = None

    def transicionar(self, novo: EstadoJob) -> None:
        """Aplica uma transição, recusando as ilegais.

        Levanta TransicaoIlegal. Ticket T2.
        """
        raise NotImplementedError("T2")
