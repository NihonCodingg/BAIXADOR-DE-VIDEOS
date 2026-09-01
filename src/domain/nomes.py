"""Nomenclatura e sanitização de arquivo para Windows. Puro.

Esta é a justificativa mais forte da camada de domínio (SPEC 5.1).

O sanitize_filename do yt-dlp NÃO trata: nomes reservados do DOS, tamanho,
nome vazio, ponto/espaço final, comprimento do diretório de destino, nem
colisão. E o que ele faz — substituir proibidos por homóglifos Unicode de
largura total — é indesejado aqui: o nome deixa de ser digitável e buscável.

Medição decisiva (RESEARCH 7.3): gravar num arquivo chamado NUL não levanta
erro e os bytes desaparecem. Sanitização aqui é correção, não estilo.

Ticket: T3.
"""

# SPEC 8.2, regra 5. Microsoft: "avoid these names followed immediately by an
# extension; NUL.txt and NUL.tar.gz are both equivalent to NUL".
NOMES_RESERVADOS = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
    # Windows trata os superscripts ISO-8859-1 como dígito.
    "COM\u00b9", "COM\u00b2", "COM\u00b3",
    "LPT\u00b9", "LPT\u00b2", "LPT\u00b3",
})

# raw string: precisa conter a barra invertida literal
CARACTERES_PROIBIDOS = r'<>:"/\|?*'

ORCAMENTO_CAMINHO = 200          # SPEC 8.3
SUBSTITUTO = "-"


def sanitizar(titulo: str) -> str:
    """Aplica as regras 1 a 5 e 7 de SPEC 8.2, sem truncar.

    Truncamento é separado porque depende do diretório de destino.
    """
    raise NotImplementedError("T3")


def e_reservado(nome: str) -> bool:
    """True se o nome, sem extensão e case-insensitive, é reservado no Windows."""
    raise NotImplementedError("T3")


def truncar(nome: str, extensao: str, espaco_disponivel: int) -> str:
    """Trunca preservando a extensão. SPEC 8.3."""
    raise NotImplementedError("T3")


def montar_nome(titulo: str, video_id: str, data_upload: str | None,
                extensao: str) -> str:
    """Monta `{data} - {titulo} [{id}].{ext}`. SPEC 8.1."""
    raise NotImplementedError("T3")


def montar_caminho(pasta_projeto: str, titulo: str, video_id: str,
                   data_upload: str | None, extensao: str) -> str:
    """Caminho completo, respeitando o orçamento de SPEC 8.3.

    Puro: só monta a string. NÃO cria diretório nem toca o disco.
    """
    raise NotImplementedError("T3")


def resolver_colisao(caminho: str, existe) -> str:
    """Sufixo ` (2)`, ` (3)`... antes da extensão. SPEC 8.4.

    `existe` é um callable que recebe um caminho e devolve bool. A checagem de
    disco é injetada para o domínio permanecer puro e testável.
    """
    raise NotImplementedError("T3")
