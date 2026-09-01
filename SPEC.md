# SPEC.md — Baixador de Footage

Especificação funcional e técnica. Documento normativo: quando o código e o
SPEC discordarem, um dos dois está errado e a discussão começa aqui.

Base factual: [RESEARCH.md](RESEARCH.md). Onde este documento afirma algo sobre
o comportamento do yt-dlp, a evidência está lá.

---

## 1. Produto

### 1.1 O que é

Aplicação local com interface web para baixar footage de vídeo destinado a
edição, construída sobre o yt-dlp usado como **biblioteca Python**.

Usuário: uma pessoa, na própria máquina, sozinha. Não é serviço, não tem
autenticação, não é exposto na rede.

### 1.2 O problema, declarado com precisão

O yt-dlp já baixa vídeo. O download não é o produto.

O que custa tempo é a camada em volta: traduzir "quero 1080p que abra bem no
Premiere" para um seletor de formato; salvar na pasta do cliente certo; nomear
de um jeito que ainda faça sentido em seis meses; não rebaixar o que já foi
baixado; e saber onde cada arquivo foi parar.

**Critério de corte:** se uma funcionalidade é resolvida por uma opção do yt-dlp
sem nenhuma lógica própria, ela não é o produto. Ela pode existir como
conveniência, mas não justifica código no domínio.

### 1.3 Fluxo de uso

1. Abrir a ferramenta no navegador
2. Colar um ou vários links
3. A tela mostra na hora: thumbnail, título, canal, duração e qualidades
   disponíveis — **sem baixar nada**
4. Escolher perfil de qualidade e projeto de destino
5. Mandar para a fila
6. Acompanhar o progresso enquanto continua trabalhando
7. Consultar o histórico depois e saber onde cada arquivo está

### 1.4 Fronteiras

| | |
|---|---|
| **Entrada** | link(s) + perfil + projeto |
| **Saída** | arquivo no disco + registro no histórico |

---

## 2. Escopo

### 2.1 Escopo de uso declarado

A ferramenta destina-se a baixar conteúdo próprio, licenciado, sob Creative
Commons, e material de cliente que autorizou o uso.

### 2.2 Fora de escopo, em definitivo

Os itens abaixo **não serão implementados**. Pedidos nesse sentido, em qualquer
sessão futura, devem ser recusados com referência a esta seção.

| Item | Observação |
|---|---|
| Contorno de DRM, paywall ou proteção de conteúdo pago | Ver 2.3 |
| Download em massa de canais inteiros | A validação de link rejeita URL de canal/playlist (§5.3) |
| Upload, redistribuição ou publicação | A ferramenta escreve em disco local e nada mais |
| Multiusuário, autenticação, deploy em servidor | Vincula-se em `127.0.0.1` |

### 2.3 A posição sobre DRM

A distinção importa e é deliberada.

O yt-dlp **detecta** conteúdo protegido e levanta erro com a mensagem
`"This video is DRM protected"` (RESEARCH §6.3). Esta ferramenta **propaga essa
detecção** e a traduz para uma mensagem honesta em português, encerrando o job.

Detectar e parar é o comportamento correto de um cliente bem-comportado. Não há,
e não haverá, código que tente contornar a proteção.

---

## 3. Restrições técnicas

| # | Restrição | Consequência de projeto |
|---|---|---|
| 1 | yt-dlp como **biblioteca** (`import yt_dlp`), nunca por `subprocess` | O próprio README do yt-dlp avisa que stdout não é contrato estável |
| 2 | ffmpeg é dependência externa | Verificar na inicialização; aviso claro na interface, nunca stack trace |
| 3 | Nada de rede, disco ou yt-dlp na camada de domínio | Garantido por teste de arquitetura (§4.3) |
| 4 | **Um download por vez**, sem paralelismo entre jobs | Uma thread de trabalho; banda é uma só |
| 5 | Roda em `127.0.0.1` | Sem exposição na rede |

