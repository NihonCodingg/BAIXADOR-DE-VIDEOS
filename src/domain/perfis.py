"""Perfis de qualidade: YAML -> configuração validada. Puro.

O yt-dlp aceita um seletor de formato; ele não tem conceito de perfil nomeado
nem valida nada (SPEC 5.2). A tradução "nome legível -> config validada" é o
produto.

Ticket: T2.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from .models import Formato


@dataclass(frozen=True)
class Perfil:
    nome: str
    descricao: str
    format: str                       # template com o placeholder {dim}
    limite_dimensao: int | None       # teto aplicado na MENOR dimensão
    format_sort: tuple[str, ...]
    merge_output_format: str
    postprocessors: tuple[dict, ...]
    exige_ffmpeg: bool


CONTAINERS_VALIDOS = frozenset({"mp4", "mkv", "webm", "m4a", "mp3", "opus"})


def campo_limite(formatos: Sequence[Formato]) -> str | None:
    """Decide se o teto de qualidade vai em `width` ou `height`. SPEC 6.3.

    O teto tem que cair na MENOR dimensão do vídeo. Num vídeo horizontal a
    menor é a altura; num vertical, a largura. Um filtro fixo [height<=1080]
    entrega 480x854 num Short — medido.

    A gramática de filtros do yt-dlp não tem OR, então "height<=1080 ou
    width<=1080" não é expressável. Resolvemos o campo aqui, em tempo de
    execução, a partir da orientação — que já conhecemos da inspeção, antes
    de qualquer download.

    Vídeo QUADRADO (largura == altura) devolve "height": os dois filtros
    selecionariam o mesmo conjunto, e "height" é a convenção de como se
    descreve qualidade de vídeo ("1080p" = 1080 linhas). A regra é: usa
    "width" apenas quando o vídeo é ESTRITAMENTE vertical.

    Devolve None quando nenhum formato tem dimensão (conteúdo só de áudio);
    nesse caso o filtro de dimensão é omitido do seletor.
    """
    com_dimensao = [f for f in formatos if f.largura and f.altura]
    if not com_dimensao:
        return None

    maior = max(com_dimensao, key=lambda f: f.largura * f.altura)
    return "width" if maior.altura > maior.largura else "height"


def resolver_dim(perfil: Perfil, formatos: Sequence[Formato]) -> str:
    """Constrói o trecho que substitui {dim} no template do perfil.

    Devolve "[height<=1080]", "[width<=1080]" ou "" (string vazia).
    """
    if perfil.limite_dimensao is None:
        return ""
    campo = campo_limite(formatos)
    if campo is None:
        return ""
    return f"[{campo}<={perfil.limite_dimensao}]"


def resolver_format(perfil: Perfil, formatos: Sequence[Formato]) -> str:
    """Aplica resolver_dim ao template e devolve o seletor final."""
    return perfil.format.format(dim=resolver_dim(perfil, formatos))


def carregar_perfis(dados: dict, validar_seletor=None) -> dict[str, Perfil]:
    """Valida e converte o dicionário lido do YAML.

    Recebe um dict já carregado — NÃO lê arquivo (o domínio não toca disco).

    TUDO OU NADA: se um perfil for inválido, levanta PerfilInvalido e não
    devolve nada. Um conjunto meio-carregado faria a UI mostrar alguns perfis e
    omitir outros em silêncio.
    """
    raise NotImplementedError("T2")


def validar_perfil(nome: str, bruto: dict, validar_seletor=None) -> Perfil:
    """Valida um perfil isolado. Regras em SPEC 6.2.

    `validar_seletor` é um callable opcional que recebe o seletor e levanta se
    a sintaxe for inválida. Entra INJETADO porque checar sintaxe exige
    `build_format_selector` do yt-dlp, e a REGRA 1 proíbe importá-lo aqui.
    Sem ele, a sintaxe não é checada e o domínio continua puro.
    """
    raise NotImplementedError("T2")


def disponivel(perfil: Perfil, tem_ffmpeg: bool) -> bool:
    """Se o perfil pode ser usado agora.

    Perfil que exige ffmpeg numa máquina sem ffmpeg fica INDISPONÍVEL, e isso
    é estado, não erro: a interface o mostra desabilitado, com o motivo.
    """
    raise NotImplementedError("T2")


def opcoes_ytdlp(perfil: Perfil, formatos: Sequence[Formato],
                 destino: str) -> dict:
    """Monta o dicionário de opções do yt-dlp a partir do perfil.

    Recebe os formatos porque o seletor depende da orientação do vídeo
    (ver campo_limite). Puro: devolve um dict. Quem o usa é o adapter.
    """
    raise NotImplementedError("T2")
