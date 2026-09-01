"""Back-end FastAPI. Só JSON, zero regra de negócio.

REGRA DURA 2: este módulo NUNCA importa de src.domain. Fala com src.pipeline.

Rotas em SPEC 11. Vincula em 127.0.0.1 — sem exposição na rede.

Ticket: T6.
"""


def criar_app():
    """Monta a aplicação FastAPI."""
    raise NotImplementedError("T6")


def main() -> None:
    """uvicorn em 127.0.0.1."""
    raise NotImplementedError("T6")
