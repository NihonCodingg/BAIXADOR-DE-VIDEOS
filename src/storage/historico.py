"""Histórico persistente em SQLite. SPEC 9 e 10.1.

Ticket: T4.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..domain.models import Video


class RegistroNaoEncontrado(Exception):
    """concluir/falhar sobre uma chave que nunca foi iniciada."""


@dataclass(frozen=True)
class RegistroHistorico:
    """Uma linha da tabela, espelhando o schema.sql."""
    id: int
    extractor: str
    video_id: str
    perfil: str
    url_original: str
    url_canonica: str
    titulo: str
    canal: str | None
    duracao_s: int | None
    projeto: str
    caminho: str | None
    tamanho_bytes: int | None
    resolucao: str | None
    status: str
    motivo_falha: str | None
    mensagem_falha: str | None
    criado_em: str
    concluido_em: str | None


def normalizar_busca(texto: str) -> str:
    """Minúsculas, sem acento, espaços colapsados. Aplicado ao gravar e ao
    buscar, para 'selecao', 'SELEÇÃO' e 'Seleção' serem a mesma coisa."""
    raise NotImplementedError("T4")


class Historico:
    """Uma conexão, um lock. O worker grava enquanto a web lê."""

    def __init__(self, caminho_db: Path | str, agora: Callable[[], str] | None = None):
        raise NotImplementedError("T4")

    def criar_schema(self) -> None:
        """Executa schema.sql. Idempotente."""
        raise NotImplementedError("T4")

    def fechar(self) -> None:
        raise NotImplementedError("T4")

    def iniciar(self, video: Video, *, perfil: str, projeto: str,
                url_original: str) -> RegistroHistorico:
        """Grava a linha `baixando`. Upsert: nova tentativa da mesma chave
        substitui a anterior."""
        raise NotImplementedError("T4")

    def concluir(self, extractor: str, video_id: str, perfil: str, *,
                 caminho: str, tamanho_bytes: int | None,
                 resolucao: str | None = None) -> RegistroHistorico:
        raise NotImplementedError("T4")

    def falhar(self, extractor: str, video_id: str, perfil: str, *,
               motivo: str, mensagem: str) -> RegistroHistorico:
        raise NotImplementedError("T4")

    def obter(self, extractor: str, video_id: str, perfil: str) -> RegistroHistorico | None:
        """A linha da chave, em qualquer status."""
        raise NotImplementedError("T4")

    def ja_baixado(self, extractor: str, video_id: str,
                   perfil: str) -> RegistroHistorico | None:
        """A linha da chave SE estiver concluída. Alimenta o aviso de duplicata."""
        raise NotImplementedError("T4")

    def buscar(self, termo: str | None = None, projeto: str | None = None,
               limite: int = 100) -> list[RegistroHistorico]:
        raise NotImplementedError("T4")

    def marcar_interrompidos(self) -> int:
        """Na subida: todo registro `baixando` vira `interrompido`.

        É o que impede um job morto no meio de ser lido como concluído
        (SPEC 10.1). Devolve quantos foram marcados.
        """
        raise NotImplementedError("T4")
