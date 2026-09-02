"""Back-end FastAPI. Só JSON, zero regra de negócio.

REGRA DURA 2: este módulo NUNCA importa de src.domain. Fala com src.pipeline,
e tudo que recebe dele já é dict serializável.

Rotas em SPEC 11. Vincula em 127.0.0.1 — sem exposição na rede.

Toda resposta de erro tem UMA forma: {"erro": "mensagem"} — inclusive o 422
de validação e o 500 interno. A tela trata um formato só, e nunca recebe
stack trace (restrição técnica 2).

Ticket: T6.
"""

from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..pipeline import Conflito, EntradaInvalida, NaoEncontrado, Pipeline

RAIZ = Path(__file__).resolve().parent.parent.parent
PASTA_WEB = RAIZ / "web"
HOST = "127.0.0.1"
PORTA = 8000


class CorpoInspecionar(BaseModel):
    links: str                      # um link por linha, como colado no textarea


class CorpoFila(BaseModel):
    urls: list[str]
    perfil: str
    projeto: str
    forcar: bool = False            # rebaixar um vídeo já concluído neste perfil


def _erro(status: int, mensagem: str, **extras) -> JSONResponse:
    return JSONResponse(status_code=status, content={"erro": mensagem, **extras})


def criar_app(pipeline, pasta_web: Path | None = None) -> FastAPI:
    """Monta a aplicação FastAPI sobre um Pipeline já construído.

    `pipeline` entra por injeção: os testes usam um dublê e não sobem worker
    nem tocam a rede. Os handlers são `def` (não `async`): o FastAPI os roda
    num threadpool, e a inspeção — que espera a rede — não trava o servidor.
    """

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI):
        yield
        pipeline.encerrar()         # para o worker e fecha o histórico

    app = FastAPI(title="Baixador de Footage", lifespan=ciclo_de_vida,
                  docs_url=None, redoc_url=None)

    # ----------------------------------------------------------- erros

    @app.exception_handler(EntradaInvalida)
    async def _entrada_invalida(request: Request, exc: EntradaInvalida):
        return _erro(400, str(exc))

    @app.exception_handler(NaoEncontrado)
    async def _nao_encontrado(request: Request, exc: NaoEncontrado):
        return _erro(404, str(exc))

    @app.exception_handler(Conflito)
    async def _conflito(request: Request, exc: Conflito):
        return _erro(409, str(exc))

    @app.exception_handler(RequestValidationError)
    async def _validacao(request: Request, exc: RequestValidationError):
        return _erro(422, "Corpo ou parâmetros inválidos.",
                     detalhes=jsonable_encoder(exc.errors()))

    @app.exception_handler(Exception)
    async def _interno(request: Request, exc: Exception):
        # Mensagem sim, traceback nunca.
        return _erro(500, f"Erro interno: {type(exc).__name__}: {exc}")

    # ----------------------------------------------------------- rotas

    @app.post("/api/inspecionar")
    def inspecionar(corpo: CorpoInspecionar):
        return {"itens": pipeline.inspecionar(corpo.links)}

    @app.post("/api/fila")
    def enfileirar(corpo: CorpoFila):
        ids = pipeline.enfileirar(corpo.urls, corpo.perfil, corpo.projeto, corpo.forcar)
        return {"ids": ids}

    @app.get("/api/fila")
    def fila():
        return {"jobs": pipeline.estado_fila()}

    @app.delete("/api/fila/{job_id}")
    def cancelar(job_id: str):
        pipeline.cancelar(job_id)
        return {"cancelado": True}

    @app.get("/api/historico")
    def historico(termo: str | None = None, projeto: str | None = None,
                  limite: int = Query(100, ge=1, le=1000)):
        return {"registros": pipeline.historico(termo, projeto, limite)}

    @app.get("/api/config")
    def config():
        return pipeline.config()

    # Estáticos por último: o mount em "/" pega tudo que as rotas não pegaram.
    app.mount("/", StaticFiles(directory=str(pasta_web or PASTA_WEB), html=True),
              name="web")
    return app


def main() -> None:
    """Sobe o Pipeline real e o uvicorn em 127.0.0.1."""
    pipeline = Pipeline(RAIZ / "config", RAIZ / "data")
    try:
        uvicorn.run(criar_app(pipeline), host=HOST, port=PORTA, log_level="warning")
    finally:
        pipeline.encerrar()
