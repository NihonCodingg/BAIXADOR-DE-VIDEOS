# PLAN.md — Tickets

Fatias verticais de 80 a 150 linhas cada. **Um ticket por sessão**, com `/clear`
entre elas.

Referências: [SPEC.md](SPEC.md) é normativo, [RESEARCH.md](RESEARCH.md) é a base
factual. Convenções em [CLAUDE.md](CLAUDE.md).

## Ordem e dependências

```
T1 (adapter)  ──┐
T2 (domínio)  ──┼──> T5 (fila) ──> T6 (API) ──> T7 (front)
T3 (nomes)    ──┤                        │
T4 (histórico)──┘                        └──> T8 (CLI)
```

T1 a T4 são independentes entre si e podem ser feitos em qualquer ordem.
Sugestão: **T2 primeiro** — é o que ancora os modelos que todos os outros usam.

| Ticket | Assunto | Esforço | TDD com confirmação? | Estado |
|---|---|---|---|---|
| T1 | Adapter do yt-dlp | medium | não | pendente |
| T2 | Domínio: validação, modelos, perfis | high | **sim** | pendente |
| T3 | Domínio: nomenclatura e caminho | high | **sim** | ✔ concluído |
| T4 | Histórico SQLite | medium | não | pendente |
| T5 | Fila e worker | high | **sim** | pendente |
| T6 | Back-end web | medium | não | pendente |
| T7 | Front-end | high | não | pendente |
| T8 | CLI | low | não | pendente |

> Nos tickets marcados: escrever os testes **antes**, mostrar a lista de casos
> de borda e **esperar confirmação** antes de implementar.

---

# T1 — Adapter do yt-dlp

**Esforço: medium**

## Objetivo

Baixar um vídeo através da biblioteca, com progress hook, e traduzir as exceções
do yt-dlp para motivos legíveis em português.

## Arquivos

- `src/download/adapter.py`
- `src/download/ffmpeg.py`
- `src/download/traducao_erros.py`
- `tests/test_traducao_erros.py` (novo)
- `tests/test_ffmpeg.py` (novo)

## O que fazer

1. `ffmpeg.detectar()` com `shutil.which`, para ffmpeg **e** ffprobe. Chamada
   uma vez, na inicialização — não por job.
2. `Downloader.inspecionar(url)`: `extract_info(download=False)` seguido de
   `sanitize_info`. Sem `sanitize_info` o resultado não é serializável em JSON
   (RESEARCH §1.3).
3. `Downloader.baixar(url, opcoes, ao_progredir)`: registra o callback em
   `progress_hooks` e devolve o caminho final, lido de
   `info["requested_downloads"][0]["filepath"]`.
4. `traducao_erros.desembrulhar(err)`: extrai a exceção real de
   `DownloadError.exc_info[1]`. **É o coração do ticket** — classificar olhando
   só o `DownloadError` transforma tudo em "erro genérico" (RESEARCH §6.2).
5. `traducao_erros.classificar(err)`: primeiro por **tipo**
   (`GeoRestrictedError`, `UnsupportedError`, `HTTPError`, `TransportError`),
   depois por **substring** na `TABELA_MENSAGENS`, e por fim o fallback
   `DESCONHECIDO` — que devolve a mensagem original, nunca "erro desconhecido".

## Testes (sem rede)

Construir instâncias de exceção do yt-dlp à mão e verificar a classificação:

- `DownloadError` embrulhando `GeoRestrictedError` → `BLOQUEIO_REGIONAL`, e a
  lista de países preservada
- `DownloadError` embrulhando `ExtractorError("Private video")` → `PRIVADO`
- `"This video is DRM protected"` → `DRM`
- `HTTPError` com status 404 → `REDE`
- exceção não reconhecida → `DESCONHECIDO` **com a mensagem original intacta**
- `DownloadError` sem `exc_info` → não estoura

## Critério de pronto

- `detectar()` devolve caminhos reais na máquina de destino
- Toda exceção mapeada em RESEARCH §6.4 tem teste
- O fallback preserva a mensagem original — testado explicitamente
- Suíte inteira passando

## Fora do escopo deste ticket

Fila, retry, histórico, montagem de opções a partir de perfil (é T2), criação de
diretório de destino (é T3).

---

# T2 — Domínio: validação, modelos e perfis

**Esforço: high — TDD com confirmação**

## Objetivo

Validação e normalização de link, dataclasses `Video` e `Job`, resolução de
perfil YAML para seletor de formato. Tudo puro.

## Arquivos

- `src/domain/validacao.py`
- `src/domain/models.py`
- `src/domain/perfis.py`
- `tests/test_validacao.py`, `tests/test_models.py`, `tests/test_perfis.py` (novos)

## Casos de borda para confirmar ANTES de implementar

**Normalização de link:**

