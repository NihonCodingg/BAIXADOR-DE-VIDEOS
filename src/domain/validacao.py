"""Validação e normalização de link. Puro.

Três responsabilidades que o yt-dlp não cobre (SPEC 5.3):
  1. rejeitar URL de canal/playlist — download em massa está fora de escopo
  2. normalizar para forma canônica, para o histórico não duplicar
  3. deduplicar a lista colada pelo usuário

Ticket: T2.
"""


def normalizar_link(url: str) -> str:
    """Reduz a URL à forma canônica do vídeo.

    youtu.be/X, youtube.com/watch?v=X e a versão com &t=42 devem produzir
    o mesmo resultado.

    Levanta LinkInvalido.
    """
    raise NotImplementedError("T2")


def e_playlist_ou_canal(url: str) -> bool:
    """True se a URL aponta para canal, playlist ou aba de canal."""
    raise NotImplementedError("T2")


def extrair_id(url: str) -> str:
    """Extrai o identificador do vídeo da URL canônica."""
    raise NotImplementedError("T2")


def normalizar_lote(texto: str) -> list[str]:
    """Recebe o conteúdo do textarea (um link por linha).

    Ignora linhas vazias, normaliza cada uma, remove duplicatas preservando a
    ordem de aparição.
    """
    raise NotImplementedError("T2")
