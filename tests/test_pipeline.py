"""Testes de T6 (rodada 1) — o pipeline, a orquestração que a CLI e a web usam.

Real: domínio, Fila, Worker, Historico (em tmp_path). Dublê: o downloader.
Nenhum teste toca a rede.

Referência: SPEC 4.4, 10.1, 11.
"""

import json
import shutil
import time
from pathlib import Path

import pytest
import yaml

from src.domain.models import ESTADOS_TERMINAIS, EstadoJob
from src.download.traducao_erros import Classificacao, ErroDeDownload
from src.domain.erros import MotivoFalha
from src.pipeline import Conflito, EntradaInvalida, NaoEncontrado, Pipeline
from src.storage.historico import Historico

RAIZ = Path(__file__).resolve().parent.parent
ESPERA = 5.0


# ===========================================================================
# Dublês e fixtures
# ===========================================================================

class DownloaderEco:
    """Devolve como caminho final exatamente o outtmpl que recebeu — como se
    o yt-dlp tivesse gravado onde mandamos. Cria o arquivo para o tamanho
    existir."""

    def __init__(self, info, erro_inspecionar=None, erro_baixar=None, eventos=None):
        self.info = info
        self.erro_inspecionar = erro_inspecionar
        self.erro_baixar = erro_baixar
        self.eventos = eventos or []
        self.chamadas = []

    def inspecionar(self, url):
        self.chamadas.append(("inspecionar", url))
        if self.erro_inspecionar:
            raise self.erro_inspecionar
        return dict(self.info)

    def baixar(self, url, opcoes, ao_progredir):
        self.chamadas.append(("baixar", url, dict(opcoes)))
        for e in self.eventos:
            ao_progredir(e)
        if self.erro_baixar:
            raise self.erro_baixar
        destino = Path(opcoes["outtmpl"])
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(b"x" * 10)
        return str(destino)


def ffmpeg_presente():
    from src.download.ffmpeg import StatusFFmpeg
    return StatusFFmpeg(ffmpeg="C:/x/ffmpeg.EXE", ffprobe="C:/x/ffprobe.EXE")


def ffmpeg_ausente():
    from src.download.ffmpeg import StatusFFmpeg
    return StatusFFmpeg(ffmpeg=None, ffprobe=None)


@pytest.fixture
def ambiente(tmp_path):
    """config/ com os perfis REAIS e projetos apontando para tmp_path."""
    config = tmp_path / "config"
    config.mkdir()
    shutil.copy(RAIZ / "config" / "perfis.yaml", config / "perfis.yaml")
    footage = tmp_path / "footage"
    (config / "projetos.yaml").write_text(yaml.safe_dump({"projetos": {
        "pessoal": {"nome": "Canal pessoal", "pasta": str(footage / "pessoal")},
        "cliente_x": {"nome": "Cliente X", "pasta": str(footage / "cliente_x")},
    }}), encoding="utf-8")
    return {"config": config, "data": tmp_path / "data", "footage": footage}


@pytest.fixture
def subir(ambiente, info_dict_real):
    """Fábrica de Pipeline com downloader dublê; encerra no teardown."""
    criados = []

    def _subir(downloader=None, detectar_ffmpeg=ffmpeg_presente):
        dl = downloader or DownloaderEco(info_dict_real)
        p = Pipeline(ambiente["config"], ambiente["data"],
                     downloader=dl, detectar_ffmpeg=detectar_ffmpeg)
        criados.append(p)
        return p, dl

    yield _subir
    for p in criados:
        p.encerrar()


URL_REAL = "https://youtube.com/shorts/LzS8kB6lIm0?si=0RP8BxS-q-XGH4Dw"
CANONICO = "https://www.youtube.com/watch?v=LzS8kB6lIm0"


def esperar_terminal(pipeline, job_id, espera=ESPERA):
    prazo = time.monotonic() + espera
    while time.monotonic() < prazo:
        for j in pipeline.estado_fila():
            if j["id"] == job_id and j["estado"] in {e.value for e in ESTADOS_TERMINAIS}:
                return j
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} não terminou em {espera}s")