- `youtu.be/ID`, `youtube.com/watch?v=ID`, `youtube.com/watch?v=ID&t=42`,
  `m.youtube.com`, `youtube.com/shorts/ID` → todos o mesmo canônico
- `youtube.com/embed/ID`
- URL com `&list=` → normaliza para o vídeo, descarta a playlist
- `youtube.com/@canal`, `/playlist?list=`, `/c/nome`, `/channel/UC...` →
  **rejeitar**, download em massa está fora de escopo
- string vazia, espaços, texto que não é URL → `LinkInvalido`
- `http` vs `https`
- lote com duplicatas em formatos diferentes (`youtu.be/X` e `watch?v=X`) →
  deduplica para um

**Perfis:**

- perfil inexistente → `PerfilInvalido`
- `format` ausente ou vazio → erro
- `format` contendo `,` → erro (quebra um-arquivo-por-job, SPEC 6.2)
- `merge_output_format` fora da lista conhecida → erro
- `key` de postprocessor inexistente → erro **na carga**, não em runtime
- `exige_ffmpeg: true` sem ffmpeg → perfil marcado indisponível, não exceção

**Máquina de estados** (SPEC 10.2):

- toda transição legal funciona
- `na_fila` → `concluido` direto → `TransicaoIlegal`
- sair de qualquer estado terminal → `TransicaoIlegal`
- `baixando` → `cancelado` → `TransicaoIlegal` (só cancela antes de começar)

**`Video.de_info_dict`:**

- info_dict real do `spike_meta.json`
- campos ausentes (`duration`, `thumbnail`, `channel`) → `None`, sem `KeyError`
- `formats` vazio

## Critério de pronto

- Testes escritos primeiro, lista confirmada pelo autor
- `carregar_perfis` valida os 4 perfis reais do `config/perfis.yaml`
- Nenhum import proibido (o teste de arquitetura garante)
- Suíte passando

## Fora do escopo

Nomenclatura de arquivo (T3), leitura do YAML do disco — as funções recebem
dict já carregado, porque o domínio não toca disco.

---

# T3 — Domínio: nomenclatura, caminho e colisão

**Esforço: high — TDD com confirmação — ✔ CONCLUÍDO**

> **A lista abaixo é histórica.** A lista confirmada e implementada está em
> `tests/test_nomes.py` (95 testes). Quatro pontos mudaram durante a revisão:
>
> - substituição dos proibidos passou a ser **por caractere**, não regra única
>   (`\|` → `" - "`, `/` → `-`, `:` → espaço, o resto removido)
> - o fallback é **`video`**, não `video_{id}` — o `[{id}]` já dá unicidade
> - "título de 300 chars" saiu (o YouTube limita a 100) e virou "100 chars +
>   pasta profunda", que é o cenário que de fato estoura
> - orçamento passou a ser de **caminho completo (240)**, não de nome, com 5
>   caracteres reservados para o sufixo de colisão
>
> Acrescentados na revisão: colisão case-insensitive, normalização NFC, e
> truncamento que não deixa ponto nem espaço no fim.

## Objetivo

Gerar um nome de arquivo que sobreviva ao Windows **e** seja utilizável por um
editor de vídeo. Montar o caminho por projeto e resolver colisão.

Este é o ticket que justifica a camada de domínio existir (SPEC §5.1).

## Arquivos

- `src/domain/nomes.py`
- `tests/test_nomes.py` (novo)

## Casos de borda para confirmar ANTES de implementar

**Caracteres proibidos:**

- título com todos os nove: `< > : " / \ | ? *`
- caracteres de controle (0–31, 127)
- **verificar que a saída NÃO contém homóglifos de largura total** — é
  exatamente o que o yt-dlp faz e o que estamos evitando (RESEARCH §7.4)

**Nomes reservados** (o achado crítico, RESEARCH §7.3):

- `CON`, `PRN`, `AUX`, `NUL` puros
- `COM1` a `COM9`, `LPT1` a `LPT9`
- **com extensão**: `NUL.mp4` — a Microsoft documenta `NUL.txt` ≡ `NUL`
- case-insensitive: `con`, `Con`, `nUl`
- superscripts: `COM¹`, `LPT²`
- **não** reservado: `CONS`, `CONTRA`, `NULO` — não podem ser mutilados

**Tamanho:**

- título com 300 caracteres
- título longo + pasta de projeto profunda → o orçamento conta o **caminho
  completo**, não só o nome
- truncamento preserva a extensão
- truncamento preserva o `[video_id]` — é a chave de reconciliação
- pasta de projeto tão profunda que não sobra espaço → erro claro, não nome
  vazio

**Degenerados:**

- título vazio `''` → `video_{id}`
- só espaços `'   '`
- só pontos `'...'`
- só emoji `'🎮🔥💀'`
- terminando em ponto: `'Final da season.'`
- terminando em espaço
- começando com ponto (legal no Windows, não mutilar)