> **Nota sobre a restrição 4.** Ela vale para **jobs**. Ela não impede o yt-dlp de
> usar threads internamente **dentro** de um job — e ele usa: o caminho DASH
> multi-formato dispara `ThreadPoolExecutor` sem configuração especial
> (RESEARCH §3.4, caso 4). São coisas diferentes. A fila serializa jobs; o
> estado precisa de lock mesmo assim.

---

## 4. Arquitetura

### 4.1 Camadas

```
src/download/    único lugar que conhece o yt-dlp (adapter)
src/domain/      PURO: models, perfis, nomenclatura, validação
src/storage/     SQLite: histórico
src/queue/       fila de trabalhos + worker em background
src/pipeline.py  orquestração, usada pela CLI E pela web
src/cli.py       linha de comando
src/web/         FastAPI, só orquestração
web/             index.html + style.css + app.js (vanilla)
config/          perfis.yaml e projetos.yaml
tests/
```

### 4.2 Regras duras

**REGRA 1** — `src/domain/` nunca importa de `src/download/`, `src/storage/` ou
`src/queue/`.

**REGRA 2** — `src/web/` nunca importa de `src/domain/`. Ele fala com
`src/pipeline.py`.

### 4.3 Garantia

`tests/test_arquitetura.py` percorre a árvore de `src/` com o módulo `ast` e
falha se qualquer import violar as regras. É um teste de verdade, não um
comentário: quebra o build.

### 4.4 Direção das dependências

```
        cli.py ─┐
                ├──> pipeline.py ──┬──> domain/    (puro)
        web/  ──┘                  ├──> download/  ──> yt_dlp
                                   ├──> storage/   ──> sqlite3
                                   └──> queue/     ──> threading
```

`domain/` é folha: não depende de ninguém dentro de `src/`.

---

## 5. O domínio — o que vive lá e por quê

Esta é a seção mais importante do documento.

**O risco declarado do projeto:** como o yt-dlp faz o trabalho pesado, existe o
perigo de `src/domain/` ficar vazia e tudo virar wrapper. Cada item abaixo
precisa justificar por que é lógica **minha** e não do yt-dlp.

O critério é: *o yt-dlp resolve isso? Se sim, não é meu. Se resolve
parcialmente, o que falta é meu.*

### 5.1 Nomenclatura e sanitização de arquivo

**Vive no domínio. Justificativa: a mais forte de todas.**

O yt-dlp tem `sanitize_filename`. Ele **não** resolve o problema. Medições em
RESEARCH §7.4, na máquina de destino:

| O que falta | Evidência |
|---|---|
| Nomes reservados do DOS (`CON`, `NUL`, `AUX`, `COM1`…) | `sanitize_filename('NUL')` → `'NUL'`. Nenhum tratamento no pacote inteiro. |
| Truncamento por tamanho | `'A'*300` sai com 300 chars. NTFS rejeita acima de 255. |
| Nome vazio | `sanitize_filename('')` → `''` |
| Ponto ou espaço final | `'Final da season.'` preservado; o shell do Windows não suporta |
| Conhecimento do diretório de destino | Não faz ideia do comprimento do caminho do projeto |
| Colisão com arquivo existente | Fora do escopo dele |

E o que ele **faz** é ativamente indesejado para este caso de uso: substitui
caracteres proibidos por homóglifos Unicode de largura total (`:` → `U+FF1A`
`：`). O arquivo é válido, mas o nome não pode ser digitado no teclado, não é
encontrado por busca com os caracteres normais, e quebra o console cp1252 do
Windows com `UnicodeEncodeError`.

**O achado decisivo** (RESEARCH §7.3): escrever num arquivo chamado `NUL` na
máquina de destino **não levanta erro**, `exists()` retorna `True`, e os bytes
desaparecem. Um título que sanitize para `NUL` produziria job "concluído",
histórico gravado e arquivo inexistente.

Sanitização, aqui, é **questão de correção**, não de estilo.

