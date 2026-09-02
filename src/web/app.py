"""Back-end FastAPI. Só JSON, zero regra de negócio.

REGRA DURA 2: este módulo NUNCA importa de src.domain. Fala com src.pipeline,
e tudo que recebe dele já é dict serializável.

Rotas em SPEC 11. Vincula em 127.0.0.1 — sem exposição na rede.

Ticket: T6.
"""

from pathlib import Path

PASTA_WEB = Path(__file__).resolve().parent.parent.parent / "web"
HOST = "127.0.0.1"
PORTA = 8000


def criar_app(pipeline, pasta_web: Path | None = None):
    """Monta a aplicação FastAPI sobre um Pipeline já construído.

    `pipeline` entra por injeção: os testes usam um dublê e não sobem worker
    nem tocam a rede.
    """
    raise NotImplementedError("T6")


def main() -> None:
    """Sobe o Pipeline real e o uvicorn em 127.0.0.1."""
    raise NotImplementedError("T6")