# ===========================================================================
# Subida
# ===========================================================================

def test_sobe_e_cria_o_banco(subir, ambiente):
    p, _ = subir()
    assert (ambiente["data"] / "historico.db").exists()


def test_reconcilia_interrompidos_na_subida(ambiente, info_dict_real):
    """SPEC 10.1: o que estava `baixando` quando o programa fechou vira
    `interrompido` na subida seguinte — nunca concluído."""
    from src.domain.models import Video
    h = Historico(ambiente["data"] / "historico.db")
    h.criar_schema()
    h.iniciar(Video.de_info_dict(info_dict_real), perfil="edicao_1080",
              projeto="pessoal", url_original=URL_REAL)
    h.fechar()

    p = Pipeline(ambiente["config"], ambiente["data"],
                 downloader=DownloaderEco(info_dict_real), detectar_ffmpeg=ffmpeg_presente)
    try:
        linhas = p.historico()
        assert linhas[0]["status"] == "interrompido"
    finally:
        p.encerrar()


def test_config_lista_perfis_projetos_e_ffmpeg(subir):
    p, _ = subir()
    c = p.config()
    assert {x["nome"] for x in c["perfis"]} == {"edicao_1080", "edicao_4k", "so_audio", "preview_leve"}
    assert all(x["disponivel"] for x in c["perfis"])
    assert {x["nome"] for x in c["projetos"]} == {"pessoal", "cliente_x"}
    assert all(x["valido"] for x in c["projetos"])
    assert c["ffmpeg"]["disponivel"] is True and c["ffmpeg"]["completo"] is True


def test_config_sem_ffmpeg_marca_perfis_indisponiveis(subir):
    p, _ = subir(detectar_ffmpeg=ffmpeg_ausente)
    c = p.config()
    assert c["ffmpeg"]["disponivel"] is False
    assert not any(x["disponivel"] for x in c["perfis"] if x["exige_ffmpeg"])


def test_config_e_serializavel_em_json(subir):
    p, _ = subir()
    json.dumps(p.config())


# ===========================================================================
# inspecionar — metadados sem baixar, resultado parcial
# ===========================================================================

def test_inspecionar_link_real(subir):
    p, dl = subir()
    itens = p.inspecionar(URL_REAL)
    assert len(itens) == 1
    item = itens[0]
    assert item["ok"] is True
    assert item["url"] == CANONICO
    assert item["aviso"] is None
    v = item["video"]
    assert v["titulo"].startswith("Camisa azul da Seleção")
    assert v["canal"] == "Canal Michuruca"
    assert v["duracao_s"] == 65
    assert v["thumbnail"].startswith("https://i.ytimg.com/")
    assert len(v["formatos"]) == 41, "41 = 45 do fixture menos 4 storyboards"
    assert dl.chamadas == [("inspecionar", CANONICO)], "inspeciona pelo canônico"


def test_inspecionar_expoe_qualidades_pela_menor_dimensao(subir):
    """Coerente com SPEC 6.3: o teto é na menor dimensão, e é isso que a UI
    mostra como 'qualidades disponíveis' — igual para vertical e horizontal."""
    p, _ = subir()
    v = p.inspecionar(URL_REAL)[0]["video"]
    assert v["qualidades"] == [144, 240, 360, 480, 608, 720, 1080]


def test_inspecionar_formatos_trazem_os_tres_estados_de_audio(subir):
    p, _ = subir()
    formatos = {f["format_id"]: f for f in p.inspecionar(URL_REAL)[0]["video"]["formatos"]}
    assert formatos["233"]["acodec"] is None and formatos["233"]["tem_audio"] is True
    assert formatos["137"]["tem_video"] is True and formatos["137"]["tem_audio"] is False
    assert formatos["140"]["tem_video"] is False and formatos["140"]["tem_audio"] is True


def test_inspecionar_e_serializavel_em_json(subir):
    p, _ = subir()
    json.dumps(p.inspecionar(URL_REAL))


