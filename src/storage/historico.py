"""Histórico persistente em SQLite. SPEC 9.

Ticket: T4.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RegistroHistorico:
    video_id: str
    perfil: str
    extractor: str
    url_canonica: str
    titulo: str
    projeto: str
    caminho: str | None
    tamanho_bytes: int | None
    status: str
    criado_em: str
    concluido_em: str | None


class Historico:
    def __init__(self, caminho_db: Path):
        raise NotImplementedError("T4")

    def criar_schema(self) -> None:
        """Executa schema.sql. Idempotente."""
        raise NotImplementedError("T4")

    def ja_baixado(self, extractor: str, video_id: str,
                   perfil: str) -> RegistroHistorico | None:
        """Consulta a chave única. É o que alimenta o aviso de duplicata."""
        raise NotImplementedError("T4")

    def registrar(self, registro: RegistroHistorico) -> None:
        raise NotImplementedError("T4")

    def buscar(self, termo: str | None = None, projeto: str | None = None,
               limite: int = 100) -> list[RegistroHistorico]:
        raise NotImplementedError("T4")

    def marcar_interrompidos(self) -> int:
        """Na subida: todo registro não-terminal vira `interrompido`.

        É o que impede um job morto no meio de ser lido como concluído
        (SPEC 10.1). Devolve quantos foram marcados.
        """
        raise NotImplementedError("T4")
