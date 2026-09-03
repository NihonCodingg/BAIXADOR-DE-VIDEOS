"""Orquestração. Usada pela CLI E pela web — nenhuma das duas duplica regra.

É o único ponto que conhece domain, download, storage e queue ao mesmo tempo.
Tudo que sai daqui é dict serializável em JSON: a camada web nunca vê Job,
Video ou Perfil (REGRA 2).

Ticket: T6.
"""

import os
import subprocess
import sys
import threading
import uuid
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .domain.erros import LinkInvalido
from .domain.models import EstadoJob, Job, Video, tem_audio, tem_video
from .domain.nomes import montar_caminho, resolver_colisao
from .domain.perfis import carregar_perfis, disponivel, opcoes_ytdlp
from .domain.projetos import Projeto, carregar_projetos
from .domain.validacao import normalizar_link, normalizar_lote
from .download.adapter import Downloader, validar_seletor
from .download.ffmpeg import detectar
from .download.traducao_erros import ErroDeDownload
from .queue.fila import Fila
from .queue.worker import Preparacao, Worker
from .storage.historico import Historico

_ATIVOS = (EstadoJob.NA_FILA, EstadoJob.BAIXANDO)

AVISO_INTERROMPIDO = (
    "O download foi interrompido, mas há um arquivo de {tamanho} bytes em "
    "{caminho}. Não é possível verificar se está completo — confira antes de "
    "usar, ou baixe de novo com forcar."
)


def abrir_no_sistema(caminho: str) -> None:
    """Abre uma pasta no explorador do sistema.

    Windows é o alvo do projeto (RESEARCH 7); os outros dois entram porque
    custam duas linhas. `os.startfile` em vez de subprocess: não passa pela
    linha de comando, então caminho com espaço, acento ou vírgula não precisa
    de aspas — e é justamente o caminho de footage que costuma ter os três.

    Abre a PASTA, não seleciona o arquivo: `explorer /select,` exige uma
    linha de comando montada à mão que quebra com espaço no caminho, e o
    pedido é abrir a pasta.
    """
    if sys.platform == "win32":
        os.startfile(caminho)                                 # noqa: S606
    elif sys.platform == "darwin":
        subprocess.run(["open", caminho], check=False)        # noqa: S603,S607
    else:
        subprocess.run(["xdg-open", caminho], check=False)    # noqa: S603,S607


class ErroDePedido(Exception):
    """Base dos erros que a API traduz em código HTTP."""


class EntradaInvalida(ErroDePedido):
    """Link, perfil ou projeto inválido. A API responde 400."""


class NaoEncontrado(ErroDePedido):
    """Job inexistente. A API responde 404."""


class Conflito(ErroDePedido):
    """Já baixado, já na fila, ou cancelamento de job em andamento. 409."""


