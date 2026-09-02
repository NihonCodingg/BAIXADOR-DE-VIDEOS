"""Traduz exceção do yt-dlp para MotivoFalha do domínio.

Fica aqui, e não no domínio, porque precisa conhecer as classes do yt-dlp
(SPEC 5.6).

O ponto central (RESEARCH 6.2): o yt-dlp embrulha quase tudo em DownloadError
e guarda a exceção real em `.exc_info`. Classificar olhando só o DownloadError
transforma tudo em "erro genérico".

A classificação por mensagem é frágil por natureza — o texto vem do site, não
do yt-dlp. Por isso é uma TABELA de dados com fallback obrigatório que mostra a
mensagem original.

Ticket: T1.
"""

from dataclasses import dataclass, field

from ..domain.erros import MENSAGENS, RETENTAVEIS, MotivoFalha


@dataclass(frozen=True)
class Classificacao:
    """Resultado de classificar(): motivo + mensagem original + detalhes.

    `detalhes` carrega o que o motivo tiver de específico: lista de países no
    bloqueio regional, status HTTP na falha de rede.
    """
    motivo: MotivoFalha
    mensagem_original: str
    detalhes: dict = field(default_factory=dict)

    @property
    def mensagem(self) -> str:
        raise NotImplementedError("T1")

    @property
    def retentavel(self) -> bool:
        raise NotImplementedError("T1")


class ErroDeDownload(Exception):
    """A única exceção que sai do adapter. Carrega a classificação."""

    def __init__(self, classificacao: Classificacao, original: Exception | None = None):
        self.classificacao = classificacao
        self.original = original
        super().__init__(classificacao.mensagem if False else "")

    @property
    def motivo(self) -> MotivoFalha:
        return self.classificacao.motivo

    @property
    def retentavel(self) -> bool:
        return self.classificacao.retentavel

# Substring (minúscula) -> motivo. Ordem importa: a primeira que casar vence.
# Origem de cada string documentada em RESEARCH 6.3.
TABELA_MENSAGENS: list[tuple[str, MotivoFalha]] = [
    ("drm", MotivoFalha.DRM),
    ("private video", MotivoFalha.PRIVADO),
    ("video unavailable", MotivoFalha.INDISPONIVEL),
    ("age-restricted", MotivoFalha.RESTRICAO_IDADE),
    ("confirm your age", MotivoFalha.RESTRICAO_IDADE),
    ("only available for registered users", MotivoFalha.RESTRICAO_IDADE),
    ("this content isn't available, try again later", MotivoFalha.RATE_LIMIT),
]


def desembrulhar(err: Exception) -> Exception:
    """Extrai a exceção original de dentro do DownloadError."""
    raise NotImplementedError("T1")


def classificar(err: Exception) -> Classificacao:
    """Devolve a Classificacao: motivo, mensagem original e detalhes.

    A mensagem original SEMPRE volta, mesmo quando o motivo é DESCONHECIDO —
    é o que impede o usuário de ficar sem informação quando o site muda o
    texto do erro.
    """
    raise NotImplementedError("T1")


def traduzir(err: Exception) -> ErroDeDownload:
    """classificar() embrulhado na exceção que o adapter levanta."""
    raise NotImplementedError("T1")
