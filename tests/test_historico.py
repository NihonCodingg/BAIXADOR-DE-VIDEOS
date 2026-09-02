"""Testes de T4 — histórico persistente em SQLite.

Escritos ANTES da implementação. Nenhum teste toca a rede nem disco fora de
tmp_path. O relógio é injetado para as datas serem determinísticas.

Referência: SPEC 9 e 10.1.
"""

import sqlite3
import threading

import pytest

from src.domain.models import Video
from src.storage.historico import (
    Historico,
    RegistroHistorico,
    RegistroNaoEncontrado,
    normalizar_busca,
)


# ===========================================================================
# Fixtures
# ===========================================================================

class Relogio:
    """Relógio injetável: cada chamada avança um segundo, em UTC ISO-8601."""

    def __init__(self):
        self.n = 0

    def __call__(self) -> str:
        self.n += 1
        return f"2026-09-02T10:00:{self.n:02d}+00:00"


@pytest.fixture
def relogio():
    return Relogio()


@pytest.fixture
def h(tmp_path, relogio):
    hist = Historico(tmp_path / "historico.db", agora=relogio)
    hist.criar_schema()
    yield hist
    hist.fechar()


def video(video_id="LzS8kB6lIm0", titulo="Camisa azul da Seleção", extractor="Youtube",
          canal="Canal Michuruca", duracao=65) -> Video:
    return Video(video_id=video_id, extractor=extractor,
                 url_canonica=f"https://www.youtube.com/watch?v={video_id}",
                 titulo=titulo, canal=canal, duracao_s=duracao,
                 thumbnail_url=None, data_upload="20260901", formatos=())


def iniciar(h, v=None, perfil="edicao_1080", projeto="pessoal"):
    v = v or video()
    return h.iniciar(v, perfil=perfil, projeto=projeto, url_original=v.url_canonica)


# ===========================================================================
# Schema
# ===========================================================================

def test_criar_schema_e_idempotente(h):
    h.criar_schema()
    h.criar_schema()


def test_cria_o_diretorio_do_banco_se_nao_existir(tmp_path, relogio):
    caminho = tmp_path / "data" / "sub" / "historico.db"
    hist = Historico(caminho, agora=relogio)
    hist.criar_schema()
    hist.fechar()
    assert caminho.exists()


def test_schema_tem_a_tabela_e_a_chave_unica(tmp_path, relogio):
    caminho = tmp_path / "h.db"
    hist = Historico(caminho, agora=relogio)
    hist.criar_schema()
    hist.fechar()
    con = sqlite3.connect(caminho)
    indices = con.execute("PRAGMA index_list(historico)").fetchall()
    con.close()
    assert any(row[2] == 1 for row in indices), "falta o índice UNIQUE"


# ===========================================================================
# iniciar — a linha `baixando` que torna o `interrompido` possível
# ===========================================================================

def test_iniciar_grava_baixando_sem_caminho(h):
    r = iniciar(h)
    assert r.status == "baixando"
    assert r.caminho is None
    assert r.tamanho_bytes is None
    assert r.concluido_em is None


def test_iniciar_grava_datas_em_iso8601_utc(h):
    r = iniciar(h)
    assert r.criado_em == "2026-09-02T10:00:01+00:00"


def test_iniciar_copia_os_metadados_do_video(h):
    r = iniciar(h)
    assert r.video_id == "LzS8kB6lIm0"
    assert r.extractor == "Youtube"
    assert r.titulo == "Camisa azul da Seleção"
    assert r.canal == "Canal Michuruca"
    assert r.duracao_s == 65
    assert r.perfil == "edicao_1080"
    assert r.projeto == "pessoal"


def test_iniciar_com_o_fixture_real(h, info_dict_real):
    v = Video.de_info_dict(info_dict_real)
    r = h.iniciar(v, perfil="edicao_1080", projeto="pessoal",
                  url_original=info_dict_real["original_url"])
    assert r.titulo == info_dict_real["title"]
    assert r.url_canonica == info_dict_real["webpage_url"]
    assert r.url_original == info_dict_real["original_url"]


def test_iniciar_devolve_id_positivo(h):
    assert iniciar(h).id > 0


