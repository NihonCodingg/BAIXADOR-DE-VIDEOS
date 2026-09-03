# Baixador de Footage

Aplicação local com interface web para baixar footage de vídeo destinado a
edição, construída sobre a biblioteca [yt-dlp](https://github.com/yt-dlp/yt-dlp).

Roda em `127.0.0.1`, para uso de uma pessoa só, na própria máquina. Não é um
serviço, não tem autenticação e não deve ser exposta na rede.

## Estado atual

**Interface funcionando; CLI pendente.** Domínio, adapter, histórico, fila, API e interface estão implementados. O visual foi desenhado fora do repositório a partir do `CONTRATO-API.md` e integrado no T7; a CLI é o T8.

O que existe hoje:

| Item | Estado |
|---|---|
| [RESEARCH.md](RESEARCH.md) — pesquisa técnica | pronto |
| [SPEC.md](SPEC.md) — especificação normativa | pronto |
| [PLAN.md](PLAN.md) — tickets T1 a T8 | pronto |
| `spike.py` — protótipo descartável | executado; gerou o `spike_meta.json` usado como fixture |
| Estrutura de pastas e stubs | pronta |
| Teste de arquitetura | passando (23 testes) |
| T1 — adapter do yt-dlp, tradução de erros, ffmpeg | **implementado** |
| T2 — validação de link, modelos, perfis | **implementado** |
| T3 — nomenclatura e sanitização | **implementado** |
| T4 — histórico SQLite | **implementado** |
| T5 — fila, worker e progresso | **implementado** |
| T6 — pipeline, API e `CONTRATO-API.md` | **implementado** |
| T7 — integração do front, validada no navegador | **implementado** |
| Smoke test com download real | **passou**: 1080x1920 H.264 + AAC |
| T8 — CLI | pendente |

A CLI ainda levanta `NotImplementedError` com o ticket que a implementa; o
resto das instruções de execução abaixo descreve o que funciona hoje.

Suíte atual: **589 testes**. Rodar:

```bash
python -m pytest tests/ -v
```

## O problema

Sou editor de vídeo de conteúdo gaming/esports. Trabalho com footage vindo de
várias fontes e, na prática, baixar o arquivo é a parte fácil — o yt-dlp resolve
isso em uma linha de comando.

O que consome tempo é tudo em volta:

- lembrar a sintaxe do seletor de formato do yt-dlp para conseguir um arquivo
  que abra bem na timeline (H.264 em MP4, e não VP9 em WebM);
- salvar na pasta certa do cliente certo, com um nome que eu consiga achar
  daqui a seis meses;
- não baixar de novo o que eu já baixei;
- saber onde cada arquivo foi parar.

Esta ferramenta existe para resolver essa camada. **O valor não está no
download.**

## O que ela faz além do yt-dlp

- **Perfis de qualidade nomeados**, definidos em YAML e voltados para edição:
  `edicao_1080`, `edicao_4k`, `so_audio`, `preview_leve`. Cada perfil carrega um
  seletor de formato, uma ordem de preferência de codec e um container de saída.
  A justificativa técnica de cada um está na Seção 2.2 do
  [RESEARCH.md](RESEARCH.md).
- **Organização automática** em pastas por projeto/cliente.
- **Nomenclatura consistente e sanitizada para Windows.** Não é um wrapper do
  `sanitize_filename` do yt-dlp: ele não trata nomes reservados do DOS, não
  trunca por tamanho, não trata título vazio e substitui caracteres proibidos
  por homóglifos Unicode de largura total, que quebram busca por nome. A Seção 7
  do RESEARCH documenta as medições.
- **Fila com progresso ao vivo**, um download por vez.
- **Histórico persistente**: avisa se o vídeo já foi baixado naquele perfil e diz
  onde o arquivo está.
- **Relatório de falha legível**, em português, com o motivo real — vídeo
  privado, bloqueio regional, restrição de idade, falha de rede — em vez de
  stack trace.

## Escopo de uso

A ferramenta é para baixar:

- conteúdo próprio;
- conteúdo licenciado;
- conteúdo sob Creative Commons;
- material de cliente que autorizou o uso.

### Fora de escopo, em definitivo

Estes itens não serão implementados. Pedidos nesse sentido em sessões futuras
devem ser recusados com referência a esta seção e ao SPEC:

- qualquer contorno de DRM, paywall ou proteção de conteúdo pago;
- download em massa de canais inteiros;
- upload, redistribuição ou publicação de qualquer coisa;
- multiusuário, autenticação ou deploy em servidor.

Sobre DRM, a distinção é importante: a ferramenta **detecta** conteúdo protegido
para dar uma mensagem de erro honesta e parar. Ela não faz, e não fará, nada
para contornar a proteção.

## Stack

| Camada | Escolha | Motivo |
|---|---|---|
| Linguagem | Python 3.14 | — |
| Download | `yt-dlp` como **biblioteca** (`import yt_dlp`) | Nunca via `subprocess`. Chamar o executável obrigaria a parsear stdout, que o próprio projeto avisa não ser estável. |
| Back-end web | FastAPI | Só orquestração e JSON; nenhuma regra de negócio. |
| Persistência | SQLite (`sqlite3`, biblioteca padrão) | Histórico de um usuário local. Não justifica um servidor de banco. |
| Configuração | YAML (`PyYAML`) | Perfis e projetos são editados à mão. |
| Front-end | HTML/CSS/JS puro | Sem framework, sem etapa de build. O visual é desenhado no Claude Design a partir do `CONTRATO-API.md`; este repositório integra. |
| Testes | `pytest` | Nenhum teste toca a rede. |
| Externo | `ffmpeg` + `ffprobe` | Dependência de sistema, não do Python. |

### Sobre o ffmpeg

O ffmpeg **não** é instalado pelo `pip` — é um binário externo que precisa estar
no `PATH`. Ele é obrigatório para todo perfil de edição, porque sites modernos
servem vídeo e áudio como streams separados e juntá-los é trabalho do ffmpeg.

Sem ele, o operador `+` do seletor de formato não funciona e o download fica
limitado aos formatos pré-combinados, tipicamente 720p ou menos. Como o sintoma
é "pedi 1080p e veio 720p", que é difícil de diagnosticar, a aplicação verifica
o ffmpeg na inicialização e mostra um aviso claro na interface — nunca um stack
trace.

No Windows, a instalação mais direta é:

```bash
winget install Gyan.FFmpeg
```

## Como rodar

> A interface já sobe e funciona; a CLI (T8) não existe. Antes de rodar,
> ajuste `config/projetos.yaml` para as suas pastas.

Requisitos: Python 3.12+ e `ffmpeg` no `PATH`.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Interface web:

```bash
python -m src.web
```

O navegador abre sozinho em `http://127.0.0.1:8000`.

Linha de comando (T8, ainda não implementada):

```bash
python -m src.cli --perfil edicao_1080 --projeto cliente_x URL
```

A CLI e a interface web usam o mesmo `pipeline.py`. A CLI aceita `--dry-run`
para mostrar o que seria baixado e onde, sem baixar nada.

## Organização do código

A separação é a regra estrutural do projeto, e existe para evitar que tudo vire
um wrapper fino do yt-dlp:

```
src/download/    único lugar que conhece o yt-dlp (adapter)
src/domain/      puro: models, perfis, nomenclatura, validação
src/storage/     SQLite: histórico
src/queue/       fila de trabalhos + worker em background
src/pipeline.py  orquestração, usada pela CLI e pela web
src/cli.py       linha de comando
src/web/         FastAPI, só orquestração
web/             index.html, style.css, app.js
config/          perfis.yaml, projetos.yaml
tests/
```

Duas regras invariantes, garantidas por um teste de arquitetura:

1. `src/domain/` nunca importa de `src/download/`, `src/storage/` ou `src/queue/`.
2. `src/web/` nunca importa de `src/domain/` — fala com `src/pipeline.py`.

O domínio não faz rede, não toca disco e não conhece o yt-dlp.

## Documentação

- [RESEARCH.md](RESEARCH.md) — pesquisa técnica: API do yt-dlp, seleção de
  formato, modelo de threads dos progress hooks, postprocessors, detecção de
  ffmpeg, mapeamento de exceções e limites de nome de arquivo no Windows.
- [CONTRATO-API.md](CONTRATO-API.md) — a API que a interface consome, com exemplos
  gerados por execução real. É a entrada do desenho da interface.
- [CLAUDE.md](CLAUDE.md) — convenções de trabalho no repositório.
