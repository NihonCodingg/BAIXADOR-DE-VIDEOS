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
    """Um stream disponível. Subconjunto do que o yt-dlp devolve.

    `largura` e `altura` existem separadas de `resolucao` porque o teto de
    qualidade é aplicado na MENOR dimensão, e para isso é preciso comparar as
    duas numericamente (SPEC 6.3). `resolucao` é a string de exibição.

    Ambas são opcionais: no fixture real, 12 dos 45 formatos não têm dimensão
    (são só-áudio) e 4 são storyboards.
    """
    format_id: str
    ext: str
    resolucao: str | None
    largura: int | None
    altura: int | None
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


def tem_video(formato: Formato) -> bool:
    """True se o formato carrega stream de vídeo.

    `vcodec` está presente em 45/45 formatos do fixture real, então aqui não há
    o problema de chave ausente que existe em `acodec`.
    """
    raise NotImplementedError("T2")


def tem_audio(formato: Formato) -> bool:
    """True se o formato carrega stream de áudio.

    TRÊS ESTADOS, não dois: tem / não tem / DESCONHECIDO.

    Medido no fixture: a chave `acodec` está AUSENTE em 2 dos 45 formatos
    (233 e 234, manifests HLS com resolution='audio only'). Ausente significa
    "o yt-dlp ainda não sabe", não "não tem áudio".

    A regra:
      acodec == 'none'          -> não tem, explicitamente
      acodec com valor          -> tem
      acodec None (desconhecido) -> tem, SE o formato também não tiver vídeo;
                                    caso contrário assume que não tem
                                    (conservador: um formato de vídeo com
                                    codec de áudio desconhecido é tratado
                                    como só-vídeo, e o merge resolve)

    Tratar 'desconhecido' como 'não tem' faria 233 e 234 não serem nem vídeo
    nem áudio, e eles sumiriam da lista.
    """
    raise NotImplementedError("T2")