# ===========================================================================
# concluir / falhar
# ===========================================================================

def test_concluir_preenche_caminho_tamanho_e_data(h):
    iniciar(h)
    r = h.concluir("Youtube", "LzS8kB6lIm0", "edicao_1080",
                   caminho="D:/F/x.mp4", tamanho_bytes=12345, resolucao="1080x1920")
    assert r.status == "concluido"
    assert r.caminho == "D:/F/x.mp4"
    assert r.tamanho_bytes == 12345
    assert r.resolucao == "1080x1920"
    assert r.concluido_em == "2026-09-02T10:00:02+00:00"


def test_falhar_guarda_motivo_e_mensagem_sem_caminho(h):
    iniciar(h)
    r = h.falhar("Youtube", "LzS8kB6lIm0", "edicao_1080",
                 motivo="privado", mensagem="Private video")
    assert r.status == "falhou"
    assert r.motivo_falha == "privado"
    assert r.mensagem_falha == "Private video"
    assert r.caminho is None
    assert r.concluido_em is not None


def test_concluir_registro_inexistente_levanta(h):
    with pytest.raises(RegistroNaoEncontrado):
        h.concluir("Youtube", "naoexiste0", "edicao_1080", caminho="x", tamanho_bytes=1)


def test_falhar_registro_inexistente_levanta(h):
    with pytest.raises(RegistroNaoEncontrado):
        h.falhar("Youtube", "naoexiste0", "edicao_1080", motivo="x", mensagem="y")


# ===========================================================================
# A chave única (extractor, video_id, perfil)
# ===========================================================================

def test_mesmo_video_em_perfis_diferentes_sao_dois_registros(h):
    iniciar(h, perfil="edicao_1080")
    iniciar(h, perfil="so_audio")
    assert len(h.buscar()) == 2


def test_mesmo_video_id_em_extractors_diferentes_sao_dois_registros(h):
    iniciar(h, video(extractor="Youtube"))
    iniciar(h, video(extractor="Vimeo"))
    assert len(h.buscar()) == 2


def test_reiniciar_mesma_chave_faz_upsert_e_nao_duplica(h):
    """Decidido: uma linha por chave, representando a ÚLTIMA tentativa.

    Rebaixar depois de uma falha precisa funcionar sem violar o UNIQUE.
    """
    iniciar(h)
    h.falhar("Youtube", "LzS8kB6lIm0", "edicao_1080", motivo="rede", mensagem="x")
    r = iniciar(h)
    assert r.status == "baixando"
    assert r.motivo_falha is None, "a nova tentativa começa limpa"
    assert len(h.buscar()) == 1


def test_reiniciar_depois_de_concluido_substitui_o_registro(h):
    """Consequência do upsert que vale deixar explícita no teste."""
    iniciar(h)
    h.concluir("Youtube", "LzS8kB6lIm0", "edicao_1080", caminho="D:/F/a.mp4", tamanho_bytes=1)
    r = iniciar(h)
    assert r.status == "baixando" and r.caminho is None
    assert len(h.buscar()) == 1


# ===========================================================================
# ja_baixado / obter — o aviso de duplicata
# ===========================================================================

def test_ja_baixado_e_none_quando_nunca_visto(h):
    assert h.ja_baixado("Youtube", "LzS8kB6lIm0", "edicao_1080") is None


def test_ja_baixado_e_none_quando_falhou(h):
    iniciar(h)
    h.falhar("Youtube", "LzS8kB6lIm0", "edicao_1080", motivo="rede", mensagem="x")
    assert h.ja_baixado("Youtube", "LzS8kB6lIm0", "edicao_1080") is None


def test_ja_baixado_e_none_enquanto_baixa(h):
    iniciar(h)
    assert h.ja_baixado("Youtube", "LzS8kB6lIm0", "edicao_1080") is None


def test_ja_baixado_devolve_o_registro_concluido(h):
    iniciar(h)
    h.concluir("Youtube", "LzS8kB6lIm0", "edicao_1080", caminho="D:/F/a.mp4", tamanho_bytes=9)
    r = h.ja_baixado("Youtube", "LzS8kB6lIm0", "edicao_1080")
    assert r is not None and r.caminho == "D:/F/a.mp4"


