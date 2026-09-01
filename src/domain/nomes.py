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

from dataclasses import dataclass

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

# Mapeamento POR CARACTERE, não regra única (SPEC 8.2).
# Cada proibido carrega um significado diferente no título; achatar todos em
# "-" destrói informação:
#   "Highlights 2024/2025"  -> "Highlights 2024-2025"   (intervalo, colado)
#   "Gameplay | Rush B"     -> "Gameplay - Rush B"      (separador)
#   "Seleção: críticas"     -> "Seleção críticas"       (espaço, depois colapsa)
#   "Round1:Final"          -> "Round1 Final"           (sem colar palavras)
MAPA_PROIBIDOS = {
    "|": " - ",
    "/": "-",
    "\\": "-",
    ":": " ",
    "?": "",
    "*": "",
    '"': "",
    "<": "",
    ">": "",
}

# Teto do CAMINHO COMPLETO, não do nome (SPEC 8.3).
# 260 (MAX_PATH) menos 20 de folga para os temporários do yt-dlp, que são mais
# longos que o nome final: NOME.f616-drc.mp4.part custa +14 sobre NOME.mp4.
ORCAMENTO_CAMINHO = 240

# Abaixo disto sobrando para o título: AVISO, não erro. O download prossegue
# truncado; o usuário precisa é enxergar que a pasta está profunda demais.
MINIMO_TITULO_SEM_AVISO = 40

# Reserva para o sufixo de colisão " (2)" a " (99)", que entra DEPOIS do
# truncamento (SPEC 8.3). Sem ela, um título que couber exatamente no orçamento
# estoura o teto na primeira colisão.
RESERVA_COLISAO = 5

# Título usado quando o original não tem nenhum alfanumérico: vazio, só
# espaços, só pontuação ou só emoji (SPEC 8.2, regra 7).
# É "video" e não "video_{id}" porque o [{id}] do template já dá unicidade.
TITULO_FALLBACK = "video"


@dataclass(frozen=True)
class CaminhoMontado:
    """Resultado de montar_caminho.

    `aviso` é preenchido quando a pasta do projeto é profunda o bastante para
    espremer o título abaixo de MINIMO_TITULO_SEM_AVISO. Não é erro: o download
    prossegue truncado (SPEC 8.3).
    """
    caminho: str
    aviso: str | None = None


def sanitizar(titulo: str) -> str:
    """Regras 1 a 4 de SPEC 8.2: controle, mapeamento, colapso, strip do fim.

    NÃO aplica o fallback video_{id} (não conhece o id) e NÃO trunca (não
    conhece o destino). Pode devolver string vazia.
    """
    raise NotImplementedError("T3")


def tem_alfanumerico(texto: str) -> bool:
    """True se há ao menos um caractere de categoria Unicode L* ou N*.

    É o critério do fallback (SPEC 8.2, regra 7): um nome sem nenhuma letra ou
    dígito é impossível de digitar numa busca.
    """
    raise NotImplementedError("T3")


def e_reservado(nome_base: str) -> bool:
    """True se o nome-base é reservado no Windows.

    Comparação por IGUALDADE case-insensitive, nunca por prefixo: CONSOLE,
    CONTRA, NULO, COM10 e LPT0 não são reservados.
    """
    raise NotImplementedError("T3")


def aplicar_reservado(nome_base: str) -> str:
    """Sufixa `_` se o nome-base for reservado. Caso contrário, devolve igual."""
    raise NotImplementedError("T3")


def truncar_titulo(titulo: str, limite: int) -> str:
    """Corta o título para caber em `limite` caracteres.

    Só o título é cortado — data, id e extensão são invioláveis.
    """
    raise NotImplementedError("T3")


def montar_nome(titulo: str, video_id: str, data_upload: str | None,
                extensao: str) -> str:
    """Monta `{data} - {titulo} [{id}].{ext}`. SPEC 8.1.

    Sem data_upload, o template vira `{titulo} [{id}].{ext}`.
    Aplica o fallback video_{id} e o tratamento de nome reservado.
    NÃO trunca — quem trunca é montar_caminho, que conhece a pasta.
    """
    raise NotImplementedError("T3")


def montar_caminho(pasta_projeto: str, titulo: str, video_id: str,
                   data_upload: str | None, extensao: str) -> CaminhoMontado:
    """Caminho completo respeitando o orçamento de SPEC 8.3.

    Reserva o custo fixo primeiro; o que sobra é o orçamento do título.
    Levanta NomeImpossivel se nem o custo fixo couber.

    Puro: só monta a string. NÃO cria diretório nem toca o disco.
    """
    raise NotImplementedError("T3")


def resolver_colisao(caminho: str, existe) -> str:
    """Sufixo ` (2)`, ` (3)`... antes da extensão. SPEC 8.4.

    `existe` é um callable que recebe um caminho e devolve bool. A checagem de
    disco é injetada para o domínio permanecer puro e testável.

    A insensibilidade a maiúsculas vem de `existe`, não daqui: no Windows o
    próprio os.path.exists já é case-insensitive. Esta função NÃO pode manter
    seu próprio conjunto de caminhos comparado com sensibilidade a caixa —
    seria sobrescrita silenciosa de footage.
    """
    raise NotImplementedError("T3")
