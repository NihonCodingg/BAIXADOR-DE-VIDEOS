# PLAN.md — Tickets

Fatias verticais de 80 a 150 linhas cada. **Um ticket por sessão**, com `/clear`
entre elas.

Referências: [SPEC.md](SPEC.md) é normativo, [RESEARCH.md](RESEARCH.md) é a base
factual. Convenções em [CLAUDE.md](CLAUDE.md).

## Ordem e dependências

```
T1 (adapter)  ──┐
T2 (domínio)  ──┼──> T5 (fila) ──> T6 (API) ──┬──> CONTRATO-API.md
T3 (nomes)    ──┤                             │         │
T4 (histórico)──┘                             │         v
                                              │   [Claude Design]
                                              │         │
                                              │         v
                                              │      T7 (integração)
                                              └──> T8 (CLI)
```

O T6 produz o `CONTRATO-API.md`, que é a **entrada do Claude Design**. A
interface visual é feita lá, fora deste repositório; o T7 só integra e corrige.

T1 a T4 são independentes entre si e podem ser feitos em qualquer ordem.
Sugestão: **T2 primeiro** — é o que ancora os modelos que todos os outros usam.

| Ticket | Assunto | Esforço | TDD com confirmação? | Estado |
|---|---|---|---|---|
| T1 | Adapter do yt-dlp | medium | não | ✔ concluído |
| T2 | Domínio: validação, modelos, perfis | high | **sim** | ✔ concluído |
| T3 | Domínio: nomenclatura e caminho | high | **sim** | ✔ concluído |
| T4 | Histórico SQLite | medium | não | ✔ concluído |
| T5 | Fila e worker | high | **sim** | ✔ concluído |
| T6 | Back-end web | medium | não | ✔ concluído |
| T7 | Integração do front-end | medium | não | pendente |
| T8 | CLI | low | não | pendente |

> Nos tickets marcados: escrever os testes **antes**, mostrar a lista de casos
> de borda e **esperar confirmação** antes de implementar.

---

# T1 — Adapter do yt-dlp

**Esforço: medium — ✔ CONCLUÍDO**

> **Concluído com quatro desvios do plano abaixo**, todos registrados nos
> testes (`tests/test_adapter.py`, `tests/test_traducao_erros.py`,
> `tests/test_ffmpeg.py`):
>
> - `classificar` devolve `Classificacao` (motivo, mensagem original,
>   detalhes) em vez de tupla — precisava carregar países e status HTTP
> - `ExtractorError` com **`cause` de rede** ("Unable to download webpage") é
>   `REDE`, não `DESCONHECIDO`; era o caso retentável mais comum
> - o adapter **escapa `%` no `outtmpl`**: medido que `%(` num caminho
>   literal vira `NA` no yt-dlp
> - **`overwrites=False` sempre**: footage nunca é sobrescrito (SPEC 8.4)
>
> Incidente encontrado no caminho: `src/download/` estava **ignorado pelo
> `.gitignore`** (padrão `download/` sem barra inicial) e nunca tinha chegado
> ao remoto. Corrigido, e o teste de arquitetura agora falha se qualquer
> pacote de `src/` sumir.

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

**Esforço: high — TDD com confirmação — ✔ CONCLUÍDO**

> **A lista abaixo é histórica.** A lista confirmada e implementada está em
> `tests/test_validacao.py`, `tests/test_models.py` e `tests/test_perfis.py`.
> O que mudou durante a revisão, com dados do fixture real:
>
> - **teto de qualidade na menor dimensão** (SPEC §6.3): `[height<=1080]`
>   entregava 480x854 num Short; o perfil virou template `{dim}` resolvido
>   por `campo_limite()` — a gramática do yt-dlp não tem OR
> - **`?si=` do botão compartilhar** era o caso mais provável de todos e não
>   estava na lista — estava no `original_url` do fixture
> - **`acodec` está AUSENTE** em 2 dos 45 formatos (não presente com `None`):
>   o risco é `KeyError`, e a classificação precisa de três estados
> - **storyboards** (`ext=mhtml`) saem na conversão, não na exibição
> - normalização conhece **só o YouTube**; outros sites passam com aviso
>   dentro do resultado (`LinkNormalizado.aviso`), nunca por print/log
> - ID nu é rejeitado; mesmo→mesmo estado é ilegal; carga de perfis é
>   tudo-ou-nada; nenhuma função deixa objeto em estado parcial ao levantar

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

**Esforço: medium — ✔ CONCLUÍDO**

> **Concluído.** 47 testes em `tests/test_historico.py`. O que a
> implementação decidiu além do plano:
>
> - status **`baixando`** gravado no início (`iniciar`), sem o que a
>   reconciliação de SPEC §10.1 não teria o que marcar — SPEC §9.2 corrigido
> - **upsert**: uma linha por chave, a última tentativa; rebaixar depois de
>   falha não viola o UNIQUE e começa limpo
> - `ja_baixado` devolve só `concluido`; `obter` devolve qualquer status
> - busca **normalizada** (minúsculas, sem acento): `selecao` acha `Seleção`;
>   `%` e `_` no termo não viram curinga
> - coluna **`resolucao`** com a resolução realmente baixada, para expor
>   quando o seletor caiu num fallback
> - uma conexão com `RLock`; o worker grava enquanto a web lê

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

**Esforço: high — TDD com confirmação — ✔ CONCLUÍDO**