O objetivo do domínio é diferente do objetivo do yt-dlp: gerar um nome que um
**editor de vídeo** consiga achar, digitar e abrir no Premiere, seis meses
depois, num HD externo.

### 5.2 Resolução de perfil YAML → seletor de formato

**Vive no domínio.** O yt-dlp aceita um seletor; ele não tem conceito de perfil
nomeado, não valida se o perfil existe, não sabe que `,` (múltiplos formatos)
é proibido neste produto porque quebra a premissa de um arquivo por job, e não
sabe que um `key` de postprocessor inválido só falha em runtime com `KeyError`
(RESEARCH §4).

A tradução "nome legível → configuração validada" é o produto.

### 5.3 Validação e normalização de link

**Vive no domínio.** Três coisas que o yt-dlp não faz por nós:

1. **Rejeitar canal/playlist.** `extract_info` percorre a lista inteira
   (RESEARCH §1.2). Download em massa está fora de escopo (§2.2), então a
   recusa tem que ser anterior à chamada.
2. **Normalizar** para forma canônica, de modo que `youtu.be/X`,
   `youtube.com/watch?v=X` e a versão com `&t=42` sejam o mesmo vídeo — sem
   isso, o histórico registra duplicatas.
3. **Deduplicar** a lista colada pelo usuário.

### 5.4 Montagem do caminho por projeto e tratamento de colisão

**Vive no domínio.** O `outtmpl` do yt-dlp monta caminhos, mas não conhece o
conceito de "projeto", não valida que o destino existe e é gravável, e sua
política de colisão é sobrescrever ou pular. A política deste produto é
desambiguar preservando os dois arquivos.

### 5.5 Modelos: `Video`, `Job`, `Perfil`, `Projeto`

**Vivem no domínio.** O `info_dict` do yt-dlp tem centenas de campos, é
"dicionário-like" mas não garantidamente `dict` (RESEARCH §1.3), e muda entre
versões. Um modelo próprio, com os campos que o produto usa, é a fronteira
anticorrupção contra essa instabilidade.

### 5.6 Classificação de erro

**A taxonomia vive no domínio; o mapeamento vive em `download/`.**

Divisão deliberada. O *enum* de motivos (`PRIVADO`, `BLOQUEIO_REGIONAL`, …) e as
mensagens em português são regra de produto — decisões sobre o que o usuário lê
e o que vale a pena tentar de novo. A tabela que traduz exceção do yt-dlp para
esse enum precisa conhecer as classes do yt-dlp, e por isso fica no adapter.

Isso importa porque a classificação é **frágil por natureza**: os motivos de
indisponibilidade só são distinguíveis por substring de mensagem, e a mensagem
vem do site, não do yt-dlp (RESEARCH §6.3). Quando o YouTube mudar o texto, a
correção é uma linha de tabela no adapter, e o domínio não é tocado.

### 5.7 Máquina de estados do job

**Vive no domínio.** Quais transições são legais é regra de produto. Em
particular, duas regras que o yt-dlp desconhece:

- só é cancelável um job que ainda não começou;
- um job interrompido por fechamento do programa é `interrompido`, nunca
  `concluido`.

### 5.8 O que NÃO vive no domínio

Registro explícito, para evitar arquitetura por inércia:

| Item | Onde vive | Por quê |
|---|---|---|
| Chamar o yt-dlp | `download/` | É I/O |
| Detectar ffmpeg | `download/` | Toca o sistema de arquivos |
| Baixar thumbnail | Em lugar nenhum | O navegador busca direto do CDN (RESEARCH §8) |
| Calcular velocidade/ETA | `queue/` | Vem pronto do progress hook |
| Escolher o melhor formato | yt-dlp | O seletor faz; nós só o construímos |
| Merge de vídeo e áudio | ffmpeg | Não é nosso problema |

---

## 6. Perfis de qualidade

Definidos em `config/perfis.yaml`. Os quatro iniciais, com justificativa em
RESEARCH §2.2:

