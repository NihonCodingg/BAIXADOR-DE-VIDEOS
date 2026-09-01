"""Perfis de qualidade: YAML -> configuração validada. Puro.

O yt-dlp aceita um seletor de formato; ele não tem conceito de perfil nomeado
nem valida nada (SPEC 5.2). A tradução "nome legível -> config validada" é o
produto.

Ticket: T2.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Perfil:
    nome: str
    descricao: str
    format: str
    format_sort: tuple[str, ...]
    merge_output_format: str
    postprocessors: tuple[dict, ...]
    exige_ffmpeg: bool


CONTAINERS_VALIDOS = frozenset({"mp4", "mkv", "webm", "m4a", "mp3", "opus"})


def carregar_perfis(dados: dict) -> dict[str, Perfil]:
    """Valida e converte o dicionário lido do YAML.

    Recebe um dict já carregado — NÃO lê arquivo (o domínio não toca disco).
    Levanta PerfilInvalido.
    """
    raise NotImplementedError("T2")


def validar_perfil(nome: str, bruto: dict) -> Perfil:
    """Valida um perfil isolado. Regras em SPEC 6.2.

    Em particular: `format` não pode conter vírgula — múltiplos formatos
    geram vários arquivos e quebram a premissa de um arquivo por job.
    """
    raise NotImplementedError("T2")


def opcoes_ytdlp(perfil: Perfil, destino: str) -> dict:
    """Monta o dicionário de opções do yt-dlp a partir do perfil.

    Puro: devolve um dict. Quem o usa é o adapter.
    """
    raise NotImplementedError("T2")
