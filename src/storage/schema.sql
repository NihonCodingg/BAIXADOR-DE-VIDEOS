-- Histórico de downloads. SPEC 9.
--
-- Chave: (extractor, video_id, perfil). O mesmo vídeo em qualidades
-- diferentes são registros distintos. `extractor` entra na chave porque
-- video_id só é único dentro de um site.

CREATE TABLE IF NOT EXISTS historico (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id        TEXT    NOT NULL,
    perfil          TEXT    NOT NULL,
    extractor       TEXT    NOT NULL,
    url_original    TEXT    NOT NULL,
    url_canonica    TEXT    NOT NULL,
    titulo          TEXT    NOT NULL,
    canal           TEXT,
    duracao_s       INTEGER,
    projeto         TEXT    NOT NULL,
    caminho         TEXT,
    tamanho_bytes   INTEGER,
    status          TEXT    NOT NULL,
    motivo_falha    TEXT,
    mensagem_falha  TEXT,
    criado_em       TEXT    NOT NULL,
    concluido_em    TEXT,

    UNIQUE (extractor, video_id, perfil)
);

CREATE INDEX IF NOT EXISTS idx_historico_titulo  ON historico (titulo);
CREATE INDEX IF NOT EXISTS idx_historico_projeto ON historico (projeto);
CREATE INDEX IF NOT EXISTS idx_historico_criado  ON historico (criado_em DESC);
