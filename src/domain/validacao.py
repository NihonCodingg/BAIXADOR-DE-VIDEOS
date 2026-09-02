"""Validação e normalização de link. Puro.

Três responsabilidades que o yt-dlp não cobre (SPEC 5.3):
  1. rejeitar URL de canal/playlist — download em massa está fora de escopo
  2. normalizar para forma canônica, para o histórico não duplicar
  3. deduplicar a lista colada pelo usuário

Escopo: conhece APENAS o YouTube. URL de outro site suportado pelo yt-dlp passa
adiante sem normalizar, com aviso. Só texto que não é URL vira LinkInvalido.
A limitação que isso cria está registrada no SPEC 5.3.

Ticket: T2.
"""

from dataclasses import dataclass

# Identificador de vídeo do YouTube: 11 caracteres do alfabeto base64url.
# Confirmado no _VALID_URL do extractor: (?P<id>[0-9A-Za-z_-]{11})
TAMANHO_ID_YOUTUBE = 11


@dataclass(frozen=True)
class LinkNormalizado:
    """Resultado da normalização de UMA linha colada.

    O aviso viaja DENTRO do resultado, e não por print ou log, para que o T7
    consiga exibi-lo no cartão de preview. Mesma forma do CaminhoMontado (T3).

    `url` é None quando a linha é inválida; nesse caso `erro` explica.
    """
    original: str
    url: str | None
    video_id: str | None
    e_youtube: bool
    aviso: str | None = None
    erro: str | None = None

    @property
    def ok(self) -> bool:
        return self.url is not None


def extrair_id(url: str) -> str | None:
    """Extrai o id de 11 caracteres de uma URL de vídeo do YouTube.

    Devolve None se a URL não for de vídeo do YouTube.
    """
    raise NotImplementedError("T2")


def e_playlist_ou_canal(url: str) -> bool:
    """True se a URL aponta para canal, playlist ou aba de canal.

    Download em massa está fora de escopo (SPEC 2.2), e extract_info percorre
    a lista inteira — a recusa tem que ser ANTES da chamada de rede.
    """
    raise NotImplementedError("T2")


def normalizar_link(url: str) -> LinkNormalizado:
    """Normaliza UMA URL. Levanta LinkInvalido.

    YouTube  -> canônico https://www.youtube.com/watch?v=ID
    Outro site suportado -> devolve a URL intacta, com aviso
    Não é URL, ou é canal/playlist -> LinkInvalido
    """
    raise NotImplementedError("T2")


def normalizar_lote(texto: str) -> tuple[LinkNormalizado, ...]:
    """Recebe o conteúdo do textarea, um link por linha.

    NUNCA levanta: cada linha inválida vira um LinkNormalizado com `erro`
    preenchido. Resultado parcial é requisito (SPEC 11.1) — um link ruim numa
    lista de dez não pode invalidar os outros nove.

    Ignora linhas vazias, apara espaços, e deduplica preservando a ordem de
    aparição.
    """
    raise NotImplementedError("T2")