class Pipeline:
    def __init__(self, config_dir: Path, data_dir: Path, *,
                 downloader=None, detectar_ffmpeg: Callable | None = None,
                 abrir_no_explorador: Callable[[str], None] | None = None):
        """Carrega perfis e projetos, detecta o ffmpeg, abre o histórico e
        reconcilia os interrompidos (SPEC 10.1), sobe o worker."""
        self._config_dir = Path(config_dir)
        self._data_dir = Path(data_dir)
        self._downloader = downloader or Downloader()
        self._ffmpeg = (detectar_ffmpeg or detectar)()
        # Injetado para o teste não abrir uma janela do explorador.
        self._abrir = abrir_no_explorador or abrir_no_sistema

        self._perfis = carregar_perfis(
            self._ler_yaml("perfis.yaml"), validar_seletor=validar_seletor)
        self._projetos = carregar_projetos(self._ler_yaml("projetos.yaml"))
        self._projetos_status = {
            nome: self._checar_pasta(projeto)
            for nome, projeto in self._projetos.items()
        }

        self._historico = Historico(self._data_dir / "historico.db")
        self._historico.criar_schema()
        # O que estava `baixando` quando o programa fechou vira `interrompido`
        # — nunca concluído (SPEC 10.1).
        self._avisar_interrompidos_com_arquivo(self._historico.marcar_interrompidos())

        self._fila = Fila()
        self._cache_lock = threading.Lock()
        self._videos: dict[str, Video] = {}        # url -> Video, da inspeção
        self._avisos: dict[str, str] = {}          # job_id -> aviso do preparo

        self._worker = Worker(self._fila, self._downloader, self._historico,
                              self._preparar)
        self._worker.iniciar()
        self._encerrado = False

    # ------------------------------------------------------------- subida

    def _ler_yaml(self, nome: str) -> dict:
        caminho = self._config_dir / nome
        return yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}

    @staticmethod
    def _checar_pasta(projeto: Projeto) -> tuple[bool, str | None]:
        """SPEC 7: a pasta existe ou é criável, e é gravável.

        Decisão 6: NÃO cria nada aqui. Um YAML de exemplo não pode fazer
        aparecer D:/FOOTAGE/cliente_exemplo na primeira execução. A pasta
        nasce em _preparar, quando um download precisa dela.

        Para uma pasta que ainda não existe, a checagem sobe até o primeiro
        ancestral existente: se ele for gravável, a pasta é criável.
        """
        alvo = Path(projeto.pasta)
        if alvo.exists():
            if not alvo.is_dir():
                return False, "o caminho existe e não é uma pasta"
            if not os.access(alvo, os.W_OK):
                return False, "sem permissão de escrita na pasta"
            return True, None

        ancestral = next((a for a in alvo.parents if a.exists()), None)
        if ancestral is None:
            return False, "nenhuma pasta do caminho existe (disco ausente?)"
        if not ancestral.is_dir() or not os.access(ancestral, os.W_OK):
            return False, f"sem permissão de escrita em {ancestral}"
        return True, None

    def _avisar_interrompidos_com_arquivo(self, interrompidos) -> None:
        """Decisão 5: se um `interrompido` tem arquivo no destino, avisa.

        Não dá para verificar integridade: o tamanho esperado nunca chegou a
        ser gravado (o `concluir` não rodou). Então o produto avisa e deixa a
        decisão com o usuário, em vez de concluir um arquivo possivelmente
        truncado ou baixar uma duplicata " (2)" em silêncio.
        """
        for registro in interrompidos or []:
            if not registro.caminho:
                continue
            try:
                existe = os.path.isfile(registro.caminho)
                tamanho = os.path.getsize(registro.caminho) if existe else 0
            except OSError:
                continue
            if not existe:
                continue
            self._historico.avisar(registro.id, AVISO_INTERROMPIDO.format(
                tamanho=tamanho, caminho=registro.caminho))

    # ---------------------------------------------------------- inspeção

    def _obter_video(self, url: str) -> Video:
        """Metadados pela rede, com cache por URL. O cache é otimização:
        enfileirar sem inspecionar antes também funciona."""
        with self._cache_lock:
            video = self._videos.get(url)
        if video is not None:
            return video
        info = self._downloader.inspecionar(url)
        video = Video.de_info_dict(info)
        with self._cache_lock:
            self._videos[url] = video
            if video.url_canonica:
                self._videos[video.url_canonica] = video
        return video

    def _baixados(self, video: Video) -> dict:
        """Por perfil, o registro concluído — é o aviso de duplicata."""
        resultado = {}
        for nome in self._perfis:
            registro = self._historico.ja_baixado(video.extractor, video.video_id, nome)
            if registro is not None:
                resultado[nome] = {
                    "caminho": registro.caminho,
                    "projeto": registro.projeto,
                    "resolucao": registro.resolucao,
                    "concluido_em": registro.concluido_em,
                }
        return resultado

    @staticmethod
    def _video_dict(video: Video) -> dict:
        com_dimensao = [f for f in video.formatos if f.largura and f.altura]
        return {
            "id": video.video_id,
            "extractor": video.extractor,
            "url_canonica": video.url_canonica,
            "titulo": video.titulo,
            "canal": video.canal,
            "duracao_s": video.duracao_s,
            "thumbnail": video.thumbnail_url,
            "data_upload": video.data_upload,
            # Pela MENOR dimensão, coerente com o teto dos perfis (SPEC 6.3):
            # um Short 1080x1920 e um vídeo 1920x1080 mostram o mesmo "1080".
            "qualidades": sorted({min(f.largura, f.altura) for f in com_dimensao}),
            "formatos": [
                {
                    "format_id": f.format_id,
                    "ext": f.ext,
                    "resolucao": f.resolucao,
                    "largura": f.largura,
                    "altura": f.altura,
                    "fps": f.fps,
                    "vcodec": f.vcodec,
                    "acodec": f.acodec,          # None = desconhecido, não ausente
                    "tem_video": tem_video(f),
                    "tem_audio": tem_audio(f),
                    "tbr": f.tbr,
                    "tamanho_bytes": f.tamanho_bytes,
                }
                for f in video.formatos
            ],
        }

    def inspecionar(self, texto_links: str) -> list[dict]:
        """Normaliza, valida e busca metadados. Não baixa.

        Resultado parcial: cada item traz seu próprio `ok`. Um link ruim numa
        lista de dez não invalida os outros nove (SPEC 11.1).
        """
        itens: list[dict] = []
        for link in normalizar_lote(texto_links):
            if not link.ok:
                itens.append({"ok": False, "original": link.original,
                              "url": None, "erro": link.erro,
                              "motivo": "link_invalido"})
                continue
            try:
                video = self._obter_video(link.url)
            except ErroDeDownload as erro:
                itens.append({"ok": False, "original": link.original,
                              "url": link.url, "erro": erro.classificacao.mensagem,
                              "motivo": erro.motivo.value})
                continue
            itens.append({
                "ok": True,
                "original": link.original,
                "url": link.url,
                "e_youtube": link.e_youtube,
                "aviso": link.aviso,
                "video": self._video_dict(video),
                "baixados": self._baixados(video),
            })
        return itens

    # ------------------------------------------------------------- fila

    def _na_fila(self, video: Video, perfil: str) -> bool:
        return any(
            j.estado in _ATIVOS
            and j.perfil == perfil
            and j.video.extractor == video.extractor
            and j.video.video_id == video.video_id
            for j in self._fila.instantaneo()
        )

    def enfileirar(self, urls: list[str], perfil: str, projeto: str,
                   forcar: bool = False) -> list[str]:
        """Devolve os ids dos jobs. EntradaInvalida / Conflito.

        Tudo ou nada: valida todos os links (inclusive duplicatas) antes de
        enfileirar o primeiro.
        """
        if not urls:
            raise EntradaInvalida("Nenhum link informado.")

        definicao, _ = self._validar_destino(perfil, projeto)

        jobs: list[Job] = []
        for url in urls:
            try:
                link = normalizar_link(url)
            except LinkInvalido as erro:
                raise EntradaInvalida(str(erro)) from erro
            try:
                video = self._obter_video(link.url)
            except ErroDeDownload as erro:
                raise EntradaInvalida(erro.classificacao.mensagem) from erro

            ja = self._historico.ja_baixado(video.extractor, video.video_id, perfil)
            if ja is not None and not forcar:
                raise Conflito(
                    f"Já baixado no perfil {perfil!r}: {ja.caminho}. "
                    f"Use forcar=true para baixar de novo.")
            if self._na_fila(video, perfil) or any(
                    j.video.video_id == video.video_id and j.perfil == perfil
                    for j in jobs):
                raise Conflito(f"Este vídeo já está na fila no perfil {perfil!r}.")

            jobs.append(Job(
                id=uuid.uuid4().hex, video=video, perfil=perfil, projeto=projeto,
                estado=EstadoJob.NA_FILA, criado_em=datetime.now(timezone.utc),
                url_original=link.original,
            ))

        return [self._fila.adicionar(job) for job in jobs]

    def _validar_destino(self, perfil: str, projeto: str):
        """Perfil e projeto existem, estão disponíveis e são válidos.

        Fatorado porque `enfileirar` e `simular` precisam exatamente da mesma
        checagem: o --dry-run não vale nada se aceitar o que o download recusa.
        """
        definicao = self._perfis.get(perfil)
        if definicao is None:
            raise EntradaInvalida(f"Perfil {perfil!r} não existe.")
        if not disponivel(definicao, self._ffmpeg.disponivel):
            raise EntradaInvalida(
                f"O perfil {perfil!r} exige ffmpeg, que não foi encontrado no PATH.")
        if projeto not in self._projetos:
            raise EntradaInvalida(f"Projeto {projeto!r} não existe.")
        valido, motivo = self._projetos_status[projeto]
        if not valido:
            raise EntradaInvalida(f"Projeto {projeto!r} inválido: {motivo}")
        return definicao, self._projetos[projeto]

    def _destino(self, video: Video, perfil, projeto: Projeto) -> tuple[str, str | None]:
        """Onde o arquivo vai cair, e o aviso de pasta profunda demais.

        Não cria pasta e não baixa: é o MESMO cálculo que o worker usa e que o
        `--dry-run` mostra. Duas contas separadas seriam duas verdades, e o
        --dry-run existe justamente para conferir o nome antes de gravar.
        """
        montado = montar_caminho(
            projeto.pasta, video.titulo, video.video_id,
            video.data_upload, "." + perfil.merge_output_format)
        return resolver_colisao(montado.caminho, os.path.exists), montado.aviso

    def simular(self, urls: list[str], perfil: str, projeto: str) -> list[dict]:
        """O que `enfileirar` faria, sem baixar nada e sem criar pasta.

        Alimenta o `--dry-run` da CLI. Consulta os metadados (é de onde sai o
        nome do arquivo), mas NUNCA chama `baixar`.

        Resultado parcial por link, como o `inspecionar`: quem roda um dry-run
        quer ver todos os problemas de uma vez, não o primeiro. Perfil e
        projeto, esses sim, são erro de saída.
        """
        if not urls:
            raise EntradaInvalida("Nenhum link informado.")
        definicao, destino_projeto = self._validar_destino(perfil, projeto)

        itens: list[dict] = []
        for url in urls:
            try:
                link = normalizar_link(url)
            except LinkInvalido as erro:
                itens.append({"ok": False, "original": url, "url": None,
                              "erro": str(erro), "motivo": "link_invalido"})
                continue
            try:
                video = self._obter_video(link.url)
            except ErroDeDownload as erro:
                itens.append({"ok": False, "original": url, "url": link.url,
                              "erro": erro.classificacao.mensagem,
                              "motivo": erro.motivo.value})
                continue

            caminho, aviso_nome = self._destino(video, definicao, destino_projeto)
            ja = self._historico.ja_baixado(video.extractor, video.video_id, perfil)
            itens.append({
                "ok": True,
                "original": url,
                "url": link.url,
                "e_youtube": link.e_youtube,
                "aviso": " | ".join(x for x in (link.aviso, aviso_nome) if x) or None,
                "video": self._video_dict(video),
                "destino": caminho,
                "ja_baixado": asdict(ja) if ja is not None else None,
            })
        return itens

    def _preparar(self, job: Job) -> Preparacao:
        """Chamado pelo worker, na thread dele, na hora de baixar.

        Resolve perfil -> opções (com o teto na menor dimensão, SPEC 6.3) e
        projeto + nome sanitizado -> destino, com colisão resolvida AGORA, não
        na hora de enfileirar. NomeImpossivel sobe e vira falha do job.
        """
        perfil = self._perfis[job.perfil]
        projeto = self._projetos[job.projeto]
        Path(projeto.pasta).mkdir(parents=True, exist_ok=True)

        destino, aviso = self._destino(job.video, perfil, projeto)
        if aviso:
            with self._cache_lock:
                self._avisos[job.id] = aviso

        opcoes = opcoes_ytdlp(perfil, job.video.formatos, destino)
        return Preparacao(url=job.video.url_canonica, opcoes=opcoes, destino=destino)

    def _job_dict(self, job: Job) -> dict:
        progresso = None
        if job.progresso is not None:
            p = job.progresso
            progresso = {
                "baixados": p.baixados,
                "total": p.total,
                "percentual": p.percentual,
                "velocidade_bps": p.velocidade_bps,
                "eta_s": p.eta_s,
            }
        with self._cache_lock:
            aviso_preparo = self._avisos.get(job.id)
        aviso = " | ".join(x for x in (aviso_preparo, job.aviso) if x) or None
        return {
            "id": job.id,
            "estado": job.estado.value,
            "ja_existia": job.ja_existia,
            # A url vive no job para "tentar de novo" sobreviver a um reload:
            # sem ela a tela só saberia refazer o download enquanto a aba que
            # enfileirou continuasse aberta.
            "url": job.url_original or job.video.url_canonica,
            "perfil": job.perfil,
            "projeto": job.projeto,
            "criado_em": job.criado_em.isoformat(timespec="seconds"),
            "video": {
                "id": job.video.video_id,
                "titulo": job.video.titulo,
                "canal": job.video.canal,
                "duracao_s": job.video.duracao_s,
                "thumbnail": job.video.thumbnail_url,
            },
            "progresso": progresso,
            "caminho_final": job.caminho_final,
            "motivo_falha": job.motivo_falha,
            "mensagem_falha": job.mensagem_falha,
            "aviso": aviso,
        }

    def estado_fila(self) -> list[dict]:
        return [self._job_dict(job) for job in self._fila.instantaneo()]

    def cancelar(self, job_id: str) -> bool:
        """NaoEncontrado se não existe; Conflito se já começou ou terminou."""
        if self._fila.obter(job_id) is None:
            raise NaoEncontrado(f"Job {job_id!r} não existe.")
        if not self._fila.cancelar(job_id):
            raise Conflito(
                "Só é possível cancelar um job que ainda não começou (SPEC 10.5).")
        return True

    # --------------------------------------------------------- consultas

    def historico(self, termo: str | None = None, projeto: str | None = None,
                  limite: int = 100) -> list[dict]:
        return [asdict(r) for r in self._historico.buscar(termo, projeto, limite)]

    # ------------------------------------------------------ abrir pasta

    def _dentro_de_projeto(self, alvo: Path) -> Path | None:
        """A raiz do projeto que contém `alvo`, ou None.

        Comparação por SEGMENTO de caminho, não por prefixo de string: assim
        `.../cliente_x_secreto` não passa por estar dentro de `.../cliente_x`.
        No Windows a comparação ignora a caixa, e o `resolve()` de quem chama
        já colapsou qualquer `..`.
        """
        for projeto in self._projetos.values():
            try:
                raiz = Path(projeto.pasta).expanduser().resolve()
            except OSError:
                continue
            if alvo.is_relative_to(raiz):
                return raiz
        return None

    def abrir_pasta(self, caminho: str) -> str:
        """Abre no explorador a pasta de `caminho`. Devolve a pasta aberta.

        Só abre o que está DENTRO de um projeto configurado. A aplicação é
        local, mas local não é sem consequência: sem esta checagem, qualquer
        página aberta no navegador poderia mandar abrir qualquer pasta do
        disco. O que não está num projeto é EntradaInvalida.
        """
        if not caminho or not str(caminho).strip():
            raise EntradaInvalida("Nenhum caminho informado.")
        try:
            alvo = Path(caminho).expanduser().resolve()
        except (OSError, ValueError) as erro:
            raise EntradaInvalida(f"Caminho inválido: {caminho}") from erro

        if self._dentro_de_projeto(alvo) is None:
            raise EntradaInvalida(
                "Só é possível abrir pastas dentro de um projeto configurado. "
                f"Fora de todos eles: {caminho}")

        if not alvo.exists():
            raise EntradaInvalida(
                f"O caminho não existe mais no disco: {caminho}")

        pasta = alvo if alvo.is_dir() else alvo.parent
        self._abrir(str(pasta))
        return str(pasta)

    def config(self) -> dict:
        """Perfis, projetos e status do ffmpeg. Alimenta GET /api/config."""
        return {
            "ffmpeg": {
                "disponivel": self._ffmpeg.disponivel,
                "completo": self._ffmpeg.completo,
                "ffmpeg": self._ffmpeg.ffmpeg,
                "ffprobe": self._ffmpeg.ffprobe,
            },
            "perfis": [
                {
                    "nome": p.nome,
                    "descricao": p.descricao,
                    "disponivel": disponivel(p, self._ffmpeg.disponivel),
                    "exige_ffmpeg": p.exige_ffmpeg,
                    "limite_dimensao": p.limite_dimensao,
                    "container": p.merge_output_format,
                }
                for p in self._perfis.values()
            ],
            "projetos": [
                {
                    "nome": pj.nome,
                    "rotulo": pj.rotulo,
                    "pasta": pj.pasta,
                    "valido": self._projetos_status[pj.nome][0],
                    "motivo": self._projetos_status[pj.nome][1],
                }
                for pj in self._projetos.values()
            ],
        }

    # ------------------------------------------------------------ fim

    def encerrar(self) -> None:
        """Para o worker e fecha o histórico. Idempotente."""
        if self._encerrado:
            return
        self._encerrado = True
        self._worker.parar(timeout=5.0)
        self._historico.fechar()