| Perfil | Alvo | Container |
|---|---|---|
| `edicao_1080` | 1080p, preferindo H.264 + AAC | mp4 |
| `edicao_4k` | até 2160p, qualquer codec | mkv |
| `so_audio` | só a trilha de áudio, em m4a | m4a |
| `preview_leve` | até 480p, menor arquivo | mp4 |

**Regra que o `edicao_4k` documenta:** ele não filtra por `avc1`, ao contrário do
`edicao_1080`. O YouTube não serve H.264 acima de 1080p; um filtro de codec ali
faria o perfil cair silenciosamente para o fallback, entregando 1080p a quem
pediu 4K.

### 6.1 Esquema de um perfil

```yaml
edicao_1080:
  descricao: "1080p H.264 para timeline"
  format: "bv*[height<=1080][vcodec^=avc1]+ba[acodec^=mp4a]/bv*[height<=1080]+ba/b[height<=1080]/b"
  format_sort: ["res:1080", "vcodec:h264", "acodec:aac", "fps"]
  merge_output_format: "mp4"
  postprocessors: []
  exige_ffmpeg: true
```

### 6.2 Validação obrigatória na carga

- `format` presente e não vazio
- `format` **não contém `,`** — múltiplos formatos quebram um-arquivo-por-job
- `merge_output_format` numa lista conhecida
- todo `key` de postprocessor existe em `yt_dlp.postprocessor`
- `exige_ffmpeg: true` + ffmpeg ausente → perfil marcado indisponível na UI

---

## 7. Projetos

`config/projetos.yaml` mapeia nome legível para diretório de destino.

```yaml
projetos:
  cliente_x:
    nome: "Cliente X"
    pasta: "D:/FOOTAGE/cliente_x"
  pessoal:
    nome: "Canal pessoal"
    pasta: "D:/FOOTAGE/pessoal"
```

Validação na carga: a pasta existe ou é criável, e é gravável. Um projeto
inválido aparece desabilitado na interface, com o motivo.

> **Recomendação forte:** apontar `pasta` para fora do repositório. O
> `.gitignore` cobre as variações comuns, mas um `.mp4` que entra no histórico
> do Git não sai mais sem reescrever o histórico.

---

## 8. Nomenclatura de arquivo

### 8.1 Padrão

```
{data_upload} - {titulo_sanitizado} [{video_id}].{ext}
```

Exemplo: `20250814 - Melhores momentos do major [dQw4w9WgXcQ].mp4`

Racional de cada parte:

- **data primeiro** — ordenação cronológica no Explorer sem depender de metadados
- **título** — é como um editor procura material
- **id entre colchetes** — desambiguação estável e chave de reconciliação com o
  histórico

### 8.2 Regras de sanitização

Ordem de aplicação (a ordem importa: truncar antes de tratar ponto final
reintroduziria o problema):

1. Remover caracteres de controle (0–31, 127)
2. Substituir os proibidos `< > : " / \ | ? *` por `-`
   — **não** por homóglifos de largura total
3. Colapsar espaços e hifens repetidos
4. Remover ponto e espaço do início e do fim
5. Se o nome (sem extensão) casar com nome reservado do DOS,
   case-insensitive, com ou sem extensão → sufixar `_`
6. Truncar respeitando o orçamento de caminho (§8.3), preservando extensão
7. Se sobrar vazio → usar `video_{id}`

### 8.3 Orçamento de caminho

Teto conservador de **200 caracteres** para o caminho completo, contado a partir
da raiz do projeto de destino.

Justificativa: o limite real do NTFS é 255 por componente e o `MAX_PATH` é 260,
mas `LongPathsEnabled` está ativo na máquina de destino e mascara o problema
localmente. Premiere, After Effects e Resolve não são confiáveis com caminhos
longos, e o material vai para HD externo, NAS e máquina de cliente. Footage que
o Windows aceita mas o Premiere não abre é pior do que um download que falha na
hora.

### 8.4 Colisão

Sufixo numérico antes da extensão: `nome (2).mp4`, `nome (3).mp4`. Nunca
sobrescrever.

---

