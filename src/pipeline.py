"""Orquestração. Usada pela CLI E pela web — nenhuma das duas duplica regra.

É o único ponto que conhece domain, download, storage e queue ao mesmo tempo.

Tickets: T6 e T8 consomem; montado ao longo de T1-T5.
"""

from pathlib import Path


class Pipeline:
    def __init__(self, config_dir: Path, data_dir: Path):
        raise NotImplementedError

    def inspecionar(self, texto_links: str) -> list[dict]:
        """Normaliza, valida e busca metadados. Não baixa.

        Resultado parcial: cada item traz seu próprio `ok`. Um link ruim numa
        lista de dez não invalida os outros nove (SPEC 11.1).
        """
        raise NotImplementedError

    def enfileirar(self, urls: list[str], perfil: str, projeto: str) -> list[str]:
        raise NotImplementedError

    def estado_fila(self) -> list[dict]:
        raise NotImplementedError

    def cancelar(self, job_id: str) -> bool:
        raise NotImplementedError

    def historico(self, termo=None, projeto=None) -> list[dict]:
        raise NotImplementedError

    def config(self) -> dict:
        """Perfis, projetos e status do ffmpeg. Alimenta GET /api/config."""
        raise NotImplementedError
