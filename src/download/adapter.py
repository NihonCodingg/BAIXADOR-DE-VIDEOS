"""Adapter do yt-dlp. Único módulo do projeto que faz `import yt_dlp`.

O que ele faz: monta as opções, registra o hook, aplica sanitize_info, extrai
o caminho final e traduz erros. O que ele NÃO faz: regra de negócio. Perfil,
nome de arquivo e destino chegam prontos do domínio.

Ticket: T1.
"""

from collections.abc import Callable

import yt_dlp

from ..domain.erros import MotivoFalha
from .traducao_erros import Classificacao, ErroDeDownload, traduzir


def _caminho_final(info: dict) -> str | None:
    """Onde o yt-dlp deixou o arquivo.

    Depois do merge, `requested_downloads[0]['filepath']` é o caminho final
    (verificado no spike). Sem merge, alguns caminhos deixam só `filepath`.
    """
    pedidos = info.get("requested_downloads") or []
    if pedidos and isinstance(pedidos[0], dict) and pedidos[0].get("filepath"):
        return pedidos[0]["filepath"]
    return info.get("filepath") or None


class Downloader:
    """Fachada sobre o yt-dlp.

    A interface é deliberadamente pequena para que a fila (T5) possa ser
    testada com um dublê que implemente estes dois métodos, sem rede.

    `fabrica_ydl` é a classe YoutubeDL (ou um dublê nos testes). Injeção em
    vez de import direto no método, para o adapter ser testável sem rede.
    """

    def __init__(self, fabrica_ydl=None):
        self._fabrica = fabrica_ydl or yt_dlp.YoutubeDL

    def inspecionar(self, url: str) -> dict:
        """extract_info(download=False) + sanitize_info.

        Devolve o info_dict serializável. Não baixa mídia.
        Levanta ErroDeDownload já classificado.
        """
        opcoes = {
            "quiet": True,
            "no_warnings": True,
            # Segunda defesa contra arrastar um canal inteiro. A primeira é a
            # validação de link no domínio (SPEC 5.3).
            "noplaylist": True,
            "skip_download": True,
            # ignoreerrors fica no padrão da API (False): os erros SOBEM, que é
            # o que queremos capturar (RESEARCH 1.4). Não mexer.
        }
        try:
            # `with` fecha o cache de conexões ao sair. Sem ele, sockets ficam
            # abertos num worker de longa duração (RESEARCH 1.1).
            with self._fabrica(opcoes) as ydl:
                bruto = ydl.extract_info(url, download=False)
                # Sem sanitize_info o resultado não é serializável em JSON
                # (RESEARCH 1.3), e a API devolve JSON.
                return ydl.sanitize_info(bruto)
        except ErroDeDownload:
            raise
        except Exception as erro:          # nunca BaseException: Ctrl+C sobe
            raise traduzir(erro) from erro

    def baixar(self, url: str, opcoes: dict,
               ao_progredir: Callable[[dict], None]) -> str:
        """Baixa e devolve o caminho final do arquivo.

        `ao_progredir` é registrado como progress_hook. ATENÇÃO: pode ser
        chamado de outra thread (RESEARCH 3.4). Quem passa o callback é
        responsável por torná-lo thread-safe.

        `opcoes` é o dict montado por opcoes_ytdlp no domínio. Não é mutado.
        """
        efetivas = dict(opcoes)
        efetivas["progress_hooks"] = [ao_progredir]
        efetivas.setdefault("quiet", True)
        efetivas.setdefault("no_warnings", True)
        efetivas.setdefault("noplaylist", True)

        # Footage nunca é sobrescrito (SPEC 8.4). O domínio resolve colisão
        # antes, mas entre a checagem e a gravação um arquivo pode aparecer;
        # com overwrites=False o yt-dlp recusa em vez de destruir.
        # DECISAO-PENDENTE: se o arquivo já existir no destino, o yt-dlp dispara
        # 'finished' sem baixar (RESEARCH 3.2) e o job parece bem-sucedido —
        # tratar como sucesso, ou como falha com aviso?
        efetivas["overwrites"] = False

        # DECISAO-PENDENTE: continuedl fica no padrão (retoma .part parcial).
        # Reiniciar do zero custa banda; retomar tem risco teórico de misturar
        # bytes se o site reencodar o stream entre tentativas. Mantido o
        # padrão do yt-dlp, que é o comportamento testado em campo.

        # O outtmpl chega como caminho LITERAL, já sanitizado pelo domínio. O
        # yt-dlp o trata como template: um "%(" no título viraria "NA"
        # (medido). Escapar "%" como "%%" faz o yt-dlp devolver "%" literal.
        if isinstance(efetivas.get("outtmpl"), str):
            efetivas["outtmpl"] = efetivas["outtmpl"].replace("%", "%%")

        try:
            with self._fabrica(efetivas) as ydl:
                info = ydl.extract_info(url, download=True)
        except ErroDeDownload:
            raise
        except Exception as erro:
            raise traduzir(erro) from erro

        caminho = _caminho_final(info or {})
        if not caminho:
            # Download "concluído" sem caminho seria histórico apontando para
            # o nada. Falha explícita é melhor que sucesso falso.
            raise ErroDeDownload(Classificacao(
                MotivoFalha.DESCONHECIDO,
                "o yt-dlp concluiu sem informar o caminho do arquivo baixado",
            ))
        return str(caminho)


def validar_seletor(seletor: str) -> None:
    """Levanta se a sintaxe do seletor de formato for inválida. Offline.

    É o `validar_seletor` injetado em carregar_perfis(): o domínio não pode
    importar yt_dlp (REGRA 1), então a checagem mora aqui.

    build_format_selector só analisa a string — não toca a rede.
    """
    ydl = yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True})
    try:
        ydl.build_format_selector(seletor)
    finally:
        ydl.close()