def test_inspecionar_resultado_parcial(subir):
    """Um link ruim numa lista de três não invalida os outros (SPEC 11.1)."""
    p, _ = subir()
    itens = p.inspecionar(f"{URL_REAL}\nnão é url\nhttps://vimeo.com/123456789")
    assert [i["ok"] for i in itens] == [True, False, True]
    assert itens[1]["erro"]
    assert itens[1]["original"] == "não é url"


def test_inspecionar_outro_site_traz_o_aviso(subir):
    p, _ = subir()
    item = p.inspecionar("https://vimeo.com/123456789")[0]
    assert item["ok"] is True
    assert item["aviso"] is not None
    assert item["e_youtube"] is False


def test_inspecionar_erro_do_site_vira_item_com_motivo(subir, info_dict_real):
    erro = ErroDeDownload(Classificacao(MotivoFalha.PRIVADO, "Private video"))
    p, _ = subir(DownloaderEco(info_dict_real, erro_inspecionar=erro))
    item = p.inspecionar(URL_REAL)[0]
    assert item["ok"] is False
    assert item["motivo"] == "privado"
    assert "privado" in item["erro"].lower()


def test_inspecionar_deduplica_e_reaproveita_o_cache(subir):
    p, dl = subir()
    p.inspecionar(f"{URL_REAL}\nhttps://youtu.be/LzS8kB6lIm0")
    p.inspecionar(CANONICO)
    assert dl.chamadas.count(("inspecionar", CANONICO)) == 1, "cache por URL canônica"


def test_inspecionar_informa_o_que_ja_foi_baixado_por_perfil(subir):
    p, _ = subir()
    ids = p.enfileirar([URL_REAL], perfil="edicao_1080", projeto="pessoal")
    esperar_terminal(p, ids[0])
    item = p.inspecionar(URL_REAL)[0]
    assert "edicao_1080" in item["baixados"]
    assert item["baixados"]["edicao_1080"]["caminho"].endswith(".mp4")
    assert "so_audio" not in item["baixados"]


def test_inspecionar_texto_vazio(subir):
    p, _ = subir()
    assert p.inspecionar("") == []


# ===========================================================================
# enfileirar — validação e o ciclo completo
# ===========================================================================

def test_enfileirar_e_baixar_ate_o_fim(subir, ambiente):
    p, dl = subir()
    ids = p.enfileirar([URL_REAL], perfil="edicao_1080", projeto="pessoal")
    assert len(ids) == 1
    j = esperar_terminal(p, ids[0])
    assert j["estado"] == "concluido", j
    caminho = Path(j["caminho_final"])
    assert caminho.exists()
    assert caminho.parent == ambiente["footage"] / "pessoal"
    assert caminho.name == ("20260901 - Camisa azul da Seleção críticas ao design "
                            "e lembrança histórica [LzS8kB6lIm0].mp4")


def test_enfileirar_resolve_o_seletor_pela_orientacao(subir):
    """O fixture é um Short vertical: o teto vai em width (SPEC 6.3)."""
    p, dl = subir()
    ids = p.enfileirar([URL_REAL], perfil="edicao_1080", projeto="pessoal")
    esperar_terminal(p, ids[0])
    opcoes = next(c[2] for c in dl.chamadas if c[0] == "baixar")
    assert "[width<=1080]" in opcoes["format"]
    assert opcoes["merge_output_format"] == "mp4"
    assert opcoes["noplaylist"] is True


def test_enfileirar_grava_no_historico(subir):
    p, _ = subir()
    ids = p.enfileirar([URL_REAL], perfil="edicao_1080", projeto="pessoal")
    esperar_terminal(p, ids[0])
    h = p.historico()
    assert len(h) == 1
    assert h[0]["status"] == "concluido"
    assert h[0]["projeto"] == "pessoal"
    assert h[0]["tamanho_bytes"] == 10


def test_enfileirar_perfil_so_audio_usa_a_extensao_do_perfil(subir):
    p, _ = subir()
    ids = p.enfileirar([URL_REAL], perfil="so_audio", projeto="pessoal")
    j = esperar_terminal(p, ids[0])
    assert j["caminho_final"].endswith(".m4a")