**Colisão:**

- caminho livre → inalterado
- existe → `nome (2).mp4`
- existem `(2)` e `(3)` → `nome (4).mp4`
- sufixo entra **antes** da extensão
- o `existe` é injetado como callable — o domínio não toca disco

## Critério de pronto

- Testes escritos primeiro, lista confirmada
- Nenhum nome gerado casa com a lista de reservados
- Nenhum caminho gerado ultrapassa o orçamento
- Suíte passando

## Fora do escopo

Criar diretório, checar permissão de escrita, mover arquivo. Tudo isso é I/O.

---

# T4 — Histórico SQLite

**Esforço: medium**

## Objetivo

Persistir o histórico com chave `(extractor, video_id, perfil)`, guardando
caminho, status, tamanho e data.

## Arquivos

- `src/storage/historico.py`
- `src/storage/schema.sql` (já escrito)
- `tests/test_historico.py` (novo)

## O que fazer

1. `criar_schema()` executa o `.sql`. Idempotente.
2. `ja_baixado(extractor, video_id, perfil)` — alimenta o aviso de duplicata.
3. `registrar(registro)`.
4. `buscar(termo, projeto, limite)` — busca por título, filtro por projeto.
5. `marcar_interrompidos()` na subida: todo registro não-terminal vira
   `interrompido`. É o que impede um job morto de ser lido como concluído.

## Testes (SQLite em memória ou `tmp_path`)

- schema criado duas vezes não quebra
- mesmo vídeo em perfis diferentes → **dois registros** (é requisito)
- mesmo vídeo, mesmo perfil, duas vezes → viola `UNIQUE`, e o comportamento é
  definido (upsert ou erro — decidir e testar)
- `video_id` igual em extractors diferentes → dois registros
- `ja_baixado` de algo nunca baixado → `None`
- busca por termo parcial e case-insensitive
- `marcar_interrompidos` mexe só nos não-terminais; devolve a contagem
- datas gravadas em ISO-8601 e ordenam corretamente como texto

## Critério de pronto

- Nenhum teste toca disco fora de `tmp_path`
- Chave única testada nas quatro combinações
- Suíte passando

## Fora do escopo

Fila, migração de schema, limpeza de registros antigos.

---

# T5 — Fila e worker

**Esforço: high — TDD com confirmação**

## Objetivo

A peça central: fila com uma thread de trabalho, um download por vez, progresso
thread-safe, estado consultável e cancelamento.

## Arquivos

- `src/queue/fila.py`
- `src/queue/worker.py`
- `tests/test_fila.py`, `tests/test_worker.py` (novos)

## O ponto crítico

O progress hook **pode ser chamado de outra thread**, sem configuração especial:
o caminho DASH multi-formato do yt-dlp usa `ThreadPoolExecutor`
(RESEARCH §3.4, caso 4). O lock não é precaução, é requisito.

O hook adquire o lock só para **substituir** o objeto `Progresso`. Nunca muta
campo a campo, nunca faz I/O.

## Casos de borda para confirmar ANTES de implementar

**Fila:**

- adicionar e retirar preserva ordem FIFO
- `proximo()` com fila vazia → `None`
- `proximo()` descarta jobs já cancelados
- `instantaneo()` devolve cópia — mutar o resultado não afeta o estado interno

**Estados:**

- ciclo feliz: `na_fila` → `baixando` → `concluido`
- falha: `na_fila` → `baixando` → `falhou`, com motivo e mensagem preenchidos
- transição ilegal → `TransicaoIlegal`

**Cancelamento:**

- job em `na_fila` → cancela, worker o descarta
- job em `baixando` → **recusa**, devolve `False` (a API traduz em 409)
- job já terminal → recusa

**Concorrência (o núcleo):**

- progresso atualizado de outra thread não corrompe o estado — usar
  `threading.Thread` real no teste, não simulação
- N threads escrevendo progresso + leituras concorrentes de `instantaneo()` →
  nenhum estado inconsistente, nenhuma exceção
- hook chamado depois do job terminar → ignorado, não ressuscita

**Interrupção:**

- `parar()` com job em `baixando` → o job vira `interrompido`, **nunca**
  `concluido`
- `parar()` com fila vazia → retorna limpo, sem travar

**Serialização:**

- dois jobs enfileirados → o segundo só começa depois do primeiro terminar.
  Verificar com timestamps registrados pelo `DownloaderFalso`.

## Critério de pronto

- Testes escritos primeiro, lista confirmada
- **Nenhum teste toca a rede** — tudo com `DownloaderFalso`
- Teste de concorrência com threads reais
- Nenhum teste depende de `sleep` para passar (evitar flake)
- Suíte passando

## Fora do escopo

