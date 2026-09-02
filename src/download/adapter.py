"""Adapter do yt-dlp. Único módulo do projeto que faz `import yt_dlp`.

Ticket: T1.
"""

from collections.abc import Callable


class Downloader:
    """Fachada sobre o yt-dlp.

    A interface é deliberadamente pequena para que a fila (T5) possa ser
    testada com um dublê que implemente estes dois métodos, sem rede.

    `fabrica_ydl` é a classe YoutubeDL (ou um dublê nos testes). Injeção em
    vez de import direto no método, para o adapter ser testável sem rede.
    """

    def __init__(self, fabrica_ydl=None):
        raise NotImplementedError("T1")

    def inspecionar(self, url: str) -> dict:
        """extract_info(download=False) + sanitize_info.

        Devolve o info_dict serializável. Não baixa mídia.
        Levanta ErroDeDownload já classificado.
        """
        raise NotImplementedError("T1")

    def baixar(self, url: str, opcoes: dict,
               ao_progredir: Callable[[dict], None]) -> str:
        """Baixa e devolve o caminho final do arquivo.

        `ao_progredir` é registrado como progress_hook. ATENÇÃO: pode ser
        chamado de outra thread (RESEARCH 3.4). Quem passa o callback é
        responsável por torná-lo thread-safe.
        """
        raise NotImplementedError("T1")