def test_enfileirar_varios_na_ordem(subir, info_dict_real):
    p, _ = subir()
    ids = p.enfileirar([URL_REAL], perfil="edicao_1080", projeto="pessoal")
    ids += p.enfileirar([URL_REAL], perfil="so_audio", projeto="pessoal")
    for i in ids:
        esperar_terminal(p, i)
    assert [j["id"] for j in p.estado_fila()] == ids


@pytest.mark.parametrize("perfil,projeto", [
    ("nao_existe", "pessoal"), ("edicao_1080", "nao_existe"),
])
def test_enfileirar_perfil_ou_projeto_inexistente(subir, perfil, projeto):
    p, _ = subir()
    with pytest.raises(EntradaInvalida):
        p.enfileirar([URL_REAL], perfil=perfil, projeto=projeto)


def test_enfileirar_perfil_indisponivel_sem_ffmpeg(subir):
    p, _ = subir(detectar_ffmpeg=ffmpeg_ausente)
    with pytest.raises(EntradaInvalida) as exc:
        p.enfileirar([URL_REAL], perfil="edicao_1080", projeto="pessoal")
    assert "ffmpeg" in str(exc.value).lower()


def test_enfileirar_link_invalido(subir):
    p, _ = subir()
    with pytest.raises(EntradaInvalida):
        p.enfileirar(["não é url"], perfil="edicao_1080", projeto="pessoal")


def test_enfileirar_lista_vazia(subir):
    p, _ = subir()
    with pytest.raises(EntradaInvalida):
        p.enfileirar([], perfil="edicao_1080", projeto="pessoal")


def test_enfileirar_ja_baixado_e_conflito_salvo_se_forcar(subir):
    """SPEC 1: avisa se já baixei. Conservador: recusa em vez de rebaixar em
    silêncio; `forcar` existe para quando o usuário quer mesmo."""
    p, _ = subir()
    ids = p.enfileirar([URL_REAL], perfil="edicao_1080", projeto="pessoal")
    esperar_terminal(p, ids[0])
    with pytest.raises(Conflito) as exc:
        p.enfileirar([URL_REAL], perfil="edicao_1080", projeto="pessoal")
    assert ".mp4" in str(exc.value)
    ids2 = p.enfileirar([URL_REAL], perfil="edicao_1080", projeto="pessoal", forcar=True)
    j = esperar_terminal(p, ids2[0])
    assert j["estado"] == "concluido"
    assert j["caminho_final"].endswith(" (2).mp4"), "colisão resolvida, nunca sobrescreve"


def test_enfileirar_mesmo_video_e_perfil_ja_na_fila_e_conflito(subir, info_dict_real):
    class Lento(DownloaderEco):
        def baixar(self, url, opcoes, ao_progredir):
            time.sleep(0.3)
            return super().baixar(url, opcoes, ao_progredir)

    p, _ = subir(Lento(info_dict_real))
    p.enfileirar([URL_REAL], perfil="edicao_1080", projeto="pessoal")
    with pytest.raises(Conflito):
        p.enfileirar([URL_REAL], perfil="edicao_1080", projeto="pessoal")


def test_enfileirar_mesmo_video_em_perfil_diferente_nao_e_conflito(subir):
    p, _ = subir()
    p.enfileirar([URL_REAL], perfil="edicao_1080", projeto="pessoal")
    p.enfileirar([URL_REAL], perfil="so_audio", projeto="pessoal")


def test_enfileirar_sem_inspecionar_antes_funciona(subir):
    """O cache é otimização, não pré-requisito."""
    p, dl = subir()
    ids = p.enfileirar([URL_REAL], perfil="edicao_1080", projeto="pessoal")
    assert esperar_terminal(p, ids[0])["estado"] == "concluido"