HTTP, persistência da fila entre execuções (a fila é em memória por decisão,
SPEC 10.1), cancelar download em andamento.

---

# T6 — Back-end web

**Esforço: medium**

## Objetivo

FastAPI, só JSON, zero regra de negócio. Seis rotas.

## Arquivos

- `src/web/app.py`
- `src/pipeline.py`
- `tests/test_api.py` (novo)

## Rotas (SPEC 11)

| Método | Rota |
|---|---|
| POST | `/api/inspecionar` |
| POST | `/api/fila` |
| GET | `/api/fila` |
| DELETE | `/api/fila/{id}` |
| GET | `/api/historico` |
| GET | `/api/config` |

## O que fazer

1. `Pipeline` monta domínio, download, storage e queue.
2. As rotas só validam corpo e delegam. **Nenhum `if` de regra de negócio.**
3. `/api/inspecionar` devolve **200 com resultado parcial**: cada item traz seu
   `ok`. Um link ruim numa lista de dez não invalida os outros nove.
4. Servir `web/` como estático.
5. Vincular em `127.0.0.1`.

## Testes (`TestClient`, sem servidor, sem rede)

- cada rota com corpo válido
- link inválido → 400
- perfil ou projeto inexistente → 400
- cancelar job inexistente → 404
- cancelar job em `baixando` → 409
- corpo malformado → 422
- `/api/inspecionar` com lista mista → 200, itens `ok` e não-`ok`
- `/api/config` reflete ffmpeg ausente

## Critério de pronto

- `src/web/` não importa `src/domain/` — o teste de arquitetura garante
- Todas as rotas testadas, incluindo os códigos de erro
- Suíte passando

## Fora do escopo

Front-end, autenticação (fora de escopo do produto), WebSocket.

---

# T7 — Front-end

**Esforço: high**

## Objetivo

HTML/CSS/JS puro. Sem framework, sem build.

## Arquivos

- `web/index.html`, `web/style.css`, `web/app.js`

## O que fazer

1. Campo de colar links, vários, um por linha
2. Cartão de preview por vídeo: thumbnail, título, canal, duração, seletor de
   perfil, seletor de projeto
3. Fila com barra de progresso, velocidade e tempo restante — **polling de 1 s**
4. Botão de cancelar por item, desabilitado quando o job já começou
5. Histórico com busca e botão "abrir pasta"
6. Aviso no topo se o ffmpeg faltar
7. Variáveis CSS no topo do `style.css` (já esboçadas)
8. Código comentado, sem minificação

## Cuidados

- A thumbnail vem do CDN do site pela URL do metadado. O backend não a baixa
  (RESEARCH §8). `thumbnail` pode ser `None` → placeholder.
- `speed` e `eta` podem ser `None` → mostrar `--`, não `NaN` nem `undefined`.
- Polling precisa parar de acumular se uma resposta demorar mais que o intervalo.
- Duplicata já no histórico: avisar antes de enfileirar.

## Critério de pronto

- Fluxo completo funciona no navegador: colar, inspecionar, enfileirar,
  acompanhar, consultar histórico
- Nenhum erro no console
- Aviso de ffmpeg aparece quando ausente

## Fora do escopo

Framework, bundler, testes de browser automatizados, responsividade para celular
(é ferramenta de desktop).

---

# T8 — CLI

**Esforço: low**

## Objetivo

Uso rápido sem abrir o navegador, pelo **mesmo** `pipeline.py`.

## Arquivos

- `src/cli.py`
- `tests/test_cli.py` (novo)

## O que fazer

```bash
python -m src.cli --perfil edicao_1080 --projeto cliente_x URL [URL...]
python -m src.cli --dry-run --perfil edicao_1080 --projeto cliente_x URL
python -m src.cli --listar-perfis
```

- `--dry-run` mostra o que seria baixado e **para onde**, sem baixar. É o modo
  de conferir a nomenclatura antes de comprometer disco.
- `sys.stdout.reconfigure(encoding="utf-8")` no topo — sem isso, imprimir título
  de vídeo quebra no console do Windows (RESEARCH §7.4).
- Código de saída: 0 sucesso, 1 falha.

## Testes

- parsing de argumentos
- `--dry-run` não chama o downloader — verificado pelo `DownloaderFalso`
- perfil inexistente → mensagem clara e código 1
- título com caractere problemático não quebra a impressão

## Critério de pronto

- CLI e web produzem o mesmo resultado para a mesma entrada
- `--dry-run` comprovadamente não toca a rede
- Suíte inteira passando

## Fora do escopo

Autocompletar, barra de progresso elaborada, modo interativo.

---

# Pendências antes de começar

1. ~~`spike_meta.json` não existe~~ — **resolvido**: capturado e versionado.
2. ~~Orçamento de caminho~~ — **decidido**: 240 do caminho completo (SPEC §8.3).