## 9. Histórico — schema SQLite

Arquivo: `data/historico.db` (ignorado pelo Git).

```sql
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
```

### 9.1 Decisões do schema

**A chave é `(extractor, video_id, perfil)`.** O mesmo vídeo em qualidades
diferentes são registros distintos — é requisito. `extractor` entra na chave
porque `video_id` só é único dentro de um site; dois sites podem colidir.

**Datas em TEXT ISO-8601 UTC.** SQLite não tem tipo de data. ISO-8601 ordena
corretamente como texto, o que torna o índice em `criado_em` útil.

**`caminho` é `NULL` até concluir.** Um caminho preenchido com status diferente
de `concluido` é inconsistência.

**`motivo_falha` guarda o enum; `mensagem_falha` guarda o texto original do
yt-dlp.** Os dois. O enum serve para filtrar e decidir retry; o texto original é
o fallback que impede "erro desconhecido" quando o site muda a mensagem
(§5.6).

### 9.2 Valores de `status`

`concluido`, `falhou`, `interrompido`.

A fila tem mais estados (§10.2); o histórico só registra desfechos.

---

## 10. Fila — schema e estados

### 10.1 A fila é em memória, com reconciliação no histórico

A fila viva não é persistida. Ao subir, o programa marca como `interrompido`
todo registro que ficou em estado não-terminal, e a fila começa vazia.

Justificativa: é uma ferramenta local de um usuário. Persistir a fila
introduziria o problema de retomar downloads parciais entre execuções, que é
complexidade que o produto não precisa. O que **não** pode acontecer é um job
interrompido ser lido como concluído — e isso a reconciliação resolve.

### 10.2 Estados

```
na_fila ──> baixando ──> concluido
   │            │
   │            └──────> falhou
   │            │
   │            └──────> interrompido   (programa fechou no meio)
   │
   └──> cancelado                       (só antes de começar)
```

| Estado | Terminal? | Descrição |
|---|---|---|
| `na_fila` | não | Aguardando o worker |
| `baixando` | não | Em progresso |
| `concluido` | sim | Arquivo no disco, histórico gravado |
| `falhou` | sim | Erro classificado |
| `cancelado` | sim | Cancelado antes de começar |
| `interrompido` | sim | Programa fechou durante o download |

**Transições ilegais** (rejeitadas pelo domínio): cancelar um job em `baixando`;
qualquer saída de estado terminal; `na_fila` direto para `concluido`.

### 10.3 Estrutura de um job em memória

| Campo | Tipo | Nota |
|---|---|---|
| `id` | str | UUID gerado na criação |
| `video` | `Video` | metadados já obtidos na inspeção |
| `perfil` | str | nome do perfil |
| `projeto` | str | nome do projeto |
| `estado` | enum | §10.2 |
| `progresso` | `Progresso` | substituído atomicamente, nunca mutado |
| `caminho_final` | str \| None | preenchido ao concluir |
| `motivo_falha` | enum \| None | |
| `mensagem_falha` | str \| None | texto original do yt-dlp |
| `criado_em` | datetime | |

### 10.4 Concorrência

**Uma** thread de trabalho, consumindo uma `queue.Queue`. Um download por vez.

O estado de todos os jobs fica num dicionário protegido por
`threading.Lock`. O progress hook adquire o lock apenas para **substituir** o
objeto `Progresso` do job — não muta campo a campo.

Isso é obrigatório, não precaução: o hook pode ser chamado de threads criadas
pelo próprio yt-dlp, sem configuração especial (RESEARCH §3.4, caso 4).

**O hook não faz I/O.** Nada de SQLite, nada de `print`. Ele dispara muitas
vezes por segundo; a persistência acontece nas transições terminais.

### 10.5 Cancelamento

- Job em `na_fila`: marcado `cancelado`; o worker o descarta ao retirá-lo.
- Job em `baixando`: **não cancelável**. A API responde `409 Conflict`.

