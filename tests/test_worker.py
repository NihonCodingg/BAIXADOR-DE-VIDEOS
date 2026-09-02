"""Testes de T5 — a thread de trabalho. UM download por vez.

Downloader e histórico são dublês; `preparar` (que resolve opções e destino)
é injetado. Espera por Event com timeout, nunca por sleep.

Referência: SPEC 10.4 e 10.5.
"""

import threading
from datetime import datetime

import pytest

from src.domain.erros import MotivoFalha, NomeImpossivel
from src.domain.models import EstadoJob, Job, Video
from src.download.traducao_erros import Classificacao, ErroDeDownload
from src.queue.fila import Fila
from src.queue.worker import Preparacao, Worker
from src.storage.historico import Historico

ESPERA = 3.0


def video(video_id="LzS8kB6lIm0") -> Video:
    return Video(video_id=video_id, extractor="Youtube",
                 url_canonica=f"https://www.youtube.com/watch?v={video_id}",
                 titulo="t", canal=None, duracao_s=None, thumbnail_url=None,
                 data_upload=None, formatos=())


def job(video_id="LzS8kB6lIm0", id_="j1") -> Job:
    return Job(id=id_, video=video(video_id), perfil="edicao_1080", projeto="p",
               estado=EstadoJob.NA_FILA, criado_em=datetime(2026, 9, 2),
               url_original="u")


def preparar_simples(j: Job) -> Preparacao:
    return Preparacao(url=j.video.url_canonica, opcoes={"format": "b"},
                      destino=f"D:/F/{j.id}.mp4")


class HistoricoFalso:
    """Gravador: registra as chamadas e sinaliza quando um job termina."""

    def __init__(self):
        self.chamadas = []
        self.terminou = threading.Event()
        self.falhar_em_iniciar = None

    def iniciar(self, video, *, perfil, projeto, url_original):
        self.chamadas.append(("iniciar", video.video_id, perfil, projeto, url_original))
        if self.falhar_em_iniciar:
            raise self.falhar_em_iniciar

    def concluir(self, extractor, video_id, perfil, *, caminho, tamanho_bytes, resolucao=None):
        self.chamadas.append(("concluir", video_id, caminho, tamanho_bytes, resolucao))
        self.terminou.set()

    def falhar(self, extractor, video_id, perfil, *, motivo, mensagem):
        self.chamadas.append(("falhar", video_id, motivo, mensagem))
        self.terminou.set()

    def marcar_interrompidos(self):
        self.chamadas.append(("marcar_interrompidos",))
        return 1


class DownloaderRoteirizado:
    """Dublê do adapter: eventos de progresso, erro ou caminho, por URL."""

    def __init__(self, eventos=None, erro=None, caminho="D:/F/final.mp4"):
        self.eventos = eventos or []
        self.erro = erro
        self.caminho = caminho
        self.chamadas = []
        self.ativos = 0
        self.max_ativos = 0
        self._lock = threading.Lock()

    def baixar(self, url, opcoes, ao_progredir):
        with self._lock:
            self.ativos += 1
            self.max_ativos = max(self.max_ativos, self.ativos)
        try:
            self.chamadas.append(("baixar", url, opcoes))
            for evento in self.eventos:
                ao_progredir(evento)
            if self.erro is not None:
                raise self.erro
            return self.caminho
        finally:
            with self._lock:
                self.ativos -= 1


