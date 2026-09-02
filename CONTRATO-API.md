# CONTRATO-API.md — Baixador de Footage

Este documento descreve a API que a interface consome. Foi escrito para quem
**não conhece o projeto** e vai desenhar a tela a partir daqui.

Todos os exemplos de resposta foram **gerados por execução real** da API
(`scripts/gerar_exemplos_contrato.py`), com os metadados de um vídeo real
capturados em `spike_meta.json`. Só o download em si é simulado — o gerador não
toca a rede —, então os números de progresso e tamanho são ilustrativos, mas a
**forma** de cada resposta é exatamente a que a interface vai receber.

---

## 1. O que a aplicação faz

É uma ferramenta **local**, de um usuário só, que roda no próprio computador
(`http://127.0.0.1:8000`). O usuário é editor de vídeo e usa a ferramenta para
baixar footage que vai entrar nas edições dele.

O fluxo de uso, na ordem em que a tela deve conduzir:

1. Cola um ou vários **links** (um por linha) numa caixa de texto.
2. A tela mostra **na hora**, sem baixar nada: thumbnail, título, canal,
   duração e as qualidades disponíveis de cada vídeo.
3. Para cada vídeo, escolhe um **perfil de qualidade** (ex.: "1080p para
   edição") e um **projeto de destino** (a pasta do cliente).
4. Manda para a **fila**. Os downloads acontecem **um por vez**, em sequência.
5. Acompanha o **progresso** enquanto continua trabalhando.
6. Consulta o **histórico** depois e vê onde cada arquivo foi parar.

Não há login, não há vários usuários, não há upload. A interface é uma página
só.

## 2. Regras gerais da API

| Regra | Detalhe |
|---|---|
| Base | `http://127.0.0.1:8000` |
| Formato | JSON em tudo: corpo de requisição e de resposta |
| Codificação | UTF-8. Títulos têm acento e podem ter emoji |
| Erros | **Uma forma só**, em qualquer status de erro: `{"erro": "mensagem legível em português"}`. O 422 acrescenta `detalhes`. Nunca vem stack trace |
| Estáticos | `GET /` serve a página (`index.html`); os demais arquivos da pasta `web/` são servidos na raiz |

Códigos de status que a tela precisa tratar:

| Código | Significado | O que mostrar |
|---|---|---|
| 200 | Sucesso | — |
| 400 | Entrada inválida: link, perfil ou projeto que não existe, ffmpeg ausente | A mensagem de `erro`, junto do campo que a causou |
| 404 | Job inexistente (só em `DELETE /api/fila/{id}`) | A mensagem; provavelmente a fila mudou — recarregar |
| 409 | Conflito: já baixado, já na fila, ou cancelar job em andamento | A mensagem. Para "já baixado", oferecer **baixar de novo** (`forcar`) |
| 422 | Corpo malformado (campo faltando ou tipo errado) | Bug de integração; mostrar `erro` e logar `detalhes` |
| 500 | Erro interno | A mensagem de `erro`, com opção de tentar de novo |

## 3. Endpoints

| Método | Caminho | Para quê |
|---|---|---|
| `GET` | `/api/config` | Perfis, projetos e status do ffmpeg. **Chamar primeiro**, ao abrir a página |
| `POST` | `/api/inspecionar` | Links colados → metadados de cada vídeo, **sem baixar** |
| `POST` | `/api/fila` | Enfileira um ou mais links com um perfil e um projeto |
| `GET` | `/api/fila` | Estado de todos os jobs. **Polling a cada 1 s** |
| `DELETE` | `/api/fila/{id}` | Cancela um job que ainda não começou |
| `GET` | `/api/historico` | O que já foi baixado, com busca e filtro |

### 3.1 `GET /api/config`

Sem parâmetros. Devolve três blocos:

- `ffmpeg` — `disponivel` (o ffmpeg foi encontrado), `completo` (ffmpeg **e**
  ffprobe), e os caminhos. **Se `disponivel` for `false`, a tela mostra um aviso
  fixo no topo**: sem ffmpeg os perfis de edição não funcionam.
- `perfis[]` — `nome` (o identificador a enviar em `/api/fila`), `descricao`
  (o texto para o usuário), `disponivel` (se `false`, mostrar desabilitado com o
  motivo "exige ffmpeg"), `limite_dimensao` (o teto de qualidade, `null` para o
  perfil de áudio), `container` (extensão do arquivo final: `mp4`, `mkv`, `m4a`).
- `projetos[]` — `nome` (identificador a enviar), `rotulo` (texto para o
  usuário), `pasta` (o destino no disco), `valido` e `motivo` (se `false`,
  mostrar desabilitado com o motivo).

### 3.2 `POST /api/inspecionar`

Corpo: `{"links": "texto colado, um link por linha"}`. Envie o conteúdo da
caixa de texto **como está** — a API apara espaços, ignora linhas vazias e
remove duplicatas.

Resposta: `{"itens": [...]}`, **um item por link distinto**, na ordem colada.
Cada item tem `ok`:

- `ok: true` — traz `video` (metadados), `url` (a forma canônica do link),
  `e_youtube`, `aviso` (ver §6) e `baixados` (ver §7).
- `ok: false` — traz `erro` (mensagem para o usuário) e `motivo` (código, ver
  §5). Um link ruim **não invalida os outros**: a tela mostra um cartão de erro
  para ele e cartões normais para os demais.

Esta chamada **espera a rede** (consulta o site de cada vídeo). Com dez links
pode levar alguns segundos: mostrar estado de carregamento.

Dentro de `video`:

| Campo | Tipo | Nota |
|---|---|---|
| `id` | string | Identificador no site de origem |
| `titulo` | string | Pode ter acento, emoji, ser longo |
| `canal` | string ou `null` | |
| `duracao_s` | inteiro ou `null` | **Segundos**. Ver §4 |
| `thumbnail` | URL ou `null` | Imagem hospedada no site de origem; usar direto no `<img>`. Ver §4 |
| `data_upload` | `"AAAAMMDD"` ou `null` | |
| `qualidades` | lista de inteiros | Qualidades disponíveis, pela **menor dimensão** do vídeo. Ver §4 |
| `formatos[]` | lista | Todos os streams disponíveis. Detalhe técnico; a tela principal não precisa exibir |

### 3.3 `POST /api/fila`

Corpo:

```json
{"urls": ["https://..."], "perfil": "edicao_1080", "projeto": "pessoal", "forcar": false}
```

- `urls`: lista de links (os mesmos que foram inspecionados, ou não — a
  inspeção não é pré-requisito).
- `perfil` e `projeto`: os `nome` vindos de `/api/config`.
- `forcar`: opcional, padrão `false`. `true` baixa de novo um vídeo que já foi
  concluído neste perfil (o arquivo antigo **não é sobrescrito**: o novo ganha
  sufixo ` (2)`).

Resposta: `{"ids": ["..."]}` — um id por job criado, na ordem das `urls`.

**Tudo ou nada**: se qualquer link da lista for inválido ou conflitar, nada é
enfileirado e a resposta é 400/409.

### 3.4 `GET /api/fila`

Sem parâmetros. `{"jobs": [...]}` na ordem de chegada, incluindo os já
terminados (a fila é a sessão atual; ao fechar o programa ela zera, e o que
importa vai para o histórico).

A tela faz **polling a cada 1 segundo** enquanto houver job em `na_fila` ou
`baixando`. Não disparar uma nova requisição antes de a anterior responder.

Campos de cada job:

| Campo | Tipo | Nota |
|---|---|---|
| `id` | string | Para o `DELETE` |
| `estado` | string | Um dos seis de §5 |
| `perfil`, `projeto` | string | Os `nome`s |
| `criado_em` | ISO-8601 UTC | Ex.: `2026-09-02T18:48:58+00:00` |
| `video` | objeto | `id`, `titulo`, `canal`, `duracao_s`, `thumbnail` |
| `progresso` | objeto ou `null` | `null` antes de começar. Ver §4 |
| `caminho_final` | string ou `null` | Preenchido só em `concluido` |
| `motivo_falha`, `mensagem_falha` | string ou `null` | Preenchidos só em `falhou`. Ver §5 |
| `aviso` | string ou `null` | Aviso não-bloqueante (ex.: pasta do projeto profunda demais, nome foi encurtado) |

### 3.5 `DELETE /api/fila/{id}`

Cancela. Só funciona para job em `na_fila`. Respostas:

- `200 {"cancelado": true}`
- `404` — id não existe
- `409` — o job já começou (ou já terminou). **Um download em andamento não
  pode ser cancelado**: é decisão do produto, para não deixar arquivo parcial
  corrompido. A tela deve **desabilitar o botão de cancelar** quando o estado for
  diferente de `na_fila`.

### 3.6 `GET /api/historico`

Parâmetros de query, todos opcionais:

- `termo` — busca no título. **Ignora acento e maiúsculas**: `selecao` acha
  "Seleção".
- `projeto` — filtra pelo `nome` do projeto.
- `limite` — padrão 100, máximo 1000.

Resposta: `{"registros": [...]}`, mais recente primeiro. Cada registro é uma
linha do banco: `titulo`, `canal`, `duracao_s`, `perfil`, `projeto`, `caminho`
(onde o arquivo está), `tamanho_bytes`, `resolucao` (a que **realmente** foi
baixada, ex.: `1080x1920`), `status`, `motivo_falha`, `mensagem_falha`,
`criado_em`, `concluido_em`.

`status` no histórico é um de: `baixando`, `concluido`, `falhou`,
`interrompido` (o programa fechou no meio).

---

## 4. Campos que a tela precisa formatar

A API entrega valores **crus**. Não formata nada. Estes exigem tratamento:

| Campo | Vem como | Mostrar como |
|---|---|---|
| `duracao_s` | segundos inteiros (`65`) | `1:05`. Acima de uma hora, `1:02:05`. `null` → `--:--` |
| `tamanho_bytes` | bytes (`9437184`) | `9,0 MB`. `null` → `--` |
| `progresso.percentual` | float (`38.88888`) ou `null` | Arredondar: `39%`. `null` = total desconhecido → barra indeterminada |
| `progresso.velocidade_bps` | bytes por segundo, float ou `null` | `3,1 MB/s`. `null` → `--` |
| `progresso.eta_s` | segundos ou `null` | `0:02`. `null` → `--` |
| `fps` (em `formatos[]`) | float **fracionário** (`29.97`, `59.94`) | Uma casa decimal quando não for inteiro. **Nunca truncar** para inteiro |
| `thumbnail` | URL ou **`null`** | Se `null`, um placeholder. Nunca `<img>` quebrado |
| `criado_em`, `concluido_em` | ISO-8601 em UTC | Converter para o fuso local |
| `qualidades` | `[144, 240, ..., 1080]` | Ex.: `1080p`. É pela **menor dimensão**: um vídeo vertical 1080x1920 e um horizontal 1920x1080 mostram o mesmo `1080` |
| `resolucao` | `"1080x1920"` | Pode exibir como está; vertical tem altura maior que largura |
| `caminho`, `caminho_final`, `pasta` | string | Caminhos do Windows. Os que vêm do download usam `\` (`D:\FOOTAGE\pessoal\...`); os da configuração vêm como foram escritos, geralmente com `/`. Exibir como está; nunca editar |

**`tem_audio` e `tem_video` (em `formatos[]`) — três estados.** Cada formato
traz `vcodec` e `acodec`. O valor da string `"none"` significa "não tem";
**`null` significa "desconhecido"**, não "não tem". Para não repetir essa
lógica na tela, a API já entrega `tem_video` e `tem_audio` resolvidos como
booleanos — use-os, e trate `acodec: null` apenas como "codec não informado"
se for exibir o codec.

---

## 5. Estados de um job e o que a tela mostra

```
na_fila ──> baixando ──> concluido
   │            │
   │            ├──────> falhou
   │            └──────> interrompido   (programa fechou no meio)
   └──> cancelado                       (só antes de começar)
```

| Estado | O que mostrar | Cancelar? |
|---|---|---|
| `na_fila` | Posição na fila, sem barra | **Sim** |
| `baixando` | Barra de progresso, velocidade, tempo restante | Não (botão desabilitado) |
| `concluido` | Caminho do arquivo (`caminho_final`) e botão "abrir pasta" (ver §8) | Não |
| `falhou` | `mensagem_falha` em destaque; se `motivo_falha` for `rede` ou `rate_limit`, oferecer **tentar de novo** | Não |
| `cancelado` | Discreto, pode colapsar | Não |
| `interrompido` | Só aparece no **histórico**: "o programa fechou durante o download" | — |

`motivo_falha` é um código estável para lógica; `mensagem_falha` é o texto
para o usuário, já em português. Códigos possíveis:

| `motivo_falha` | Significa | Vale tentar de novo? |
|---|---|---|
| `indisponivel` | Vídeo removido ou inexistente | Não |
| `privado` | Vídeo privado | Não |
| `restricao_idade` | Exige conta autenticada | Não |
| `bloqueio_regional` | Bloqueado no país | Não |
| `drm` | Conteúdo protegido. **Fora do escopo da ferramenta**, por decisão | Não |
| `site_nao_suportado` | O site não é suportado | Não |
| `rede` | Falha de rede | **Sim** |
| `rate_limit` | O site limitou as requisições | **Sim**, depois de esperar |
| `sem_ffmpeg` | ffmpeg ausente | Não (instalar) |
| `disco` | Falha ao gravar | Não |
| `desconhecido` | Não classificado; `mensagem_falha` traz o texto original do erro | — |

Em `/api/inspecionar`, o `motivo` de um item com `ok: false` usa os mesmos
códigos, mais `link_invalido` (a linha colada não é um link, ou é link de
canal/playlist — download em massa está fora do escopo).

---

## 6. O aviso de "site que não é YouTube"

A ferramenta conhece o YouTube: normaliza o link (remove parâmetros de
rastreio, aceita `youtu.be`, `/shorts/`, etc.), evita duplicatas e casa com o
histórico. Para **qualquer outro site**, o link passa como foi colado, e a
deduplicação e o histórico só funcionam se o link for colado exatamente igual.

Onde aparece: no item de `/api/inspecionar`, campo **`aviso`** (string), com
**`e_youtube: false`**. Para links do YouTube, `aviso` é `null`.

Como mostrar: um aviso **visível no cartão do vídeo**, não escondido. O texto
vem pronto da API. Não bloqueia o enfileiramento.

---

## 7. Duplicatas: `baixados` e `forcar`

No item de `/api/inspecionar`, `baixados` é um objeto **por perfil** com o que
já foi concluído para aquele vídeo:

```json
{"baixados": {"edicao_1080": {"caminho": "...", "projeto": "pessoal", "resolucao": "1080x1920", "concluido_em": "..."}}}
```

Vazio (`{}`) se nunca foi baixado. A tela usa isso para avisar **antes de
enfileirar**: se o perfil selecionado está em `baixados`, mostrar "já baixado
em <caminho>" e oferecer "baixar de novo". Se o usuário insistir, enviar
`forcar: true` em `/api/fila`; sem isso a API responde 409.

---

## 8. Botão "abrir pasta" — pendente na API

O produto prevê um botão "abrir pasta" no histórico e no job concluído. Um
navegador não abre pastas do disco por conta própria; isso exige um endpoint
que peça ao sistema operacional. **Ele ainda não existe.** A forma planejada:

```
POST /api/abrir-pasta   {"caminho": "<caminho_final ou caminho do histórico>"}
→ 200 {"aberto": true}  |  400 se o caminho não estiver dentro de um projeto configurado
```

Enquanto não existir, o botão deve **copiar o caminho** para a área de
transferência. Desenhe o botão; a integração decide o comportamento.

---

## 9. Exemplos reais

Gerados por `python scripts/gerar_exemplos_contrato.py`. Vídeo real: um Short
vertical de 65 segundos, com 41 formatos (45 do site menos 4 storyboards).
Listas de `formatos` truncadas em 3 itens.

### GET /api/config

`200`

```json
{
  "ffmpeg": {
    "disponivel": true,
    "completo": true,
    "ffmpeg": "C:\\ffmpeg\\bin\\ffmpeg.exe",
    "ffprobe": "C:\\ffmpeg\\bin\\ffprobe.exe"
  },
  "perfis": [
    {
      "nome": "edicao_1080",
      "descricao": "1080p H.264 + AAC — abre nativo no Premiere/Resolve",
      "disponivel": true,
      "exige_ffmpeg": true,
      "limite_dimensao": 1080,
      "container": "mp4"
    },
    {
      "nome": "edicao_4k",
      "descricao": "Até 2160p — VP9/AV1, pode exigir transcode para a timeline",
      "disponivel": true,
      "exige_ffmpeg": true,
      "limite_dimensao": 2160,
      "container": "mkv"
    },
    {
      "nome": "so_audio",
      "descricao": "Só a trilha de áudio, em m4a",
      "disponivel": true,
      "exige_ffmpeg": true,
      "limite_dimensao": null,
      "container": "m4a"
    },
    {
      "nome": "preview_leve",
      "descricao": "Até 480p, menor arquivo — para bater o olho antes de baixar",
      "disponivel": true,
      "exige_ffmpeg": true,
      "limite_dimensao": 480,
      "container": "mp4"
    }
  ],
  "projetos": [
    {
      "nome": "cliente_x",
      "rotulo": "Cliente X",
      "pasta": "D:/FOOTAGE/cliente_x",
      "valido": true,
      "motivo": null
    },
    {
      "nome": "pessoal",
      "rotulo": "Canal pessoal",
      "pasta": "D:/FOOTAGE/pessoal",
      "valido": true,
      "motivo": null
    }
  ]
}
```

### POST /api/inspecionar — três links: real, outro site, lixo

`200`

```json
{
  "itens": [
    {
      "ok": true,
      "original": "https://youtube.com/shorts/LzS8kB6lIm0?si=0RP8BxS-q-XGH4Dw",
      "url": "https://www.youtube.com/watch?v=LzS8kB6lIm0",
      "e_youtube": true,
      "aviso": null,
      "video": {
        "id": "LzS8kB6lIm0",
        "extractor": "Youtube",
        "url_canonica": "https://www.youtube.com/watch?v=LzS8kB6lIm0",
        "titulo": "Camisa azul da Seleção: críticas ao design e lembrança histórica",
        "canal": "Canal Michuruca",
        "duracao_s": 65,
        "thumbnail": "https://i.ytimg.com/vi/LzS8kB6lIm0/maxresdefault.jpg",
        "data_upload": "20260901",
        "qualidades": [
          144,
          240,
          360,
          480,
          608,
          720,
          1080
        ],
        "formatos": [
          {
            "format_id": "233",
            "ext": "mp4",
            "resolucao": "audio only",
            "largura": null,
            "altura": null,
            "fps": null,
            "vcodec": "none",
            "acodec": null,
            "tem_video": false,
            "tem_audio": true,
            "tbr": null,
            "tamanho_bytes": null
          },
          {
            "format_id": "234",
            "ext": "mp4",
            "resolucao": "audio only",
            "largura": null,
            "altura": null,
            "fps": null,
            "vcodec": "none",
            "acodec": null,
            "tem_video": false,
            "tem_audio": true,
            "tbr": null,
            "tamanho_bytes": null
          },
          {
            "format_id": "139-drc",
            "ext": "m4a",
            "resolucao": "audio only",
            "largura": null,
            "altura": null,
            "fps": null,
            "vcodec": "none",
            "acodec": "mp4a.40.5",
            "tem_video": false,
            "tem_audio": true,
            "tbr": 48.889,
            "tamanho_bytes": 397606
          },
          "... mais 38 formatos omitidos neste exemplo ..."
        ]
      },
      "baixados": {}
    },
    {
      "ok": true,
      "original": "https://vimeo.com/123456789",
      "url": "https://vimeo.com/123456789",
      "e_youtube": false,
      "aviso": "Link fora do YouTube: o download pode funcionar, mas a deduplicação e o histórico só reconhecem este endereço se ele for colado exatamente igual.",
      "video": {
        "id": "123456789",
        "extractor": "Vimeo",
        "url_canonica": "https://vimeo.com/123456789",
        "titulo": "Exemplo simulado de outro site",
        "canal": "alguem",
        "duracao_s": 120,
        "thumbnail": null,
        "data_upload": null,
        "qualidades": [],
        "formatos": []
      },
      "baixados": {}
    },
    {
      "ok": false,
      "original": "não é um link",
      "url": null,
      "erro": "Não é um link válido: 'não é um link'",
      "motivo": "link_invalido"
    }
  ]
}
```

### POST /api/fila

`200`

```json
{
  "ids": [
    "bbfb01ebf24c448b815c99bfd388e670"
  ]
}
```

### GET /api/fila — durante o download

`200`

```json
{
  "jobs": [
    {
      "id": "bbfb01ebf24c448b815c99bfd388e670",
      "estado": "baixando",
      "perfil": "edicao_1080",
      "projeto": "pessoal",
      "criado_em": "2026-09-02T18:55:47+00:00",
      "video": {
        "id": "LzS8kB6lIm0",
        "titulo": "Camisa azul da Seleção: críticas ao design e lembrança histórica",
        "canal": "Canal Michuruca",
        "duracao_s": 65,
        "thumbnail": "https://i.ytimg.com/vi/LzS8kB6lIm0/maxresdefault.jpg"
      },
      "progresso": {
        "baixados": 3670016,
        "total": 9437184,
        "percentual": 38.88888888888889,
        "velocidade_bps": 3276800.0,
        "eta_s": 2
      },
      "caminho_final": null,
      "motivo_falha": null,
      "mensagem_falha": null,
      "aviso": null
    }
  ]
}
```

### POST /api/fila — mesmo vídeo e perfil já na fila (409)

`409`

```json
{
  "erro": "Este vídeo já está na fila no perfil 'edicao_1080'."
}
```

### POST /api/fila — perfil inexistente (400)

`400`

```json
{
  "erro": "Perfil 'nao_existe' não existe."
}
```

### POST /api/fila — corpo malformado (422)

`422`

```json
{
  "erro": "Corpo ou parâmetros inválidos.",
  "detalhes": [
    {
      "type": "list_type",
      "loc": [
        "body",
        "urls"
      ],
      "msg": "Input should be a valid list",
      "input": "isso deveria ser uma lista"
    },
    {
      "type": "missing",
      "loc": [
        "body",
        "perfil"
      ],
      "msg": "Field required",
      "input": {
        "urls": "isso deveria ser uma lista"
      }
    },
    {
      "type": "missing",
      "loc": [
        "body",
        "projeto"
      ],
      "msg": "Field required",
      "input": {
        "urls": "isso deveria ser uma lista"
      }
    }
  ]
}
```

### DELETE /api/fila/{id} — job ainda na fila

`200`

```json
{
  "cancelado": true
}
```

### DELETE /api/fila/{id} — job em andamento (409)

`409`

```json
{
  "erro": "Só é possível cancelar um job que ainda não começou (SPEC 10.5)."
}
```

### DELETE /api/fila/{id} — inexistente (404)

`404`

```json
{
  "erro": "Job 'nao-existe' não existe."
}
```

### GET /api/fila — depois: um concluído, um cancelado

`200`

```json
{
  "jobs": [
    {
      "id": "bbfb01ebf24c448b815c99bfd388e670",
      "estado": "concluido",
      "perfil": "edicao_1080",
      "projeto": "pessoal",
      "criado_em": "2026-09-02T18:55:47+00:00",
      "video": {
        "id": "LzS8kB6lIm0",
        "titulo": "Camisa azul da Seleção: críticas ao design e lembrança histórica",
        "canal": "Canal Michuruca",
        "duracao_s": 65,
        "thumbnail": "https://i.ytimg.com/vi/LzS8kB6lIm0/maxresdefault.jpg"
      },
      "progresso": {
        "baixados": 9437184,
        "total": 9437184,
        "percentual": 100.0,
        "velocidade_bps": null,
        "eta_s": 0
      },
      "caminho_final": "D:\\FOOTAGE\\pessoal\\20260901 - Camisa azul da Seleção críticas ao design e lembrança histórica [LzS8kB6lIm0].mp4",
      "motivo_falha": null,
      "mensagem_falha": null,
      "aviso": null
    },
    {
      "id": "aecac92461fd496bab33a3db2b082522",
      "estado": "cancelado",
      "perfil": "so_audio",
      "projeto": "pessoal",
      "criado_em": "2026-09-02T18:55:47+00:00",
      "video": {
        "id": "LzS8kB6lIm0",
        "titulo": "Camisa azul da Seleção: críticas ao design e lembrança histórica",
        "canal": "Canal Michuruca",
        "duracao_s": 65,
        "thumbnail": "https://i.ytimg.com/vi/LzS8kB6lIm0/maxresdefault.jpg"
      },
      "progresso": null,
      "caminho_final": null,
      "motivo_falha": null,
      "mensagem_falha": null,
      "aviso": null
    }
  ]
}
```

### GET /api/historico

`200`

```json
{
  "registros": [
    {
      "id": 1,
      "extractor": "Youtube",
      "video_id": "LzS8kB6lIm0",
      "perfil": "edicao_1080",
      "url_original": "https://youtube.com/shorts/LzS8kB6lIm0?si=0RP8BxS-q-XGH4Dw",
      "url_canonica": "https://www.youtube.com/watch?v=LzS8kB6lIm0",
      "titulo": "Camisa azul da Seleção: críticas ao design e lembrança histórica",
      "canal": "Canal Michuruca",
      "duracao_s": 65,
      "projeto": "pessoal",
      "caminho": "D:\\FOOTAGE\\pessoal\\20260901 - Camisa azul da Seleção críticas ao design e lembrança histórica [LzS8kB6lIm0].mp4",
      "tamanho_bytes": 9437184,
      "resolucao": "1080x1920",
      "status": "concluido",
      "motivo_falha": null,
      "mensagem_falha": null,
      "criado_em": "2026-09-02T18:55:47+00:00",
      "concluido_em": "2026-09-02T18:55:47+00:00"
    }
  ]
}
```

### GET /api/historico?termo=selecao&projeto=pessoal

`200`

```json
{
  "registros": [
    {
      "id": 1,
      "extractor": "Youtube",
      "video_id": "LzS8kB6lIm0",
      "perfil": "edicao_1080",
      "url_original": "https://youtube.com/shorts/LzS8kB6lIm0?si=0RP8BxS-q-XGH4Dw",
      "url_canonica": "https://www.youtube.com/watch?v=LzS8kB6lIm0",
      "titulo": "Camisa azul da Seleção: críticas ao design e lembrança histórica",
      "canal": "Canal Michuruca",
      "duracao_s": 65,
      "projeto": "pessoal",
      "caminho": "D:\\FOOTAGE\\pessoal\\20260901 - Camisa azul da Seleção críticas ao design e lembrança histórica [LzS8kB6lIm0].mp4",
      "tamanho_bytes": 9437184,
      "resolucao": "1080x1920",
      "status": "concluido",
      "motivo_falha": null,
      "mensagem_falha": null,
      "criado_em": "2026-09-02T18:55:47+00:00",
      "concluido_em": "2026-09-02T18:55:47+00:00"
    }
  ]
}
```

### POST /api/inspecionar — depois de baixado: `baixados` preenchido

`200`

```json
{
  "itens": [
    {
      "ok": true,
      "original": "https://youtube.com/shorts/LzS8kB6lIm0?si=0RP8BxS-q-XGH4Dw",
      "url": "https://www.youtube.com/watch?v=LzS8kB6lIm0",
      "e_youtube": true,
      "aviso": null,
      "video": {
        "id": "LzS8kB6lIm0",
        "extractor": "Youtube",
        "url_canonica": "https://www.youtube.com/watch?v=LzS8kB6lIm0",
        "titulo": "Camisa azul da Seleção: críticas ao design e lembrança histórica",
        "canal": "Canal Michuruca",
        "duracao_s": 65,
        "thumbnail": "https://i.ytimg.com/vi/LzS8kB6lIm0/maxresdefault.jpg",
        "data_upload": "20260901",
        "qualidades": [
          144,
          240,
          360,
          480,
          608,
          720,
          1080
        ],
        "formatos": [
          {
            "format_id": "233",
            "ext": "mp4",
            "resolucao": "audio only",
            "largura": null,
            "altura": null,
            "fps": null,
            "vcodec": "none",
            "acodec": null,
            "tem_video": false,
            "tem_audio": true,
            "tbr": null,
            "tamanho_bytes": null
          },
          {
            "format_id": "234",
            "ext": "mp4",
            "resolucao": "audio only",
            "largura": null,
            "altura": null,
            "fps": null,
            "vcodec": "none",
            "acodec": null,
            "tem_video": false,
            "tem_audio": true,
            "tbr": null,
            "tamanho_bytes": null
          },
          {
            "format_id": "139-drc",
            "ext": "m4a",
            "resolucao": "audio only",
            "largura": null,
            "altura": null,
            "fps": null,
            "vcodec": "none",
            "acodec": "mp4a.40.5",
            "tem_video": false,
            "tem_audio": true,
            "tbr": 48.889,
            "tamanho_bytes": 397606
          },
          "... mais 38 formatos omitidos neste exemplo ..."
        ]
      },
      "baixados": {
        "edicao_1080": {
          "caminho": "D:\\FOOTAGE\\pessoal\\20260901 - Camisa azul da Seleção críticas ao design e lembrança histórica [LzS8kB6lIm0].mp4",
          "projeto": "pessoal",
          "resolucao": "1080x1920",
          "concluido_em": "2026-09-02T18:55:47+00:00"
        }
      }
    }
  ]
}
```

### POST /api/fila — já baixado neste perfil (409)

`409`

```json
{
  "erro": "Já baixado no perfil 'edicao_1080': D:\\FOOTAGE\\pessoal\\20260901 - Camisa azul da Seleção críticas ao design e lembrança histórica [LzS8kB6lIm0].mp4. Use forcar=true para baixar de novo."
}
```
