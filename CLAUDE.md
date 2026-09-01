# CLAUDE.md — Convenções do projeto

Instruções permanentes para qualquer sessão de trabalho neste repositório.

Documentos de referência: [SPEC.md](SPEC.md) é normativo, [RESEARCH.md](RESEARCH.md)
é a base factual, [PLAN.md](PLAN.md) tem os tickets.

---

## Contexto

Ferramenta local de download de footage para edição de vídeo. Usuário único, na
própria máquina.

O autor é desenvolvedor iniciante (2º semestre de ADS) e editor de vídeo
profissional. Ele quer **aprender** a parte Python: arquitetura, testes e
concorrência. Explique o "porquê" das decisões, em português. Prefira a solução
mais simples que resolve — não venda arquitetura que o projeto não precisa.

Decisões sobre qualidade de vídeo e codec são território dele. Decisões de
Python são onde ele quer aprender.

---

## Fluxo de trabalho

### Um ticket por sessão

- **Um ticket por sessão**, com `/clear` entre elas.
- Ao final de cada ticket: rodar a suíte inteira e mostrar o resultado.
- Commit + push ao concluir, com a suíte passando.

### T2, T3 e T5 exigem TDD com confirmação

Nestes três tickets:

1. Escrever os testes **antes** da implementação
2. **Mostrar a lista de casos de borda ao autor**
3. **Esperar a confirmação dele** antes de implementar

Não é sugestão. É o ponto do projeto: são os tickets onde mora a lógica de
domínio, e é onde ele quer aprender.

### Testes

- **NENHUM teste pode tocar a rede.** Sem exceção.
- Metadados vêm de `spike_meta.json`, capturado uma vez pelo `spike.py`.
- A fila é testada com `DownloaderFalso` (`tests/conftest.py`).
- Rodar tudo: `python -m pytest tests/ -v`

---

## Arquitetura

### As duas regras duras

**REGRA 1** — `src/domain/` nunca importa de `src/download/`, `src/storage/` ou
`src/queue/`.

**REGRA 2** — `src/web/` nunca importa de `src/domain/`. Ele fala com
`src/pipeline.py`.

Garantidas por `tests/test_arquitetura.py`, que analisa a árvore com `ast` e
quebra o build. Não é comentário decorativo — foi verificado que ele falha
quando violado.

### O domínio é puro

Sem rede, sem disco, sem `yt_dlp`. Quando precisar de I/O, **injete a
dependência** em vez de importar. Modelo:
`resolver_colisao(caminho, existe)` recebe a checagem de existência como
callable.

### Só `src/download/` conhece o yt-dlp

`import yt_dlp` fora de `src/download/` quebra o build.

### Onde colocar coisa nova

Antes de criar um módulo, o critério do SPEC 5: *o yt-dlp já resolve isso?* Se
sim, não é domínio. Se resolve parcialmente, o que falta é domínio. O risco
central do projeto é o domínio virar wrapper vazio.

---

## Convenções de código

- Nomes de identificador e comentários em **português**, seguindo o que já
  existe. Não misturar idiomas dentro de um módulo.
- Docstring de módulo diz **o quê** e cita a seção do SPEC ou do RESEARCH que
  justifica.
- Todo stub referencia o ticket: `raise NotImplementedError("T3")`.
- Type hints em assinaturas públicas.
- Sem dependência nova sem justificativa em `requirements.txt`. Se não dá para
  justificar em uma linha, não entra.

### Duas armadilhas do Windows já conhecidas

Ambas medidas e documentadas em RESEARCH §7:

1. **Console é cp1252.** Todo entry point que imprime título de vídeo precisa de
   `sys.stdout.reconfigure(encoding="utf-8")`. Sem isso: `UnicodeEncodeError`.
2. **`NUL` engole dados em silêncio.** Gravar em arquivo com nome reservado do
   DOS não levanta erro e os bytes somem. Sanitização é correção, não estilo.

### O progress hook

- Pode ser chamado de **outra thread** (RESEARCH §3.4). Sempre tratar como tal.
- Dispara muitas vezes por segundo: **nenhuma I/O** dentro dele. Sem SQLite, sem
  `print`.
- Toda chave do dicionário é opcional: `d.get('speed')`, nunca `d['speed']`. Um
  `KeyError` ali derruba o download inteiro.

---

## O front-end não é desenhado aqui

A interface visual é feita no **Claude Design**, a partir do `CONTRATO-API.md`
que o T6 produz. O papel deste repositório no T7 é **integrar e corrigir**:
polling, estados, tratamento de erro e divergências com o contrato real.

Não redesenhar cores, tipografia ou layout. Mexer no visual só para corrigir
defeito funcional.

## Escopo

Está em [SPEC.md §2.2](SPEC.md). Fora de escopo **em definitivo**: contorno de
DRM ou paywall, download em massa de canais, upload ou redistribuição,
multiusuário/autenticação/deploy.

Pedido nesse sentido em sessão futura: recusar e citar o SPEC.

---

## Versionamento

### A regra geral

- Commit + push ao concluir cada ticket, com a suíte de testes passando.
- Se um ticket tiver partes distintas (implementação, testes, documentação),
  fazer commits separados. Commits menores e mais frequentes são preferíveis a
  um commit grande no fim.

### Em ciclo TDD (T2, T3, T5)

O que a regra "nunca commitar com teste falhando" protege é o **remoto**, não o
commit local. Um commit local vermelho é o registro do ciclo TDD, e vê-lo é
parte do objetivo de aprendizado deste projeto.

1. **Commit dos testes** — vermelho, com a mensagem deixando claro que os
   testes ainda não passam.
2. **Commit da implementação** — verde.
3. **`git push` SOMENTE depois do verde**, com a suíte inteira passando.

**O remoto nunca fica quebrado.** Se a implementação não terminar na sessão, o
commit vermelho fica local e não sobe.

Fora de ciclo TDD, vale a regra geral acima: commit + push ao concluir.
- Formato da mensagem: prefixo do ticket, dois pontos, descrição objetiva em
  português.

  Exemplos:

  ```
  T3: sanitização de nomes de arquivo para Windows
  T3: testes de borda (caractere proibido, nome longo, título vazio)
  T5: worker da fila com um download por vez
  ```

- Sem emoji nas mensagens. Sem "update", "wip" ou "ajustes".
- Antes de todo commit: rodar `git status` e mostrar ao autor a lista do que
  será commitado. Esperar aprovação explícita.
- Antes de todo commit: confirmar que nenhum vídeo, banco de dados, `.env` ou
  arquivo binário está na lista.
- Nunca usar `git push --force`. Nunca reescrever histórico.
- Nunca criar commit vazio ou commit sem mudança real de conteúdo.