Justificativa: interromper o yt-dlp no meio exigiria levantar exceção de dentro
do progress hook, o que deixa arquivos `.part` órfãos e estado ambíguo. Para uma
ferramenta de um usuário, esperar o download atual terminar é aceitável; estado
corrompido não é.

---

## 11. API HTTP

Toda em `127.0.0.1`. Só JSON. Zero regra de negócio — delega a `pipeline.py`.

| Método | Rota | Descrição |
|---|---|---|
| POST | `/api/inspecionar` | link(s) → metadados, **sem baixar** |
| POST | `/api/fila` | adiciona job(s) com perfil e projeto |
| GET | `/api/fila` | estado atual de todos os jobs |
| DELETE | `/api/fila/{id}` | cancela job que ainda não começou |
| GET | `/api/historico` | com busca e filtro |
| GET | `/api/config` | perfis, projetos, status do ffmpeg |

### 11.1 Códigos de resposta

| Código | Quando |
|---|---|
| 200 | Sucesso |
| 400 | Link inválido, perfil ou projeto inexistente |
| 404 | Job não encontrado |
| 409 | Cancelamento de job já em andamento |
| 422 | Corpo malformado (FastAPI) |

`POST /api/inspecionar` responde **200 com resultado parcial** quando alguns
links falham: cada item traz seu próprio `ok` e, se falhou, o motivo. Um link
ruim numa lista de dez não invalida os outros nove.

---

## 12. Interface

HTML/CSS/JS puro em `web/`. Sem framework, sem etapa de build.

- Campo de colar links, vários, um por linha
- Cartão de preview por vídeo: thumbnail, título, canal, duração, seletor de
  perfil, seletor de projeto
- Fila com barra de progresso, velocidade e tempo restante, via **polling a cada
  1 s**
- Botão de cancelar por item
- Histórico navegável com busca e botão "abrir pasta"
- Aviso no topo se o ffmpeg não estiver instalado
- Variáveis CSS no topo de `style.css`
- Código comentado, sem minificação

**Polling e não WebSocket**, deliberadamente: um usuário, uma aba, atualização a
cada segundo. WebSocket adicionaria reconexão e gestão de estado sem benefício
perceptível.

---

## 13. Decisões tomadas sem consulta

Registradas para revisão.

| # | Decisão | Racional |
|---|---|---|
| 1 | `(extractor, video_id, perfil)` como chave, e não só `(video_id, perfil)` | `video_id` só é único por site |
| 2 | Fila em memória + reconciliação de interrompidos na subida | Evita retomada parcial entre execuções |
| 3 | Job em `baixando` não é cancelável (409) | Cancelar no meio deixa `.part` órfão e estado ambíguo |
| 4 | Datas em TEXT ISO-8601 UTC | SQLite não tem tipo de data; ISO ordena como texto |
| 5 | Proibidos viram `-`, não homóglifos Unicode | Nome tem que ser digitável e buscável |
| 6 | Orçamento de 200 chars de caminho | Margem para NLE e destino externo |
| 7 | Polling de 1 s em vez de WebSocket | Um usuário, uma aba |
| 8 | `motivo_falha` **e** `mensagem_falha`, ambos | Enum para lógica, texto original como fallback |
| 9 | Perfil com `,` no seletor é erro de config | Quebra a premissa de um arquivo por job |
| 10 | Thumbnail não é baixada pelo backend | O navegador busca do CDN |

## 14. Decisões em aberto

| # | Questão | Situação |
|---|---|---|
| 1 | Container do `edicao_4k`: `mkv` ou forçar `mp4`? | Proposto `mkv`; depende do fluxo de edição |
| 2 | Embutir thumbnail no arquivo? | Recomendado **não**; `writethumbnail` como `.jpg` ao lado é mais barato |
| 3 | Orçamento de 200 chars é adequado? | Depende da profundidade real das pastas de projeto |
| 4 | Retry automático em falha de rede? | Não especificado. Sugestão: manual no MVP |
| 5 | Limpeza de `.part` órfãos na subida? | Não especificado |