def test_ja_baixado_distingue_o_perfil(h):
    iniciar(h, perfil="edicao_1080")
    h.concluir("Youtube", "LzS8kB6lIm0", "edicao_1080", caminho="a", tamanho_bytes=1)
    assert h.ja_baixado("Youtube", "LzS8kB6lIm0", "so_audio") is None


def test_obter_devolve_qualquer_status(h):
    iniciar(h)
    assert h.obter("Youtube", "LzS8kB6lIm0", "edicao_1080").status == "baixando"
    assert h.obter("Youtube", "nao", "edicao_1080") is None


# ===========================================================================
# buscar
# ===========================================================================

def test_buscar_sem_filtro_devolve_tudo_mais_recente_primeiro(h):
    iniciar(h, video("aaaaaaaaaaa", "Primeiro"))
    iniciar(h, video("bbbbbbbbbbb", "Segundo"))
    iniciar(h, video("ccccccccccc", "Terceiro"))
    assert [r.titulo for r in h.buscar()] == ["Terceiro", "Segundo", "Primeiro"]


def test_buscar_por_termo_parcial(h):
    iniciar(h, video("aaaaaaaaaaa", "Melhores momentos do major"))
    iniciar(h, video("bbbbbbbbbbb", "Rush B"))
    assert [r.titulo for r in h.buscar(termo="major")] == ["Melhores momentos do major"]


def test_buscar_ignora_caixa_ascii(h):
    iniciar(h, video("aaaaaaaaaaa", "Rush B"))
    assert len(h.buscar(termo="rush")) == 1
    assert len(h.buscar(termo="RUSH")) == 1


def test_buscar_ignora_acento_e_caixa_de_acentuado(h):
    """O LIKE do SQLite só ignora caixa em ASCII: 'Ç' não casa com 'ç'.

    Busca normalizada: 'selecao', 'SELEÇÃO' e 'Seleção' encontram o mesmo
    título. Quem digita rápido não põe acento.
    """
    iniciar(h, video("aaaaaaaaaaa", "Camisa azul da Seleção"))
    for termo in ("selecao", "SELEÇÃO", "seleção", "Seleção"):
        assert len(h.buscar(termo=termo)) == 1, termo


def test_buscar_por_projeto(h):
    iniciar(h, video("aaaaaaaaaaa", "A"), projeto="cliente_x")
    iniciar(h, video("bbbbbbbbbbb", "B"), projeto="pessoal")
    assert [r.titulo for r in h.buscar(projeto="cliente_x")] == ["A"]


def test_buscar_termo_e_projeto_juntos(h):
    iniciar(h, video("aaaaaaaaaaa", "Final major"), projeto="cliente_x")
    iniciar(h, video("bbbbbbbbbbb", "Final major"), projeto="pessoal")
    r = h.buscar(termo="major", projeto="pessoal")
    assert len(r) == 1 and r[0].projeto == "pessoal"


def test_buscar_respeita_o_limite(h):
    for i in range(5):
        iniciar(h, video(f"{i:0>11}", f"v{i}"))
    assert len(h.buscar(limite=2)) == 2


def test_buscar_termo_vazio_e_igual_a_sem_termo(h):
    iniciar(h)
    assert len(h.buscar(termo="")) == 1
    assert len(h.buscar(termo="   ")) == 1


def test_buscar_nao_e_vulneravel_a_curinga_do_like(h):
    """'%' e '_' são curingas do LIKE. Um termo com eles não pode virar
    'tudo'."""
    iniciar(h, video("aaaaaaaaaaa", "Rush B"))
    assert h.buscar(termo="%") == []
    assert h.buscar(termo="_") == []


@pytest.mark.parametrize("entrada,esperado", [
    ("Seleção", "selecao"), ("SELEÇÃO", "selecao"), ("Ação!", "acao!"),
    ("  Rush  B ", "rush b"), ("", ""),
])
def test_normalizar_busca(entrada, esperado):
    assert normalizar_busca(entrada) == esperado


