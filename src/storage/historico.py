"""Histórico persistente em SQLite. SPEC 9 e 10.1.

Uma conexão, um lock. O worker (T5) grava enquanto a web (T6) lê; uma
conexão SQLite não pode ser compartilhada entre threads sem serialização,
então cada operação pública adquire o lock.

Ticket: T4.
"""

import re
import sqlite3
import threading
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from pathlib import Path

from ..domain.models import Video

SCHEMA = Path(__file__).with_name("schema.sql")


class RegistroNaoEncontrado(Exception):
    """concluir/falhar sobre uma chave que nunca foi iniciada."""


@dataclass(frozen=True)
class RegistroHistorico:
    """Uma linha da tabela, espelhando o schema.sql."""
    id: int
    extractor: str
    video_id: str
    perfil: str
    url_original: str
    url_canonica: str
    titulo: str
    canal: str | None
    duracao_s: int | None
    projeto: str
    caminho: str | None
    tamanho_bytes: int | None
    resolucao: str | None
    status: str
    motivo_falha: str | None
    mensagem_falha: str | None
    criado_em: str
    concluido_em: str | None


_COLUNAS = [f.name for f in fields(RegistroHistorico)]


def _agora_utc() -> str:
    """ISO-8601 em UTC. TEXT que ordena corretamente como texto (SPEC 9.1)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalizar_busca(texto: str) -> str:
    """Minúsculas, sem acento, espaços colapsados.

    Aplicado ao gravar (coluna titulo_busca) e ao buscar, para 'selecao',
    'SELEÇÃO' e 'Seleção' serem a mesma coisa. O LIKE do SQLite só ignora caixa
    em ASCII: 'Ç' não casa com 'ç'.
    """
    if not texto:
        return ""
    decomposto = unicodedata.normalize("NFD", texto)
    sem_acento = "".join(c for c in decomposto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", sem_acento).strip().casefold()


def _escapar_like(texto: str) -> str:
    """'%' e '_' são curingas do LIKE. Um termo com eles não pode virar 'tudo'."""
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class Historico:
    """Uma conexão, um lock. O worker grava enquanto a web lê."""

    def __init__(self, caminho_db: Path | str, agora: Callable[[], str] | None = None):
        self._caminho = Path(caminho_db)
        self._agora = agora or _agora_utc
        self._lock = threading.RLock()
        self._fechado = False

        # data/ pode não existir na primeira execução.
        self._caminho.parent.mkdir(parents=True, exist_ok=True)

        # check_same_thread=False porque a conexão é usada pelo worker e pela
        # web; a serialização é o lock desta classe, não o do sqlite3.
        self._con = sqlite3.connect(str(self._caminho), check_same_thread=False)
        self._con.row_factory = sqlite3.Row

    # ------------------------------------------------------------------ infra

    def _exigir_aberto(self) -> None:
        if self._fechado:
            raise RuntimeError("Histórico já fechado; abra uma nova instância.")

    def _executar(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            self._exigir_aberto()
            cursor = self._con.execute(sql, params)
            self._con.commit()
            return cursor

    def _linha(self, row: sqlite3.Row | None) -> RegistroHistorico | None:
        if row is None:
            return None
        return RegistroHistorico(**{coluna: row[coluna] for coluna in _COLUNAS})

    def criar_schema(self) -> None:
        """Executa schema.sql. Idempotente (CREATE ... IF NOT EXISTS)."""
        with self._lock:
            self._exigir_aberto()
            self._con.executescript(SCHEMA.read_text(encoding="utf-8"))
            self._con.commit()

    def fechar(self) -> None:
        with self._lock:
            if not self._fechado:
                self._con.close()
                self._fechado = True

    # --------------------------------------------------------------- escrita

    def iniciar(self, video: Video, *, perfil: str, projeto: str,
                url_original: str) -> RegistroHistorico:
        """Grava a linha `baixando`.

        Upsert: nova tentativa da mesma chave substitui a anterior e começa
        limpa — sem caminho, sem motivo de falha. Uma linha por chave
        representando a ÚLTIMA tentativa (SPEC 9.2).
        """
        with self._lock:
            self._executar(
                """
                INSERT INTO historico (
                    extractor, video_id, perfil, url_original, url_canonica,
                    titulo, titulo_busca, canal, duracao_s, projeto,
                    caminho, tamanho_bytes, resolucao, status,
                    motivo_falha, mensagem_falha, criado_em, concluido_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          NULL, NULL, NULL, 'baixando', NULL, NULL, ?, NULL)
                ON CONFLICT (extractor, video_id, perfil) DO UPDATE SET
                    url_original   = excluded.url_original,
                    url_canonica   = excluded.url_canonica,
                    titulo         = excluded.titulo,
                    titulo_busca   = excluded.titulo_busca,
                    canal          = excluded.canal,
                    duracao_s      = excluded.duracao_s,
                    projeto        = excluded.projeto,
                    caminho        = NULL,
                    tamanho_bytes  = NULL,
                    resolucao      = NULL,
                    status         = 'baixando',
                    motivo_falha   = NULL,
                    mensagem_falha = NULL,
                    criado_em      = excluded.criado_em,
                    concluido_em   = NULL
                """,
                (video.extractor, video.video_id, perfil, url_original,
                 video.url_canonica, video.titulo, normalizar_busca(video.titulo),
                 video.canal, video.duracao_s, projeto, self._agora()),
            )
            return self.obter(video.extractor, video.video_id, perfil)

    def concluir(self, extractor: str, video_id: str, perfil: str, *,
                 caminho: str, tamanho_bytes: int | None,
                 resolucao: str | None = None) -> RegistroHistorico:
        with self._lock:
            cursor = self._executar(
                """
                UPDATE historico
                   SET status = 'concluido', caminho = ?, tamanho_bytes = ?,
                       resolucao = ?, concluido_em = ?
                 WHERE extractor = ? AND video_id = ? AND perfil = ?
                """,
                (caminho, tamanho_bytes, resolucao, self._agora(),
                 extractor, video_id, perfil),
            )
            if cursor.rowcount == 0:
                raise RegistroNaoEncontrado(f"{extractor}/{video_id}/{perfil}")
            return self.obter(extractor, video_id, perfil)

    def falhar(self, extractor: str, video_id: str, perfil: str, *,
               motivo: str, mensagem: str) -> RegistroHistorico:
        """Caminho volta a NULL: um caminho preenchido com status diferente de
        concluido é inconsistência (SPEC 9.1)."""
        with self._lock:
            cursor = self._executar(
                """
                UPDATE historico
                   SET status = 'falhou', caminho = NULL, tamanho_bytes = NULL,
                       resolucao = NULL, motivo_falha = ?, mensagem_falha = ?,
                       concluido_em = ?
                 WHERE extractor = ? AND video_id = ? AND perfil = ?
                """,
                (motivo, mensagem, self._agora(), extractor, video_id, perfil),
            )
            if cursor.rowcount == 0:
                raise RegistroNaoEncontrado(f"{extractor}/{video_id}/{perfil}")
            return self.obter(extractor, video_id, perfil)

    def marcar_interrompidos(self) -> int:
        """Na subida: todo registro `baixando` vira `interrompido`.

        É o que impede um job morto no meio de ser lido como concluído
        (SPEC 10.1). Devolve quantos foram marcados.
        """
        cursor = self._executar(
            """
            UPDATE historico
               SET status = 'interrompido', concluido_em = ?
             WHERE status = 'baixando'
            """,
            (self._agora(),),
        )
        return cursor.rowcount

    # --------------------------------------------------------------- leitura

    def obter(self, extractor: str, video_id: str, perfil: str) -> RegistroHistorico | None:
        """A linha da chave, em qualquer status."""
        cursor = self._executar(
            "SELECT * FROM historico WHERE extractor = ? AND video_id = ? AND perfil = ?",
            (extractor, video_id, perfil),
        )
        return self._linha(cursor.fetchone())

    def ja_baixado(self, extractor: str, video_id: str,
                   perfil: str) -> RegistroHistorico | None:
        """A linha da chave SE estiver concluída. Alimenta o aviso de duplicata.

        `baixando`, `falhou` e `interrompido` devolvem None: não há arquivo
        pronto para apontar.
        """
        registro = self.obter(extractor, video_id, perfil)
        if registro is not None and registro.status == "concluido":
            return registro
        return None

    def buscar(self, termo: str | None = None, projeto: str | None = None,
               limite: int = 100) -> list[RegistroHistorico]:
        """Mais recente primeiro. Termo casa por substring no título
        normalizado; projeto casa por igualdade."""
        condicoes: list[str] = []
        params: list = []

        termo_normalizado = normalizar_busca(termo or "")
        if termo_normalizado:
            condicoes.append("titulo_busca LIKE ? ESCAPE '\\'")
            params.append(f"%{_escapar_like(termo_normalizado)}%")
        if projeto:
            condicoes.append("projeto = ?")
            params.append(projeto)

        sql = "SELECT * FROM historico"
        if condicoes:
            sql += " WHERE " + " AND ".join(condicoes)
        sql += " ORDER BY criado_em DESC, id DESC LIMIT ?"
        params.append(int(limite))

        cursor = self._executar(sql, tuple(params))
        return [self._linha(row) for row in cursor.fetchall()]
