-- Histórico de downloads. SPEC 9.
--
-- Chave: (extractor, video_id, perfil). O mesmo vídeo em qualidades
-- diferentes são registros distintos. `extractor` entra na chave porque
-- video_id só é único dentro de um site.
--
-- Uma linha por chave, representando a ÚLTIMA tentativa (upsert).
--
-- status: baixando | concluido | falhou | interrompido
--   `baixando` é gravado no INÍCIO do download. É o que permite, na subida
--   seguinte, marcar como `interrompido` o que estava rodando quando o
--   programa fechou (SPEC 10.1). Sem essa linha, um job morto no meio não
--   deixaria rastro nenhum.
--
-- titulo_busca: título normalizado (minúsculas, sem acento) para a busca.
--   O LIKE do SQLite só ignora caixa em ASCII — 'Ç' não casa com 'ç'.

CREATE TABLE IF NOT EXISTS historico (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    extractor       TEXT    NOT NULL,
    video_id        TEXT    NOT NULL,
    perfil          TEXT    NOT NULL,
    url_original    TEXT    NOT NULL,
    url_canonica    TEXT    NOT NULL,
    titulo          TEXT    NOT NULL,
    titulo_busca    TEXT    NOT NULL DEFAULT '',
    canal           TEXT,
    duracao_s       INTEGER,
    projeto         TEXT    NOT NULL,
    caminho         TEXT,
    tamanho_bytes   INTEGER,
    resolucao       TEXT,
    status          TEXT    NOT NULL,
    motivo_falha    TEXT,
    mensagem_falha  TEXT,
    criado_em       TEXT    NOT NULL,
    concluido_em    TEXT,

    UNIQUE (extractor, video_id, perfil)
);

CREATE INDEX IF NOT EXISTS idx_historico_busca   ON historico (titulo_busca);
CREATE INDEX IF NOT EXISTS idx_historico_projeto ON historico (projeto);
CREATE INDEX IF NOT EXISTS idx_historico_criado  ON historico (criado_em DESC);