> **Concluído** (casos de borda por conta do implementador, no modo de
> autonomia vigente). 73 testes em `tests/test_fila.py`, `tests/test_worker.py`
> e `tests/test_progresso.py`. O que a implementação decidiu além da lista:
>
> - `proximo()` já devolve o job em **BAIXANDO**, sob o mesmo lock do dequeue,
>   para `cancelar()` não entrar na fresta entre retirar e começar
> - **`AgregadorProgresso`** soma por `format_id`: no DASH multi-formato vídeo e
>   áudio chegam de threads diferentes com bytes próprios (RESEARCH §3.4)
> - a **resolução real** do `finished` do formato mesclado vai para o histórico
> - opções e destino vêm de um **`preparar` injetado** (o pipeline resolve
>   perfil, nome e pasta); o worker não conhece regra de negócio
> - falha do histórico ao iniciar é falha do job, sem download: um arquivo sem
>   linha no histórico contradiz "sei onde cada arquivo está"
> - conclusão tardia depois de `parar()` não ressuscita o job
> - tudo que sai da fila é **cópia**; nenhum hook pode levantar

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

**Esforço: medium — ✔ CONCLUÍDO**

> **Concluído em duas rodadas TDD**: pipeline (`tests/test_pipeline.py`,
> `tests/test_projetos.py`) e camada web (`tests/test_api.py`). Entregável
> extra: `CONTRATO-API.md`, com exemplos gerados por execução real via
> `scripts/gerar_exemplos_contrato.py`. Decisões além do plano:
>
> - respostas embrulhadas: `{"itens"}`, `{"ids"}`, `{"jobs"}`, `{"registros"}`
>   — e **uma forma só de erro**, `{"erro": ...}`, inclusive no 422 e no 500
> - `inspecionar` expõe `qualidades` pela menor dimensão e `baixados` por
>   perfil; `enfileirar` é tudo-ou-nada e recusa duplicata (409) salvo `forcar`
> - a colisão de nome é resolvida na hora de **baixar**, não de enfileirar
> - o worker recebe `preparar` injetado do pipeline; a web nunca vê o domínio
> - "abrir pasta" exige um endpoint que **não existe ainda** (CONTRATO §8)

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

## Entregável extra: CONTRATO-API.md

Ao concluir o T6, produzir `CONTRATO-API.md` na raiz. **Ele é a entrada do
Claude Design**, que vai desenhar a interface sem conhecer o projeto — então
escreva para quem chega de fora.

Conteúdo obrigatório:

1. Cada endpoint: método, caminho, parâmetros e forma da resposta
2. **Um exemplo de resposta REAL de cada endpoint**, gerado a partir do
   `spike_meta.json`. Nada inventado — rodar o código e colar a saída
3. Os campos que exigem formatação na interface, com o motivo:
   - `duracao_s` vem em **segundos** (`65`), não formatado
   - `fps` é **fracionário** (`59.94`), truncar mostra `59`
   - `tamanho_bytes` vem em **bytes**
   - `thumbnail` **pode ser `null`** → precisa de placeholder
   - `speed` e `eta` **podem ser `null`** durante o download
4. Os seis estados de um job e o que a tela deve mostrar em cada:
   `na_fila`, `baixando`, `concluido`, `falhou`, `cancelado`, `interrompido`
5. O aviso de **site não-YouTube**: onde aparece na resposta
   (`aviso` do item de `/api/inspecionar`) e por que existe (SPEC 5.3)

## Critério de pronto

- `src/web/` não importa `src/domain/` — o teste de arquitetura garante
- Todas as rotas testadas, incluindo os códigos de erro
- `CONTRATO-API.md` escrito, com exemplos gerados de execução real
- Suíte passando

## Fora do escopo

Desenho da interface (é do Claude Design), autenticação (fora de escopo do
produto), WebSocket.

---

# T7 — Integração do front-end

**Esforço: medium**

> **Mudança de escopo.** A interface visual **não é implementada aqui**. Ela é
> feita no Claude Design a partir do `CONTRATO-API.md` produzido ao final do T6.
> O papel deste ticket é **integrar e corrigir**, não desenhar.

## Objetivo

Integrar o HTML/CSS/JS trazido pelo autor e garantir que ele funciona contra a
API real.

## Arquivos

- `web/index.html`, `web/style.css`, `web/app.js` (recebidos, não criados)

## O que fazer

1. Integrar os arquivos ao servidor estático do T6
2. Garantir que o **polling de 1 s** funciona e não acumula requisições quando
   uma resposta demora mais que o intervalo
3. Garantir que os seis estados de job (`na_fila`, `baixando`, `concluido`,
   `falhou`, `cancelado`, `interrompido`) são tratados na tela
4. Garantir o tratamento de erro: 400, 404, 409 e 422 precisam virar mensagem
   legível, não silêncio nem `[object Object]`
5. **Corrigir o que não bater com o contrato real** — campo com outro nome,
   tipo diferente, campo opcional tratado como obrigatório

## Cuidados

Os mesmos pontos que o `CONTRATO-API.md` documenta, verificados contra o
comportamento real:

- `thumbnail` pode ser `None` → placeholder, nunca imagem quebrada
- `speed` e `eta` podem ser `None` → `--`, nunca `NaN` nem `undefined`
- `fps` é fracionário (`59.94`) → formatar, não truncar
- `duracao_s` vem em segundos → formatar como `m:ss`
- Aviso de site não-YouTube precisa aparecer no cartão, não sumir
- Duplicata já no histórico: avisar antes de enfileirar

## Critério de pronto

- Fluxo completo funciona no navegador: colar, inspecionar, enfileirar,
  acompanhar, consultar histórico
- Nenhum erro no console
- Aviso de ffmpeg aparece quando ausente
- Todo campo opcional do contrato foi exercitado com valor ausente

## Fora do escopo

**Desenhar a interface.** Escolha de cores, tipografia, layout e hierarquia
visual são do Claude Design. Aqui só se mexe no visual para corrigir defeito
funcional.

Também fora: framework, bundler, testes de browser automatizados,
responsividade para celular (é ferramenta de desktop).

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