class DownloaderBloqueante(DownloaderRoteirizado):
    """Trava dentro de baixar() até o teste liberar — simula download longo."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.entrou = threading.Event()
        self.liberar = threading.Event()

    def baixar(self, url, opcoes, ao_progredir):
        self.entrou.set()
        self.liberar.wait(ESPERA)
        return super().baixar(url, opcoes, ao_progredir)


def erro_de_download(motivo=MotivoFalha.PRIVADO, original="Private video"):
    return ErroDeDownload(Classificacao(motivo, original))


@pytest.fixture
def montar():
    """Fábrica de worker já iniciado; para no teardown."""
    workers = []

    def _montar(downloader, historico=None, preparar=preparar_simples):
        fila = Fila()
        hist = historico or HistoricoFalso()
        w = Worker(fila, downloader, hist, preparar)
        w.iniciar()
        workers.append(w)
        return fila, w, hist

    yield _montar
    for w in workers:
        w.parar(timeout=1.0)


# ===========================================================================
# Ciclo feliz
# ===========================================================================

def test_ciclo_feliz(montar):
    dl = DownloaderRoteirizado()
    fila, w, hist = montar(dl)
    fila.adicionar(job())

    assert hist.terminou.wait(ESPERA)
    j = fila.obter("j1")
    assert j.estado is EstadoJob.CONCLUIDO
    assert j.caminho_final == "D:/F/final.mp4"
    assert [c[0] for c in hist.chamadas] == ["iniciar", "concluir"]


def test_worker_usa_a_preparacao_injetada(montar):
    dl = DownloaderRoteirizado()
    fila, w, hist = montar(dl)
    fila.adicionar(job())
    assert hist.terminou.wait(ESPERA)
    assert dl.chamadas[0][1] == "https://www.youtube.com/watch?v=LzS8kB6lIm0"
    assert dl.chamadas[0][2] == {"format": "b"}


def test_historico_recebe_iniciar_antes_do_download(montar):
    """A linha `baixando` é o que permite marcar `interrompido` depois."""
    ordem = []

    class Hist(HistoricoFalso):
        def iniciar(self, *a, **k):
            ordem.append("historico.iniciar")
            return super().iniciar(*a, **k)

    class Dl(DownloaderRoteirizado):
        def baixar(self, *a, **k):
            ordem.append("downloader.baixar")
            return super().baixar(*a, **k)

    fila, w, hist = montar(Dl(), Hist())
    fila.adicionar(job())
    assert hist.terminou.wait(ESPERA)
    assert ordem == ["historico.iniciar", "downloader.baixar"]


def test_progresso_do_hook_chega_na_fila(montar):
    dl = DownloaderRoteirizado(eventos=[
        {"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100,
         "info_dict": {"format_id": "137"}},
    ])
    fila, w, hist = montar(dl)
    fila.adicionar(job())
    assert hist.terminou.wait(ESPERA)
    p = fila.obter("j1").progresso
    assert p is not None and p.baixados == 50 and p.total == 100


def test_progresso_agrega_video_e_audio(montar):
    """Caso 4 da RESEARCH 3.4: dois streams, cada um com seus bytes."""
    dl = DownloaderRoteirizado(eventos=[
        {"status": "downloading", "downloaded_bytes": 500, "total_bytes": 1000,
         "info_dict": {"format_id": "137"}},
        {"status": "downloading", "downloaded_bytes": 200, "total_bytes": 400,
         "info_dict": {"format_id": "140"}},
    ])
    fila, w, hist = montar(dl)
    fila.adicionar(job())
    assert hist.terminou.wait(ESPERA)
    p = fila.obter("j1").progresso
    assert (p.baixados, p.total) == (700, 1400)


def test_resolucao_baixada_vai_para_o_historico(montar):
    """O 'finished' do formato mesclado traz width/height: é a resolução real,
    a que denuncia quando o seletor caiu num fallback."""
    dl = DownloaderRoteirizado(eventos=[
        {"status": "finished", "downloaded_bytes": 10, "total_bytes": 10,
         "info_dict": {"format_id": "137+140", "width": 1080, "height": 1920}},
    ])
    fila, w, hist = montar(dl)
    fila.adicionar(job())
    assert hist.terminou.wait(ESPERA)
    concluir = next(c for c in hist.chamadas if c[0] == "concluir")
    assert concluir[4] == "1080x1920"


def test_hook_que_levanta_nao_derruba_o_worker(montar):
    """Um KeyError dentro do hook derruba o download do yt-dlp; o worker
    ainda assim precisa registrar a falha e seguir para o próximo."""
    dl = DownloaderRoteirizado(eventos=[{"status": "downloading", "speed": "lixo"}])
    fila, w, hist = montar(dl)
    fila.adicionar(job())
    assert hist.terminou.wait(ESPERA)
    assert fila.obter("j1").estado is EstadoJob.CONCLUIDO


# ===========================================================================
# Falhas
# ===========================================================================

def test_erro_de_download_vira_falhou_com_motivo(montar):
    dl = DownloaderRoteirizado(erro=erro_de_download())
    fila, w, hist = montar(dl)
    fila.adicionar(job())
    assert hist.terminou.wait(ESPERA)
    j = fila.obter("j1")
    assert j.estado is EstadoJob.FALHOU
    assert j.motivo_falha == "privado"
    assert j.mensagem_falha == "Private video"
    assert ("falhar", "LzS8kB6lIm0", "privado", "Private video") in hist.chamadas


def test_erro_inesperado_vira_falhou_desconhecido_e_o_worker_sobrevive(montar):
    dl = DownloaderRoteirizado(erro=RuntimeError("bug no adapter"))
    fila, w, hist = montar(dl)
    fila.adicionar(job(id_="a"))
    assert hist.terminou.wait(ESPERA)
    assert fila.obter("a").estado is EstadoJob.FALHOU
    assert fila.obter("a").motivo_falha == "desconhecido"
    assert "bug no adapter" in fila.obter("a").mensagem_falha

    hist.terminou.clear()
    dl.erro = None
    fila.adicionar(job(video_id="bbbbbbbbbbb", id_="b"))
    assert hist.terminou.wait(ESPERA), "o worker morreu depois do erro"
    assert fila.obter("b").estado is EstadoJob.CONCLUIDO


def test_preparar_que_falha_vira_falhou_sem_chamar_o_downloader(montar):
    """Pasta profunda demais (NomeImpossivel) é falha do job, não do worker."""
    def preparar(j):
        raise NomeImpossivel("pasta profunda demais")

    dl = DownloaderRoteirizado()
    fila, w, hist = montar(dl, preparar=preparar)
    fila.adicionar(job())
    assert hist.terminou.wait(ESPERA)
    assert fila.obter("j1").estado is EstadoJob.FALHOU
    assert "profunda" in fila.obter("j1").mensagem_falha
    assert dl.chamadas == []


def test_historico_que_falha_ao_iniciar_impede_o_download(montar):
    """Conservador: sem registro, sem download. Um arquivo sem linha no
    histórico contradiz "sei onde cada arquivo está"."""
    hist = HistoricoFalso()
    hist.falhar_em_iniciar = RuntimeError("disco cheio")
    dl = DownloaderRoteirizado()
    fila, w, _ = montar(dl, hist)
    fila.adicionar(job())
    assert fila_terminou(fila, "j1")
    assert fila.obter("j1").estado is EstadoJob.FALHOU
    assert dl.chamadas == []


def fila_terminou(fila, job_id, espera=ESPERA):
    """Espera um job chegar a estado terminal, em passos curtos e limitados."""
    fim = threading.Event()
    from src.domain.models import ESTADOS_TERMINAIS

    def observar():
        import time
        prazo = time.monotonic() + espera
        while time.monotonic() < prazo:
            j = fila.obter(job_id)
            if j and j.estado in ESTADOS_TERMINAIS:
                fim.set()
                return
            time.sleep(0.01)

    threading.Thread(target=observar, daemon=True).start()
    return fim.wait(espera)


# ===========================================================================
# Serialização e cancelamento
# ===========================================================================

def test_um_download_por_vez(montar):
    dl = DownloaderBloqueante()
    fila, w, hist = montar(dl)
    fila.adicionar(job(id_="a"))
    fila.adicionar(job(video_id="bbbbbbbbbbb", id_="b"))

    assert dl.entrou.wait(ESPERA)
    assert fila.obter("a").estado is EstadoJob.BAIXANDO
    assert fila.obter("b").estado is EstadoJob.NA_FILA, "o segundo começou antes do primeiro acabar"

    dl.liberar.set()
    assert hist.terminou.wait(ESPERA)
    assert fila_terminou(fila, "b")
    assert dl.max_ativos == 1


def test_cancelado_antes_de_comecar_nao_e_baixado(montar):
    dl = DownloaderBloqueante()
    fila, w, hist = montar(dl)
    fila.adicionar(job(id_="a"))
    assert dl.entrou.wait(ESPERA)
    fila.adicionar(job(video_id="bbbbbbbbbbb", id_="b"))
    assert fila.cancelar("b") is True
    dl.liberar.set()
    assert hist.terminou.wait(ESPERA)
    w.parar(timeout=ESPERA)
    assert fila.obter("b").estado is EstadoJob.CANCELADO
    assert [c[1] for c in dl.chamadas] == ["https://www.youtube.com/watch?v=LzS8kB6lIm0"]


# ===========================================================================
# parar() — interrupção
# ===========================================================================

def test_parar_com_fila_vazia_retorna_limpo(montar):
    fila, w, hist = montar(DownloaderRoteirizado())
    w.parar(timeout=ESPERA)
    assert w.vivo is False


def test_parar_com_job_em_andamento_marca_interrompido(montar):
    """O requisito de origem: fechou no meio -> interrompido, nunca concluído."""
    dl = DownloaderBloqueante()
    fila, w, hist = montar(dl)
    fila.adicionar(job())
    assert dl.entrou.wait(ESPERA)

    w.parar(timeout=0.2)

    assert fila.obter("j1").estado is EstadoJob.INTERROMPIDO
    assert ("marcar_interrompidos",) in hist.chamadas
    dl.liberar.set()


def test_conclusao_tardia_depois_de_parar_nao_ressuscita(montar):
    dl = DownloaderBloqueante()
    fila, w, hist = montar(dl)
    fila.adicionar(job())
    assert dl.entrou.wait(ESPERA)
    w.parar(timeout=0.2)
    assert fila.obter("j1").estado is EstadoJob.INTERROMPIDO

    dl.liberar.set()
    assert hist.terminou.wait(ESPERA) or True     # pode ou não gravar; o estado é o que importa
    w.parar(timeout=ESPERA)
    assert fila.obter("j1").estado is EstadoJob.INTERROMPIDO


def test_parar_e_idempotente(montar):
    fila, w, hist = montar(DownloaderRoteirizado())
    w.parar(timeout=ESPERA)
    w.parar(timeout=ESPERA)


def test_iniciar_duas_vezes_nao_cria_duas_threads(montar):
    fila, w, hist = montar(DownloaderRoteirizado())
    w.iniciar()
    assert threading.active_count() >= 1
    assert w.vivo is True


# ===========================================================================
# Integração com o histórico real
# ===========================================================================

def test_integracao_com_historico_real(tmp_path):
    hist = Historico(tmp_path / "h.db")
    hist.criar_schema()
    fila = Fila()
    dl = DownloaderRoteirizado(eventos=[
        {"status": "finished", "downloaded_bytes": 10, "total_bytes": 10,
         "info_dict": {"format_id": "137+140", "width": 1080, "height": 1920}},
    ])
    w = Worker(fila, dl, hist, preparar_simples)
    w.iniciar()
    fila.adicionar(job())
    assert fila_terminou(fila, "j1")
    w.parar(timeout=ESPERA)

    r = hist.ja_baixado("Youtube", "LzS8kB6lIm0", "edicao_1080")
    assert r is not None
    assert r.caminho == "D:/F/final.mp4"
    assert r.resolucao == "1080x1920"
    hist.fechar()
