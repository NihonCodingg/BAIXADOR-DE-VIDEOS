# CLAUDE.md — Convenções do projeto

Instruções permanentes para qualquer sessão de trabalho neste repositório.

> Este arquivo cresce ao longo do projeto. A Fase 4 acrescenta as convenções de
> arquitetura, testes e fluxo de trabalho por ticket. Por ora, só versionamento.

## Versionamento

- Commit + push ao concluir cada ticket, com a suíte de testes passando. Nunca
  commitar com teste falhando.
- Se um ticket tiver partes distintas (implementação, testes, documentação),
  fazer commits separados. Commits menores e mais frequentes são preferíveis a
  um commit grande no fim.
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
