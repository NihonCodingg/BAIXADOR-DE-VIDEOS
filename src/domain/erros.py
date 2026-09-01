"""Taxonomia de falhas — regra de produto, não do yt-dlp.

O enum e as mensagens vivem aqui porque são decisões sobre o que o usuário lê
e sobre o que vale a pena tentar de novo (SPEC 5.6).

A tabela que traduz exceção do yt-dlp para este enum vive em
src/download/traducao_erros.py, porque precisa conhecer as classes do yt-dlp.
"""

from enum import Enum


class MotivoFalha(str, Enum):
    INDISPONIVEL = "indisponivel"
    PRIVADO = "privado"
    RESTRICAO_IDADE = "restricao_idade"
    BLOQUEIO_REGIONAL = "bloqueio_regional"
    DRM = "drm"
    SITE_NAO_SUPORTADO = "site_nao_suportado"
    REDE = "rede"
    RATE_LIMIT = "rate_limit"
    SEM_FFMPEG = "sem_ffmpeg"
    DISCO = "disco"
    DESCONHECIDO = "desconhecido"


# Mensagem legível por motivo. RESEARCH.md 6.4.
MENSAGENS = {
    MotivoFalha.INDISPONIVEL: "Vídeo indisponível ou removido.",
    MotivoFalha.PRIVADO: "Vídeo privado. Só o dono tem acesso.",
    MotivoFalha.RESTRICAO_IDADE: "Vídeo com restrição de idade — exige conta autenticada.",
    MotivoFalha.BLOQUEIO_REGIONAL: "Bloqueado na sua região.",
    MotivoFalha.DRM: "Conteúdo protegido por DRM. Fora do escopo desta ferramenta.",
    MotivoFalha.SITE_NAO_SUPORTADO: "Este site não é suportado pelo yt-dlp.",
    MotivoFalha.REDE: "Falha de rede.",
    MotivoFalha.RATE_LIMIT: "O site limitou a taxa de requisições. Aguarde.",
    MotivoFalha.SEM_FFMPEG: "ffmpeg não encontrado — não é possível juntar vídeo e áudio.",
    MotivoFalha.DISCO: "Falha ao gravar no disco.",
    MotivoFalha.DESCONHECIDO: "Falha não classificada.",
}

# Motivos em que repetir a tentativa faz sentido.
RETENTAVEIS = frozenset({MotivoFalha.REDE, MotivoFalha.RATE_LIMIT})


class ErroDeDominio(Exception):
    """Erro de regra de negócio. Nunca embrulha exceção de I/O."""


class LinkInvalido(ErroDeDominio):
    pass


class PerfilInvalido(ErroDeDominio):
    pass


class ProjetoInvalido(ErroDeDominio):
    pass


class TransicaoIlegal(ErroDeDominio):
    pass


class NomeImpossivel(ErroDeDominio):
    """A pasta do projeto é tão profunda que não sobra espaço nem para o custo
    fixo do nome (data + id + extensão). SPEC 8.3."""
