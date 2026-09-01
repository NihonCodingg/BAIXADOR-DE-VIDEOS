// Baixador de Footage. JS puro, sem framework, sem build. Ticket T7.
//
// Polling de 1s e não WebSocket: um usuário, uma aba (SPEC 12).

'use strict';

const INTERVALO_POLLING_MS = 1000;

// GET  /api/config       -> perfis, projetos, status do ffmpeg
// POST /api/inspecionar  -> metadados sem baixar
// POST /api/fila         -> enfileira
// GET  /api/fila         -> estado atual
// DELETE /api/fila/{id}  -> cancela
// GET  /api/historico    -> busca e filtro

// T7