# ===========================================================================
# marcar_interrompidos — a reconciliação na subida (SPEC 10.1)
# ===========================================================================

def test_marcar_interrompidos_so_mexe_em_baixando(h):
    iniciar(h, video("aaaaaaaaaaa", "A"))
    iniciar(h, video("bbbbbbbbbbb", "B"))
    h.concluir("Youtube", "bbbbbbbbbbb", "edicao_1080", caminho="x", tamanho_bytes=1)
    iniciar(h, video("ccccccccccc", "C"))
    h.falhar("Youtube", "ccccccccccc", "edicao_1080", motivo="rede", mensagem="x")

    assert h.marcar_interrompidos() == 1
    por_id = {r.video_id: r.status for r in h.buscar()}
    assert por_id == {"aaaaaaaaaaa": "interrompido",
                      "bbbbbbbbbbb": "concluido",
                      "ccccccccccc": "falhou"}


def test_interrompido_nunca_vira_concluido(h):
    """O requisito de origem: programa fechou no meio -> interrompido, não
    concluído."""
    iniciar(h)
    h.marcar_interrompidos()
    assert h.ja_baixado("Youtube", "LzS8kB6lIm0", "edicao_1080") is None
    assert h.obter("Youtube", "LzS8kB6lIm0", "edicao_1080").status == "interrompido"


def test_marcar_interrompidos_preenche_a_data(h):
    iniciar(h)
    h.marcar_interrompidos()
    assert h.obter("Youtube", "LzS8kB6lIm0", "edicao_1080").concluido_em is not None


def test_marcar_interrompidos_e_idempotente(h):
    iniciar(h)
    assert h.marcar_interrompidos() == 1
    assert h.marcar_interrompidos() == 0


def test_interrompido_pode_ser_reiniciado(h):
    iniciar(h)
    h.marcar_interrompidos()
    assert iniciar(h).status == "baixando"


# ===========================================================================
# Persistência e concorrência
# ===========================================================================

def test_dados_sobrevivem_a_reabertura(tmp_path, relogio):
    caminho = tmp_path / "h.db"
    a = Historico(caminho, agora=relogio)
    a.criar_schema()
    a.iniciar(video(), perfil="edicao_1080", projeto="p", url_original="u")
    a.fechar()

    b = Historico(caminho, agora=relogio)
    b.criar_schema()
    assert b.obter("Youtube", "LzS8kB6lIm0", "edicao_1080") is not None
    b.fechar()


def test_escritas_concorrentes_de_varias_threads(h):
    """O worker (T5) grava enquanto a web (T6) lê. Uma conexão SQLite não pode
    ser compartilhada entre threads sem cuidado; o lock interno resolve.
    Threads reais, sem sleep."""
    erros = []

    def gravar(i):
        try:
            h.iniciar(video(f"{i:0>11}", f"v{i}"), perfil="edicao_1080",
                      projeto="p", url_original="u")
            h.buscar()
        except Exception as e:      # noqa: BLE001
            erros.append(e)

    threads = [threading.Thread(target=gravar, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert erros == []
    assert len(h.buscar(limite=100)) == 20


def test_registro_e_imutavel(h):
    r = iniciar(h)
    with pytest.raises(Exception):
        r.status = "concluido"


def test_fechar_e_idempotente(tmp_path, relogio):
    hist = Historico(tmp_path / "h.db", agora=relogio)
    hist.criar_schema()
    hist.fechar()
    hist.fechar()


def test_usar_depois_de_fechar_levanta_erro_claro(tmp_path, relogio):
    hist = Historico(tmp_path / "h.db", agora=relogio)
    hist.criar_schema()
    hist.fechar()
    with pytest.raises(Exception):
        hist.buscar()


def test_datas_iso_ordenam_como_texto(h):
    """A decisão do SPEC 9.1: ISO-8601 em TEXT ordena corretamente, o que
    torna o índice em criado_em útil."""
    iniciar(h, video("aaaaaaaaaaa", "A"))
    iniciar(h, video("bbbbbbbbbbb", "B"))
    datas = [r.criado_em for r in h.buscar()]
    assert datas == sorted(datas, reverse=True)
