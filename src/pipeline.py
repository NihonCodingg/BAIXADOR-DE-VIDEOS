"""Orquestração. Usada pela CLI E pela web — nenhuma das duas duplica regra.

É o único ponto que conhece domain, download, storage e queue ao mesmo tempo.
Tudo que sai daqui é dict serializável em JSON: a camada web nunca vê Job,
Video ou Perfil (REGRA 2).

Ticket: T6.
"""

from collections.abc import Callable
from pathlib import Path


class ErroDePedido(Exception):
    """Base dos erros que a API traduz em código HTTP."""


class EntradaInvalida(ErroDePedido):
    """Link, perfil ou projeto inválido. A API responde 400."""


class NaoEncontrado(ErroDePedido):
    """Job inexistente. A API responde 404."""


class Conflito(ErroDePedido):
    """Já baixado, já na fila, ou cancelamento de job em andamento. 409."""


class Pipeline:
    def __init__(self, config_dir: Path, data_dir: Path, *,
                 downloader=None, detectar_ffmpeg: Callable | None = None):
        """Carrega perfis e projetos, detecta o ffmpeg, abre o histórico e
        reconcilia os interrompidos (SPEC 10.1), sobe o worker."""
        raise NotImplementedError("T6")

    def inspecionar(self, texto_links: str) -> list[dict]:
        """Normaliza, valida e busca metadados. Não baixa.

        Resultado parcial: cada item traz seu próprio `ok`. Um link ruim numa
        lista de dez não invalida os outros nove (SPEC 11.1).
        """
        raise NotImplementedError("T6")

    def enfileirar(self, urls: list[str], perfil: str, projeto: str,
                   forcar: bool = False) -> list[str]:
        """Devolve os ids dos jobs. EntradaInvalida / Conflito."""
        raise NotImplementedError("T6")

    def estado_fila(self) -> list[dict]:
        raise NotImplementedError("T6")

    def cancelar(self, job_id: str) -> bool:
        """NaoEncontrado se não existe; Conflito se já começou."""
        raise NotImplementedError("T6")

    def historico(self, termo: str | None = None, projeto: str | None = None,
                  limite: int = 100) -> list[dict]:
        raise NotImplementedError("T6")

    def config(self) -> dict:
        """Perfis, projetos e status do ffmpeg. Alimenta GET /api/config."""
        raise NotImplementedError("T6")

    def encerrar(self) -> None:
        """Para o worker e fecha o histórico. Idempotente."""
        raise NotImplementedError("T6")