def test_falha_do_site_vira_job_falhou_com_motivo(subir, info_dict_real):
    erro = ErroDeDownload(Classificacao(MotivoFalha.BLOQUEIO_REGIONAL, "geo", {"paises": ["US"]}))
    p, _ = subir(DownloaderEco(info_dict_real, erro_baixar=erro))
    ids = p.enfileirar([URL_REAL], perfil="edicao_1080", projeto="pessoal")
    j = esperar_terminal(p, ids[0])
    assert j["estado"] == "falhou"
    assert j["motivo_falha"] == "bloqueio_regional"
    assert p.historico()[0]["status"] == "falhou"


def test_pasta_profunda_gera_aviso_no_job(ambiente, info_dict_real):
    pasta = ambiente["footage"] / ("p" * 80)
    (ambiente["config"] / "projetos.yaml").write_text(yaml.safe_dump({"projetos": {
        "fundo": {"nome": "Fundo", "pasta": str(pasta)}}}), encoding="utf-8")
    p = Pipeline(ambiente["config"], ambiente["data"],
                 downloader=DownloaderEco(info_dict_real), detectar_ffmpeg=ffmpeg_presente)
    try:
        ids = p.enfileirar([URL_REAL], perfil="edicao_1080", projeto="fundo")
        j = esperar_terminal(p, ids[0])
        assert j["estado"] == "concluido"
        assert j["aviso"] and "profund" in j["aviso"].lower()
    finally:
        p.encerrar()


# ===========================================================================
# estado_fila / cancelar / historico
# ===========================================================================

def test_estado_fila_e_serializavel_e_traz_progresso(subir, info_dict_real):
    eventos = [{"status": "downloading", "downloaded_bytes": 5, "total_bytes": 10,
                "info_dict": {"format_id": "137"}}]
    p, _ = subir(DownloaderEco(info_dict_real, eventos=eventos))
    ids = p.enfileirar([URL_REAL], perfil="edicao_1080", projeto="pessoal")
    j = esperar_terminal(p, ids[0])
    json.dumps(p.estado_fila())
    assert j["progresso"]["percentual"] == 50.0
    assert j["video"]["titulo"].startswith("Camisa")
    assert j["perfil"] == "edicao_1080" and j["projeto"] == "pessoal"


def test_cancelar_na_fila(subir, info_dict_real):
    class Lento(DownloaderEco):
        def baixar(self, url, opcoes, ao_progredir):
            time.sleep(0.3)
            return super().baixar(url, opcoes, ao_progredir)

    p, _ = subir(Lento(info_dict_real))
    a = p.enfileirar([URL_REAL], perfil="edicao_1080", projeto="pessoal")[0]
    b = p.enfileirar([URL_REAL], perfil="so_audio", projeto="pessoal")[0]
    assert p.cancelar(b) is True
    assert next(j for j in p.estado_fila() if j["id"] == b)["estado"] == "cancelado"
    esperar_terminal(p, a)


def test_cancelar_inexistente(subir):
    p, _ = subir()
    with pytest.raises(NaoEncontrado):
        p.cancelar("nao")


def test_cancelar_em_andamento_e_conflito(subir, info_dict_real):
    class Lento(DownloaderEco):
        def baixar(self, url, opcoes, ao_progredir):
            time.sleep(0.4)
            return super().baixar(url, opcoes, ao_progredir)

    p, _ = subir(Lento(info_dict_real))
    a = p.enfileirar([URL_REAL], perfil="edicao_1080", projeto="pessoal")[0]
    prazo = time.monotonic() + ESPERA
    while time.monotonic() < prazo and p.estado_fila()[0]["estado"] != "baixando":
        time.sleep(0.01)
    with pytest.raises(Conflito):
        p.cancelar(a)
    esperar_terminal(p, a)


def test_historico_busca_e_filtra(subir):
    p, _ = subir()
    ids = p.enfileirar([URL_REAL], perfil="edicao_1080", projeto="pessoal")
    esperar_terminal(p, ids[0])
    assert len(p.historico(termo="selecao")) == 1
    assert p.historico(termo="inexistente") == []
    assert p.historico(projeto="cliente_x") == []
    json.dumps(p.historico())


def test_encerrar_e_idempotente(subir):
    p, _ = subir()
    p.encerrar()
    p.encerrar()
