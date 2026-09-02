/* ============================================================
   BAIXADOR DE FOOTAGE — app.js
   JavaScript puro, sem dependências.

   Sumário:
     1. Constantes e utilidades
     2. Formatação (a API entrega valores crus)
     3. Camada de API  (fetch + fallback de demonstração)
     4. Estado da aplicação
     5. Boot / config
     6. Entrada e inspeção
     7. Preview
     8. Fila (render incremental + polling de 1s)
     9. Histórico
    10. Toasts
    11. SERVIDOR DE DEMONSTRAÇÃO (só roda se a API real não responder)
   ============================================================ */

'use strict';

/* ------------------------------------------------------------
   1. CONSTANTES E UTILIDADES
   ------------------------------------------------------------ */

var INTERVALO_POLLING = 1000;         // contrato: 1 s
var LIMITE_HISTORICO = 100;
var CHAVE_ESCOLHAS = 'footage.escolhas';   // último perfil/projeto usados
var CHAVE_RASCUNHO = 'footage.rascunho';   // texto da caixa de links

function $(sel) { return document.querySelector(sel); }

/* escapa texto antes de entrar em innerHTML (títulos têm caracteres livres) */
function esc(v) {
  if (v === null || v === undefined) return '';
  return String(v)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function debounce(fn, ms) {
  var t;
  return function () {
    var args = arguments, self = this;
    clearTimeout(t);
    t = setTimeout(function () { fn.apply(self, args); }, ms);
  };
}

/* ícones dos selos de estado: forma distinta para cada estado,
   para não depender só de cor */
var ICONES = {
  na_fila:      '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="6" cy="6" r="4.6"/><path d="M6 3.4V6l2 1.4"/></svg>',
  baixando:     '<svg viewBox="0 0 12 12" fill="currentColor"><path d="M6 1v6.2l2.4-2.4 1 1L6 9.4 2.6 5.8l1-1L6 7.2V1z"/><rect x="1.6" y="10.2" width="8.8" height="1.4" rx=".7"/></svg>',
  concluido:    '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2"><path d="M1.6 6.4 4.6 9.4 10.4 2.8"/></svg>',
  falhou:       '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2"><path d="M2.4 2.4l7.2 7.2M9.6 2.4 2.4 9.6"/></svg>',
  cancelado:    '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="6" cy="6" r="4.6"/><path d="M2.9 9.1 9.1 2.9"/></svg>',
  interrompido: '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M6 1.4 11.2 10.6H.8z"/><path d="M6 4.6v2.6M6 8.8v.6"/></svg>'
};

var ROTULO_ESTADO = {
  na_fila: 'Na fila',
  baixando: 'Baixando',
  concluido: 'Concluído',
  falhou: 'Falhou',
  cancelado: 'Cancelado',
  interrompido: 'Interrompido'
};

/* motivos que valem uma nova tentativa (contrato §5) */
var MOTIVOS_RETENTAVEIS = { rede: true, rate_limit: true };

function selo(est) {
  return '<span class="selo" data-estado="' + esc(est) + '">' +
    (ICONES[est] || '') + esc(ROTULO_ESTADO[est] || est) + '</span>';
}

/* ------------------------------------------------------------
   2. FORMATAÇÃO
   ------------------------------------------------------------ */

/* 65 -> "1:05" ; 3725 -> "1:02:05" ; null -> "--:--" */
function fmtDuracao(s) {
  if (s === null || s === undefined) return '--:--';
  s = Math.round(s);
  var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), seg = s % 60;
  var mm = h > 0 ? String(m).padStart(2, '0') : String(m);
  return (h > 0 ? h + ':' : '') + mm + ':' + String(seg).padStart(2, '0');
}

function num(v, casas) {
  return v.toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

/* 9437184 -> "9,0 MB" ; null -> "--" */
function fmtBytes(b) {
  if (b === null || b === undefined) return '--';
  var un = ['B', 'KB', 'MB', 'GB', 'TB'], i = 0, v = b;
  while (v >= 1024 && i < un.length - 1) { v /= 1024; i++; }
  return num(v, i === 0 ? 0 : 1) + ' ' + un[i];
}

function fmtVelocidade(bps) {
  if (bps === null || bps === undefined) return '--';
  return fmtBytes(bps) + '/s';
}

function fmtPercentual(p) {
  if (p === null || p === undefined) return null;
  return Math.round(p);
}

/* ISO-8601 UTC -> data/hora local */
function fmtDataHora(iso) {
  if (!iso) return '--';
  var d = new Date(iso);
  if (isNaN(d)) return '--';
  return d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' });
}

/* "20260901" -> "01/09/2026" */
function fmtDataUpload(s) {
  if (!s || s.length !== 8) return null;
  return s.slice(6, 8) + '/' + s.slice(4, 6) + '/' + s.slice(0, 4);
}

/* ------------------------------------------------------------
   3. CAMADA DE API
   Uma função só. Se a API real não responder (página aberta sem o
   servidor Python atrás), cai no servidor de demonstração da seção 11
   para a interface continuar navegável. Ponha DEMO_PERMITIDO = false
   para exigir a API real.
   ------------------------------------------------------------ */

var DEMO_PERMITIDO = true;
var usandoDemo = false;

function api(metodo, caminho, corpo) {
  if (usandoDemo) return Demo.chamar(metodo, caminho, corpo);

  var opcoes = { method: metodo, headers: { 'Accept': 'application/json' } };
  if (corpo !== undefined) {
    opcoes.headers['Content-Type'] = 'application/json';
    opcoes.body = JSON.stringify(corpo);
  }

  return fetch(caminho, opcoes).then(function (r) {
    var tipo = r.headers.get('content-type') || '';
    // página aberta sem a API atrás: o servidor de arquivos responde HTML/404
    if (tipo.indexOf('json') === -1) return semApi(metodo, caminho, corpo);
    return r.json().catch(function () { return {}; }).then(function (dados) {
      if (r.ok) return dados;
      // erro sempre na mesma forma: {erro: "..."} (+ detalhes no 422)
      if (r.status === 422 && dados.detalhes) console.warn('422 detalhes:', dados.detalhes);
      var e = new Error(dados.erro || 'Erro ' + r.status);
      e.status = r.status;
      e.detalhes = dados.detalhes || null;
      throw e;
    });
  }, function (falhaRede) {
    return semApi(metodo, caminho, corpo, falhaRede);
  });
}

/* sem API real: cai na demonstração (se permitida) ou avisa */
function semApi(metodo, caminho, corpo, causa) {
  if (DEMO_PERMITIDO) {
    if (!usandoDemo) {
      usandoDemo = true;
      console.info('API real não respondeu — usando dados de demonstração.', causa || '');
    }
    return Demo.chamar(metodo, caminho, corpo);
  }
  var e = new Error('A API em 127.0.0.1:8000 não respondeu.');
  e.status = 0;
  return Promise.reject(e);
}

/* ------------------------------------------------------------
   4. ESTADO
   ------------------------------------------------------------ */

var estado = {
  config: null,
  preview: [],        // itens de /api/inspecionar + escolhas locais
  jobs: [],
  historico: [],
  urlPorJob: {},      // id do job -> url enviada (para "tentar de novo")
  pollAtivo: false,
  pollEmVoo: false,
  escolhas: { perfil: null, projeto: null }
};

var nosJob = {};      // cache de nós DOM da fila, por id, para atualizar sem recriar

function lerEscolhas() {
  try {
    var v = JSON.parse(localStorage.getItem(CHAVE_ESCOLHAS) || '{}');
    if (v && typeof v === 'object') estado.escolhas = { perfil: v.perfil || null, projeto: v.projeto || null };
  } catch (e) { /* ignora */ }
}
function salvarEscolhas() {
  try { localStorage.setItem(CHAVE_ESCOLHAS, JSON.stringify(estado.escolhas)); } catch (e) {}
}

/* ------------------------------------------------------------
   5. BOOT / CONFIG
   ------------------------------------------------------------ */

function iniciar() {
  lerEscolhas();

  // rascunho da caixa de links sobrevive a um reload
  try {
    var r = localStorage.getItem(CHAVE_RASCUNHO);
    if (r) $('#campo-links').value = r;
  } catch (e) {}
  atualizarContadorLinks();

  ligarEventos();
  renderPreview();
  renderFila();
  renderHistorico();

  api('GET', '/api/config').then(aplicarConfig).then(function () {
    carregarHistorico();
    atualizarFila();          // a fila é da sessão, mas pode haver job vivo
  }).catch(function (e) {
    toast(e.message, 'erro');
  });
}

function aplicarConfig(cfg) {
  estado.config = cfg;

  // ffmpeg
  var f = cfg.ffmpeg || {};
  var pill = $('#pill-ffmpeg');
  pill.textContent = 'ffmpeg ' + (f.disponivel ? (f.completo ? 'ok' : 'parcial') : 'ausente');
  pill.dataset.tone = f.disponivel ? (f.completo ? 'ok' : 'neutral') : 'erro';
  pill.title = f.disponivel ? (f.ffmpeg || '') + (f.ffprobe ? '\n' + f.ffprobe : '') : 'não encontrado no sistema';

  if (!f.disponivel) {
    $('#banner-ffmpeg').hidden = false;
  } else if (!f.completo) {
    $('#banner-ffmpeg').hidden = false;
    $('#banner-ffmpeg-msg').textContent = 'ffprobe não foi encontrado. Alguns perfis podem falhar.';
  }

  // selects em lote
  preencherPerfis($('#lote-perfil'), estado.escolhas.perfil);
  preencherProjetos($('#lote-projeto'), estado.escolhas.projeto);

  // filtro de projeto do histórico
  var filtro = $('#filtro-projeto');
  filtro.innerHTML = '<option value="">Todos os projetos</option>' +
    (cfg.projetos || []).map(function (p) {
      return '<option value="' + esc(p.nome) + '">' + esc(p.rotulo) + '</option>';
    }).join('');
}

function preencherPerfis(sel, escolhido) {
  var perfis = (estado.config && estado.config.perfis) || [];
  sel.innerHTML = perfis.map(function (p) {
    var motivo = p.disponivel ? '' : ' — exige ffmpeg';
    return '<option value="' + esc(p.nome) + '"' + (p.disponivel ? '' : ' disabled') + '>' +
      esc(p.descricao) + esc(motivo) + '</option>';
  }).join('');
  var alvo = escolhido || primeiroValido(perfis, 'disponivel');
  if (alvo) sel.value = alvo;
}

function preencherProjetos(sel, escolhido) {
  var projetos = (estado.config && estado.config.projetos) || [];
  sel.innerHTML = projetos.map(function (p) {
    var motivo = p.valido ? '' : ' — ' + (p.motivo || 'indisponível');
    return '<option value="' + esc(p.nome) + '"' + (p.valido ? '' : ' disabled') + ' title="' + esc(p.pasta) + '">' +
      esc(p.rotulo) + esc(motivo) + '</option>';
  }).join('');
  var alvo = escolhido || primeiroValido(projetos, 'valido');
  if (alvo) sel.value = alvo;
}

function primeiroValido(lista, campo) {
  for (var i = 0; i < lista.length; i++) if (lista[i][campo]) return lista[i].nome;
  return lista.length ? lista[0].nome : null;
}

function perfilPorNome(nome) {
  var l = (estado.config && estado.config.perfis) || [];
  for (var i = 0; i < l.length; i++) if (l[i].nome === nome) return l[i];
  return null;
}
function projetoPorNome(nome) {
  var l = (estado.config && estado.config.projetos) || [];
  for (var i = 0; i < l.length; i++) if (l[i].nome === nome) return l[i];
  return null;
}
function rotuloProjeto(nome) { var p = projetoPorNome(nome); return p ? p.rotulo : nome; }

/* ------------------------------------------------------------
   6. ENTRADA E INSPEÇÃO
   ------------------------------------------------------------ */

function linhasDeLinks() {
  return $('#campo-links').value.split('\n')
    .map(function (l) { return l.trim(); })
    .filter(function (l) { return l.length > 0; })
    .filter(function (l, i, a) { return a.indexOf(l) === i; });
}

function atualizarContadorLinks() {
  var n = linhasDeLinks().length;
  $('#contador-links').textContent = n === 0 ? 'nenhum link' : n + (n === 1 ? ' link' : ' links');
  $('#btn-inspecionar').disabled = n === 0;
  try { localStorage.setItem(CHAVE_RASCUNHO, $('#campo-links').value); } catch (e) {}
}

function inspecionar() {
  var texto = $('#campo-links').value;
  if (!linhasDeLinks().length) return;

  $('#btn-inspecionar').disabled = true;
  // a chamada espera a rede: mostra carregamento
  $('#lista-preview').innerHTML = '<div class="carregando">Consultando ' +
    linhasDeLinks().length + ' link(s)…</div>';
  $('#contador-preview').textContent = '';
  $('#lote').hidden = true;

  api('POST', '/api/inspecionar', { links: texto }).then(function (r) {
    estado.preview = (r.itens || []).map(function (item) {
      return {
        item: item,
        perfil: $('#lote-perfil').value || null,
        projeto: $('#lote-projeto').value || null,
        forcar: false,
        enfileirado: false
      };
    });
    renderPreview();
  }).catch(function (e) {
    estado.preview = [];
    renderPreview();
    toast(e.message, 'erro');
  }).then(function () {
    $('#btn-inspecionar').disabled = linhasDeLinks().length === 0;
  });
}

/* ------------------------------------------------------------
   7. PREVIEW
   ------------------------------------------------------------ */

function renderPreview() {
  var alvo = $('#lista-preview');
  var lista = estado.preview;

  if (!lista.length) {
    $('#lote').hidden = true;
    $('#contador-preview').textContent = '';
    alvo.innerHTML = vazio('Nada inspecionado',
      'Cole os links acima e clique em Inspecionar. Os metadados aparecem aqui antes de qualquer download.');
    return;
  }

  var validos = lista.filter(function (p) { return p.item.ok && !p.enfileirado; }).length;
  $('#lote').hidden = false;
  $('#btn-enfileirar-todos').disabled = validos === 0;
  $('#btn-enfileirar-todos').textContent = 'Enfileirar todos' + (validos ? ' (' + validos + ')' : '');
  $('#contador-preview').textContent = lista.length + ' item(ns)';

  alvo.innerHTML = lista.map(function (p, i) {
    return p.item.ok ? cartaoVideo(p, i) : cartaoErro(p.item, i);
  }).join('');
  preencherSelectsPreview();
}

function cartaoErro(item, i) {
  return '' +
    '<article class="cartao cartao--erro" data-i="' + i + '">' +
      '<div class="cartao__topo">' +
        '<div class="cartao__info">' +
          '<div class="row row--gap">' + selo('falhou') +
            '<span class="tag">' + esc(item.motivo || 'desconhecido') + '</span></div>' +
          '<p class="falha__msg">' + esc(item.erro) + '</p>' +
          '<p class="caminho">' + esc(item.original) + '</p>' +
        '</div>' +
      '</div>' +
    '</article>';
}

function cartaoVideo(p, i) {
  var v = p.item.video || {};
  var perfilSel = p.perfil;
  var jaBaixado = (p.item.baixados || {})[perfilSel] || null;
  var dataUp = fmtDataUpload(v.data_upload);
  var maxQual = (v.qualidades && v.qualidades.length) ? Math.max.apply(null, v.qualidades) : null;

  var html = '<article class="cartao" data-i="' + i + '">';

  // topo: thumbnail + identificação
  html += '<div class="cartao__topo">';
  html += '<div class="thumb' + (v.thumbnail ? '' : ' thumb--vazia') + '">' +
    (v.thumbnail
      ? '<img src="' + esc(v.thumbnail) + '" alt="" loading="lazy" ' +
        'onerror="this.remove(); this.parentNode.classList.add(\'thumb--vazia\')">'
      : '') +
    '<span class="thumb__dur mono">' + fmtDuracao(v.duracao_s) + '</span>' +
    '</div>';

  html += '<div class="cartao__info">';
  html += '<h3 class="titulo" title="' + esc(v.titulo) + '">' + esc(v.titulo) + '</h3>';
  html += '<div class="meta">' +
    '<span class="meta__canal">' + esc(v.canal || 'canal desconhecido') + '</span>' +
    (dataUp ? '<span class="meta__sep">/</span><span class="mono">' + esc(dataUp) + '</span>' : '') +
    '<span class="meta__sep">/</span><span class="mono">' + esc(v.extractor || '') + '</span>' +
    '</div>';

  if (v.qualidades && v.qualidades.length) {
    html += '<div class="quals">' + v.qualidades.map(function (q) {
      return '<span class="qual' + (q === maxQual ? ' qual--max' : '') + '">' + q + 'p</span>';
    }).join('') + '</div>';
  } else {
    html += '<div class="quals"><span class="qual">qualidades não informadas</span></div>';
  }
  html += '</div></div>';

  // escolhas por vídeo
  html += '<div class="cartao__acoes">' +
    '<label class="field field--inline"><span class="field__label">Perfil</span>' +
      '<select class="select" data-acao="perfil" data-i="' + i + '"></select></label>' +
    '<label class="field field--inline"><span class="field__label">Projeto</span>' +
      '<select class="select" data-acao="projeto" data-i="' + i + '"></select></label>' +
    '<button class="btn ' + (p.enfileirado ? 'btn--ghost' : 'btn--primary') + '" data-acao="enfileirar" data-i="' + i + '"' +
      (p.enfileirado ? ' disabled' : '') + '>' +
      (p.enfileirado ? 'Na fila' : (jaBaixado && !p.forcar ? 'Enfileirar' : 'Enfileirar')) + '</button>' +
    '</div>';

  // aviso de site fora do YouTube — visível, não escondido
  if (p.item.aviso) {
    html += '<div class="nota nota--aviso">' +
      '<span class="nota__tag">Fora do YouTube</span>' +
      '<span class="nota__corpo">' + esc(p.item.aviso) + '</span></div>';
  }

  // duplicata para o perfil escolhido
  if (jaBaixado) {
    html += '<div class="nota nota--dup">' +
      '<span class="nota__tag">Já baixado</span>' +
      '<span class="nota__corpo">' +
        '<span class="caminho">' + esc(jaBaixado.caminho) + '</span><br>' +
        esc(rotuloProjeto(jaBaixado.projeto)) + ' / ' + esc(jaBaixado.resolucao || '--') +
        ' / ' + esc(fmtDataHora(jaBaixado.concluido_em)) +
      '</span>' +
      '<button class="btn btn--mini' + (p.forcar ? ' btn--primary' : '') + '" data-acao="forcar" data-i="' + i + '">' +
        (p.forcar ? 'Vai baixar de novo' : 'Baixar de novo') + '</button>' +
      '</div>';
  }

  html += '</article>';
  return html;
}

/* os <select> de cada cartão são preenchidos após o innerHTML,
   para reaproveitar as mesmas funções de preenchimento */
function preencherSelectsPreview() {
  var selects = $('#lista-preview').querySelectorAll('select[data-acao]');
  for (var k = 0; k < selects.length; k++) {
    var s = selects[k], p = estado.preview[Number(s.dataset.i)];
    if (!p) continue;
    if (s.dataset.acao === 'perfil') preencherPerfis(s, p.perfil);
    else preencherProjetos(s, p.projeto);
    p[s.dataset.acao] = s.value;
  }
}

function enfileirar(indices) {
  var itens = indices.map(function (i) { return estado.preview[i]; })
    .filter(function (p) { return p && p.item.ok && !p.enfileirado; });
  if (!itens.length) return;

  // /api/fila aceita um perfil e um projeto por chamada:
  // agrupa por (perfil, projeto, forcar)
  var grupos = {};
  itens.forEach(function (p) {
    var chave = p.perfil + '|' + p.projeto + '|' + (p.forcar ? 1 : 0);
    (grupos[chave] = grupos[chave] || []).push(p);
  });

  Object.keys(grupos).forEach(function (chave) {
    var grupo = grupos[chave];
    var partes = chave.split('|');
    var corpo = {
      urls: grupo.map(function (p) { return p.item.url; }),
      perfil: partes[0],
      projeto: partes[1],
      forcar: partes[2] === '1'
    };

    api('POST', '/api/fila', corpo).then(function (r) {
      // tudo ou nada: se voltou 200, todos entraram
      (r.ids || []).forEach(function (id, k) {
        if (grupo[k]) estado.urlPorJob[id] = grupo[k].item.url;
      });
      grupo.forEach(function (p) { p.enfileirado = true; });
      estado.escolhas.perfil = corpo.perfil;
      estado.escolhas.projeto = corpo.projeto;
      salvarEscolhas();
      renderPreview();
      preencherSelectsPreview();
      atualizarFila();
      ligarPolling();
      toast(grupo.length + (grupo.length === 1 ? ' job na fila' : ' jobs na fila'), 'ok');
    }).catch(function (e) {
      // 409 de "já baixado" ganha caminho de saída: marcar forcar e tentar de novo
      if (e.status === 409 && /forcar=true/i.test(e.message)) {
        grupo.forEach(function (p) { p.forcar = true; });
        renderPreview();
        preencherSelectsPreview();
        toast(e.message + ' Marquei "baixar de novo" — clique em Enfileirar outra vez.', 'erro');
      } else {
        toast(e.message, 'erro');
      }
    });
  });
}

/* ------------------------------------------------------------
   8. FILA
   Render incremental: cada job tem um nó reaproveitado, para a
   barra transicionar entre os passos do polling em vez de recriar.
   ------------------------------------------------------------ */

function atualizarFila() {
  if (estado.pollEmVoo) return;                 // nunca duas requisições juntas
  estado.pollEmVoo = true;
  return api('GET', '/api/fila').then(function (r) {
    estado.jobs = r.jobs || [];
    renderFila();
    ligarPolling();
  }).catch(function (e) {
    if (e.status !== 0) toast(e.message, 'erro');
  }).then(function () { estado.pollEmVoo = false; });
}

function ligarPolling() {
  var pendente = estado.jobs.some(function (j) {
    return j.estado === 'na_fila' || j.estado === 'baixando';
  });
  if (pendente && !estado.pollAtivo) {
    estado.pollAtivo = setInterval(atualizarFila, INTERVALO_POLLING);
  } else if (!pendente && estado.pollAtivo) {
    clearInterval(estado.pollAtivo);
    estado.pollAtivo = false;
    carregarHistorico();      // o que terminou já está no banco
  }
}

function renderFila() {
  var alvo = $('#lista-fila');
  var jobs = estado.jobs;

  // resumo no cabeçalho + pill do topo
  var cont = { na_fila: 0, baixando: 0, concluido: 0, falhou: 0, cancelado: 0 };
  jobs.forEach(function (j) { if (cont[j.estado] !== undefined) cont[j.estado]++; });
  var ativos = cont.na_fila + cont.baixando;
  $('#pill-fila').textContent = 'fila ' + ativos;
  $('#pill-fila').dataset.tone = cont.baixando ? 'ativo' : (cont.falhou ? 'erro' : 'neutral');
  $('#resumo-fila').textContent = jobs.length
    ? [cont.baixando + ' baixando', cont.na_fila + ' na fila', cont.concluido + ' ok', cont.falhou + ' falha'].join('  ·  ')
    : '';

  if (!jobs.length) {
    nosJob = {};
    alvo.innerHTML = vazio('Fila vazia',
      'Downloads acontecem um por vez, em sequência. O que você enfileirar aparece aqui com progresso ao vivo.');
    return;
  }

  if (alvo.firstElementChild && alvo.firstElementChild.classList.contains('vazio')) {
    alvo.innerHTML = '';
    nosJob = {};
  }

  var posicao = 0;
  var vistos = {};

  jobs.forEach(function (j) {
    if (j.estado === 'na_fila') posicao++;
    vistos[j.id] = true;
    var no = nosJob[j.id];
    if (!no) {
      no = document.createElement('article');
      no.className = 'job';
      no.dataset.id = j.id;
      nosJob[j.id] = no;
      alvo.appendChild(no);
    }
    atualizarNoJob(no, j, j.estado === 'na_fila' ? posicao : 0);
  });

  // jobs que sumiram (cancelados e removidos)
  Object.keys(nosJob).forEach(function (id) {
    if (!vistos[id]) { nosJob[id].remove(); delete nosJob[id]; }
  });
}

function atualizarNoJob(no, j, posicao) {
  var pr = j.progresso;
  var pct = pr ? fmtPercentual(pr.percentual) : null;

  // a estrutura só é reconstruída quando o estado muda
  if (no.dataset.estado !== j.estado) {
    no.dataset.estado = j.estado;
    no.innerHTML = estruturaJob(j, posicao);
  }

  var q = function (sel) { return no.querySelector(sel); };

  if (j.estado === 'na_fila') {
    var pos = q('[data-campo="posicao"]');
    if (pos) pos.textContent = posicao === 1 ? 'próximo da fila' : posicao + 'º da fila';
  }

  if (j.estado === 'baixando' || j.estado === 'concluido') {
    var barra = q('.barra'), fill = q('.barra__fill');
    if (barra) {
      barra.classList.toggle('barra--indet', pct === null);
      if (pct !== null) fill.style.width = pct + '%';
      barra.setAttribute('aria-valuenow', pct === null ? '' : pct);
    }
    var elPct = q('[data-campo="pct"]');
    if (elPct) elPct.innerHTML = pct === null ? '--<small>%</small>' : pct + '<small>%</small>';

    var elTam = q('[data-campo="tamanho"]');
    if (elTam && pr) elTam.textContent = fmtBytes(pr.baixados) + ' / ' + fmtBytes(pr.total);
    var elVel = q('[data-campo="velocidade"]');
    if (elVel && pr) elVel.textContent = fmtVelocidade(pr.velocidade_bps);
    var elEta = q('[data-campo="eta"]');
    if (elEta && pr) elEta.textContent = pr.eta_s === null || pr.eta_s === undefined ? '--' : fmtDuracao(pr.eta_s);
  }

  var avisoEl = q('[data-campo="aviso"]');
  if (avisoEl) {
    avisoEl.hidden = !j.aviso;
    if (j.aviso) avisoEl.querySelector('.nota__corpo').textContent = j.aviso;
  }
}

function estruturaJob(j, posicao) {
  var v = j.video || {};
  var html = '';

  html += '<div class="job__topo">';
  html += '<div class="thumb' + (v.thumbnail ? '' : ' thumb--vazia') + '">' +
    (v.thumbnail ? '<img src="' + esc(v.thumbnail) + '" alt="" loading="lazy" ' +
      'onerror="this.remove(); this.parentNode.classList.add(\'thumb--vazia\')">' : '') +
    '<span class="thumb__dur mono">' + fmtDuracao(v.duracao_s) + '</span></div>';

  html += '<div class="job__info">';
  html += '<div class="row row--gap">' + selo(j.estado) +
    '<span class="tag">' + esc(j.perfil) + '</span>' +
    '<span class="tag">' + esc(rotuloProjeto(j.projeto)) + '</span></div>';
  html += '<h3 class="titulo" title="' + esc(v.titulo) + '">' + esc(v.titulo) + '</h3>';
  html += '<div class="meta"><span class="meta__canal">' + esc(v.canal || 'canal desconhecido') + '</span>' +
    '<span class="meta__sep">/</span><span class="mono">' + esc(fmtDataHora(j.criado_em)) + '</span></div>';
  html += '</div>';

  // cancelar: só habilitado em na_fila (contrato §3.5)
  html += '<button class="btn btn--mini btn--perigo" data-acao="cancelar" data-id="' + esc(j.id) + '"' +
    (j.estado === 'na_fila' ? '' : ' disabled title="só é possível cancelar antes de começar"') +
    '>Cancelar</button>';
  html += '</div>';

  if (j.estado === 'na_fila') {
    html += '<div class="row row--gap"><span class="posicao" data-campo="posicao"></span></div>';
  }

  if (j.estado === 'baixando' || j.estado === 'concluido') {
    html += '<div class="prog">' +
      '<div class="prog__linha">' +
        '<div class="prog__pct mono" data-campo="pct">--<small>%</small></div>' +
        '<div class="prog__nums">' +
          '<div><b data-campo="tamanho">--</b><span>baixado</span></div>' +
          '<div><b data-campo="velocidade">--</b><span>velocidade</span></div>' +
          '<div><b data-campo="eta">--</b><span>restante</span></div>' +
        '</div>' +
      '</div>' +
      '<div class="barra" role="progressbar" aria-valuemin="0" aria-valuemax="100"><div class="barra__fill"></div></div>' +
      '</div>';
  }

  if (j.estado === 'falhou') {
    var podeTentar = MOTIVOS_RETENTAVEIS[j.motivo_falha] && estado.urlPorJob[j.id];
    html += '<div class="falha">' +
      '<div class="falha__cod">' + esc(j.motivo_falha || 'desconhecido') + '</div>' +
      '<p class="falha__msg">' + esc(j.mensagem_falha || 'Falha sem mensagem.') + '</p>' +
      (MOTIVOS_RETENTAVEIS[j.motivo_falha]
        ? '<div class="falha__acoes"><button class="btn btn--mini" data-acao="tentar" data-id="' + esc(j.id) + '"' +
          (podeTentar ? '' : ' disabled title="cole o link novamente para tentar"') + '>Tentar de novo</button></div>'
        : '') +
      '</div>';
  }

  if (j.estado === 'concluido' && j.caminho_final) {
    html += '<div class="job__rodape">' +
      '<span class="caminho" title="' + esc(j.caminho_final) + '">' + esc(j.caminho_final) + '</span>' +
      '<button class="btn btn--mini" data-acao="copiar" data-caminho="' + esc(j.caminho_final) + '">Copiar caminho</button>' +
      '</div>';
  }

  html += '<div class="nota nota--aviso" data-campo="aviso" hidden>' +
    '<span class="nota__tag">Aviso</span><span class="nota__corpo"></span></div>';

  return html;
}

function cancelar(id) {
  api('DELETE', '/api/fila/' + encodeURIComponent(id)).then(function () {
    atualizarFila();
  }).catch(function (e) {
    toast(e.message, 'erro');
    atualizarFila();          // 404/409: a fila mudou, recarrega
  });
}

function tentarDeNovo(id) {
  var job = estado.jobs.filter(function (j) { return j.id === id; })[0];
  var url = estado.urlPorJob[id];
  if (!job || !url) return;
  api('POST', '/api/fila', { urls: [url], perfil: job.perfil, projeto: job.projeto, forcar: true })
    .then(function (r) {
      (r.ids || []).forEach(function (novo) { estado.urlPorJob[novo] = url; });
      atualizarFila();
      ligarPolling();
    }).catch(function (e) { toast(e.message, 'erro'); });
}

/* ------------------------------------------------------------
   9. HISTÓRICO
   ------------------------------------------------------------ */

function carregarHistorico() {
  var termo = $('#busca-historico').value.trim();
  var projeto = $('#filtro-projeto').value;
  var q = [];
  if (termo) q.push('termo=' + encodeURIComponent(termo));
  if (projeto) q.push('projeto=' + encodeURIComponent(projeto));
  q.push('limite=' + LIMITE_HISTORICO);

  return api('GET', '/api/historico?' + q.join('&')).then(function (r) {
    estado.historico = r.registros || [];
    renderHistorico();
  }).catch(function (e) {
    if (e.status !== 0) toast(e.message, 'erro');
  });
}

function renderHistorico() {
  var alvo = $('#lista-historico');
  var regs = estado.historico;
  var filtrando = $('#busca-historico').value.trim() || $('#filtro-projeto').value;

  $('#contador-historico').textContent = regs.length
    ? regs.length + (regs.length === LIMITE_HISTORICO ? '+ registros' : ' registro(s)')
    : '';

  if (!regs.length) {
    alvo.innerHTML = filtrando
      ? vazio('Nenhum resultado', 'A busca ignora acento e maiúsculas. Tente um termo mais curto ou limpe o filtro de projeto.')
      : vazio('Histórico vazio', 'Cada download concluído entra aqui com o caminho do arquivo no disco.');
    return;
  }

  alvo.innerHTML = regs.map(function (r) {
    return '' +
      '<div class="hist">' +
        '<div class="hist__info">' +
          '<div class="row row--gap">' + selo(r.status) +
            '<span class="tag">' + esc(r.perfil) + '</span>' +
            '<span class="tag">' + esc(rotuloProjeto(r.projeto)) + '</span>' +
          '</div>' +
          '<h3 class="titulo titulo--1" title="' + esc(r.titulo) + '">' + esc(r.titulo) + '</h3>' +
          '<div class="meta">' +
            '<span class="meta__canal">' + esc(r.canal || 'canal desconhecido') + '</span>' +
            '<span class="meta__sep">/</span><span class="mono">' + fmtDuracao(r.duracao_s) + '</span>' +
            '<span class="meta__sep">/</span><span class="mono">' + esc(r.resolucao || '--') + '</span>' +
            '<span class="meta__sep">/</span><span class="mono">' + fmtBytes(r.tamanho_bytes) + '</span>' +
            '<span class="meta__sep">/</span><span class="mono">' + esc(fmtDataHora(r.concluido_em || r.criado_em)) + '</span>' +
          '</div>' +
          (r.status === 'falhou' || r.status === 'interrompido'
            ? '<p class="falha__msg">' + esc(r.mensagem_falha ||
                (r.status === 'interrompido' ? 'O programa fechou durante o download.' : 'Falha sem mensagem.')) + '</p>'
            : '<span class="caminho caminho--1" title="' + esc(r.caminho) + '">' + esc(r.caminho) + '</span>') +
        '</div>' +
        '<div class="hist__acoes">' +
          '<button class="btn btn--mini" data-acao="copiar" data-caminho="' + esc(r.caminho) + '"' +
            (r.caminho ? '' : ' disabled') + '>Copiar caminho</button>' +
        '</div>' +
      '</div>';
  }).join('');
}

/* ------------------------------------------------------------
   10. TOASTS, VAZIOS, EVENTOS
   ------------------------------------------------------------ */

function vazio(titulo, texto) {
  return '<div class="vazio"><div class="vazio__marca"></div>' +
    '<p class="vazio__titulo">' + esc(titulo) + '</p>' +
    '<p class="vazio__texto">' + esc(texto) + '</p></div>';
}

function toast(msg, tom) {
  var el = document.createElement('div');
  el.className = 'toast';
  if (tom) el.dataset.tone = tom;
  el.textContent = msg;
  $('#toasts').appendChild(el);
  setTimeout(function () { el.remove(); }, 6000);
}

function copiarCaminho(caminho) {
  // §8: o endpoint "abrir pasta" ainda não existe; por ora copiamos o caminho.
  var ok = function () { toast('Caminho copiado.', 'ok'); };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(caminho).then(ok, function () { copiaManual(caminho, ok); });
  } else {
    copiaManual(caminho, ok);
  }
}
function copiaManual(texto, ok) {
  var ta = document.createElement('textarea');
  ta.value = texto;
  ta.style.position = 'fixed';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand('copy'); ok(); } catch (e) { toast('Não foi possível copiar.', 'erro'); }
  ta.remove();
}

function ligarEventos() {
  $('#campo-links').addEventListener('input', atualizarContadorLinks);
  $('#campo-links').addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); inspecionar(); }
  });
  $('#btn-inspecionar').addEventListener('click', inspecionar);
  $('#btn-limpar-links').addEventListener('click', function () {
    $('#campo-links').value = '';
    atualizarContadorLinks();
    $('#campo-links').focus();
  });

  // lote: aplica a todos os cartões
  $('#lote-perfil').addEventListener('change', function () {
    estado.preview.forEach(function (p) { if (!p.enfileirado) p.perfil = $('#lote-perfil').value; });
    estado.escolhas.perfil = $('#lote-perfil').value; salvarEscolhas();
    renderPreview(); preencherSelectsPreview();
  });
  $('#lote-projeto').addEventListener('change', function () {
    estado.preview.forEach(function (p) { if (!p.enfileirado) p.projeto = $('#lote-projeto').value; });
    estado.escolhas.projeto = $('#lote-projeto').value; salvarEscolhas();
    renderPreview(); preencherSelectsPreview();
  });
  $('#btn-enfileirar-todos').addEventListener('click', function () {
    enfileirar(estado.preview.map(function (_, i) { return i; }));
  });

  // delegação: cartões de preview
  $('#lista-preview').addEventListener('change', function (e) {
    var s = e.target.closest('select[data-acao]');
    if (!s) return;
    var p = estado.preview[Number(s.dataset.i)];
    if (!p) return;
    p[s.dataset.acao] = s.value;
    if (s.dataset.acao === 'perfil') p.forcar = false;   // duplicata é por perfil
    renderPreview(); preencherSelectsPreview();
  });
  $('#lista-preview').addEventListener('click', function (e) {
    var b = e.target.closest('button[data-acao]');
    if (!b) return;
    var i = Number(b.dataset.i);
    if (b.dataset.acao === 'enfileirar') enfileirar([i]);
    if (b.dataset.acao === 'forcar') {
      estado.preview[i].forcar = !estado.preview[i].forcar;
      renderPreview(); preencherSelectsPreview();
    }
  });

  // delegação: fila e histórico
  document.addEventListener('click', function (e) {
    var b = e.target.closest('button[data-acao]');
    if (!b) return;
    if (b.dataset.acao === 'cancelar') cancelar(b.dataset.id);
    if (b.dataset.acao === 'tentar') tentarDeNovo(b.dataset.id);
    if (b.dataset.acao === 'copiar') copiarCaminho(b.dataset.caminho);
  });

  $('#busca-historico').addEventListener('input', debounce(carregarHistorico, 250));
  $('#filtro-projeto').addEventListener('change', carregarHistorico);
}

/* ============================================================
   11. SERVIDOR DE DEMONSTRAÇÃO
   Só entra em ação quando a API real não responde (abrir o
   index.html sem o servidor atrás). Reproduz as mesmas respostas
   do contrato para a interface poder ser navegada e revisada.
   Apague este bloco quando não precisar mais dele.
   ============================================================ */

var Demo = (function () {

  var config = {
    ffmpeg: { disponivel: true, completo: true, ffmpeg: 'C:\\ffmpeg\\bin\\ffmpeg.exe', ffprobe: 'C:\\ffmpeg\\bin\\ffprobe.exe' },
    perfis: [
      { nome: 'edicao_1080', descricao: '1080p H.264 + AAC — abre nativo no Premiere/Resolve', disponivel: true, exige_ffmpeg: true, limite_dimensao: 1080, container: 'mp4' },
      { nome: 'edicao_4k', descricao: 'Até 2160p — VP9/AV1, pode exigir transcode', disponivel: true, exige_ffmpeg: true, limite_dimensao: 2160, container: 'mkv' },
      { nome: 'so_audio', descricao: 'Só a trilha de áudio, em m4a', disponivel: true, exige_ffmpeg: true, limite_dimensao: null, container: 'm4a' },
      { nome: 'preview_leve', descricao: 'Até 480p, menor arquivo', disponivel: true, exige_ffmpeg: true, limite_dimensao: 480, container: 'mp4' }
    ],
    projetos: [
      { nome: 'cliente_x', rotulo: 'Cliente X', pasta: 'D:/FOOTAGE/cliente_x', valido: true, motivo: null },
      { nome: 'pessoal', rotulo: 'Canal pessoal', pasta: 'D:/FOOTAGE/pessoal', valido: true, motivo: null }
    ]
  };

  // catálogo fictício de vídeos, incluindo casos difíceis:
  // título muito longo, thumbnail null, site fora do YouTube
  var catalogo = [
    { id: 'LzS8kB6lIm0', extractor: 'Youtube', titulo: 'Grand Final — Major 2026, mapa 5 em Inferno: overtime duplo, clutch de 1v3 e a virada que decidiu o campeonato', canal: 'Canal Michuruca', duracao_s: 4265, thumbnail: 'https://i.ytimg.com/vi/LzS8kB6lIm0/maxresdefault.jpg', data_upload: '20260901', qualidades: [144, 240, 360, 480, 720, 1080, 1440, 2160] },
    { id: 'aB3dEf7Hi9k', extractor: 'Youtube', titulo: 'Highlights da semifinal — sem comentário, áudio limpo para reuso', canal: 'Liga Sul Esports', duracao_s: 612, thumbnail: null, data_upload: '20260830', qualidades: [360, 480, 720, 1080] },
    { id: 'zz9PlaqWx0y', extractor: 'Youtube', titulo: 'Entrevista pós-jogo com o capitão (vertical, Shorts)', canal: 'Arena PT', duracao_s: 65, thumbnail: null, data_upload: '20260902', qualidades: [144, 240, 360, 480, 608, 720, 1080] }
  ];

  var jobs = [];
  var historico = [];
  var proxSeq = 1;
  var tickLigado = false;

  function agora() { return new Date().toISOString().replace('.000Z', '+00:00').replace(/\.\d+Z$/, '+00:00'); }
  function idAleatorio() { return (Math.random().toString(16).slice(2) + Math.random().toString(16).slice(2)).slice(0, 32); }

  function ehLink(s) { return /^https?:\/\/\S+\.\S+/.test(s); }

  function videoPara(url, i) {
    var base = catalogo[i % catalogo.length];
    var v = JSON.parse(JSON.stringify(base));
    if (!/youtu/.test(url)) {
      v.extractor = 'Vimeo';
      v.titulo = 'Clipe hospedado fora do YouTube — captura de tela da partida';
      v.qualidades = [];
      v.thumbnail = null;
      v.canal = 'alguem';
    }
    v.url_canonica = url;
    return v;
  }

  function baixadosPara(videoId) {
    var out = {};
    historico.forEach(function (r) {
      if (r.video_id === videoId && r.status === 'concluido') {
        out[r.perfil] = { caminho: r.caminho, projeto: r.projeto, resolucao: r.resolucao, concluido_em: r.concluido_em };
      }
    });
    return out;
  }

  function inspecionar(texto) {
    var linhas = String(texto || '').split('\n').map(function (l) { return l.trim(); })
      .filter(function (l) { return l; })
      .filter(function (l, i, a) { return a.indexOf(l) === i; });

    return { itens: linhas.map(function (l, i) {
      if (!ehLink(l)) {
        return { ok: false, original: l, url: null, erro: "Não é um link válido: '" + l + "'", motivo: 'link_invalido' };
      }
      var ehYt = /youtu/.test(l);
      var v = videoPara(l, i);
      return {
        ok: true,
        original: l,
        url: ehYt ? 'https://www.youtube.com/watch?v=' + v.id : l,
        e_youtube: ehYt,
        aviso: ehYt ? null : 'Link fora do YouTube: o download pode funcionar, mas a deduplicação e o histórico só reconhecem este endereço se ele for colado exatamente igual.',
        video: v,
        baixados: baixadosPara(v.id)
      };
    }) };
  }

  function enfileira(corpo) {
    var urls = corpo.urls || [];
    var perfil = config.perfis.filter(function (p) { return p.nome === corpo.perfil; })[0];
    if (!perfil) throw erro(400, "Perfil '" + corpo.perfil + "' não existe.");
    var projeto = config.projetos.filter(function (p) { return p.nome === corpo.projeto; })[0];
    if (!projeto) throw erro(400, "Projeto '" + corpo.projeto + "' não existe.");

    var criados = [];
    urls.forEach(function (u, i) {
      var v = videoPara(u, i);
      var dup = baixadosPara(v.id)[corpo.perfil];
      if (dup && !corpo.forcar) {
        throw erro(409, "Já baixado no perfil '" + corpo.perfil + "': " + dup.caminho + '. Use forcar=true para baixar de novo.');
      }
      var naFila = jobs.some(function (j) {
        return j.video.id === v.id && j.perfil === corpo.perfil && (j.estado === 'na_fila' || j.estado === 'baixando');
      });
      if (naFila) throw erro(409, "Este vídeo já está na fila no perfil '" + corpo.perfil + "'.");
      criados.push({ v: v, u: u });
    });

    var ids = criados.map(function (c) {
      var total = 8 * 1024 * 1024 + Math.floor(Math.random() * 90) * 1024 * 1024;
      var job = {
        id: idAleatorio(),
        estado: 'na_fila',
        perfil: corpo.perfil,
        projeto: corpo.projeto,
        criado_em: agora(),
        video: { id: c.v.id, titulo: c.v.titulo, canal: c.v.canal, duracao_s: c.v.duracao_s, thumbnail: c.v.thumbnail },
        progresso: null,
        caminho_final: null,
        motivo_falha: null,
        mensagem_falha: null,
        aviso: null,
        _total: total,
        _falhar: /vimeo|dailymotion/.test(c.u) && Math.random() < .5,   // exercita o estado falhou
        _indet: Math.random() < .25                                     // total desconhecido
      };
      jobs.push(job);
      return job.id;
    });

    ligarTick();
    return { ids: ids };
  }

  function cancela(id) {
    var j = jobs.filter(function (x) { return x.id === id; })[0];
    if (!j) throw erro(404, "Job '" + id + "' não existe.");
    if (j.estado !== 'na_fila') throw erro(409, 'Só é possível cancelar um job que ainda não começou (SPEC 10.5).');
    j.estado = 'cancelado';
    return { cancelado: true };
  }

  /* um download por vez, avançando em passos */
  function ligarTick() {
    if (tickLigado) return;
    tickLigado = true;
    setInterval(function () {
      var ativo = jobs.filter(function (j) { return j.estado === 'baixando'; })[0];
      if (!ativo) {
        ativo = jobs.filter(function (j) { return j.estado === 'na_fila'; })[0];
        if (!ativo) return;
        ativo.estado = 'baixando';
        ativo.progresso = { baixados: 0, total: ativo._indet ? null : ativo._total, percentual: ativo._indet ? null : 0, velocidade_bps: 0, eta_s: null };
      }
      var passo = (2 + Math.random() * 5) * 1024 * 1024;   // ~2-7 MB/s
      var p = ativo.progresso;
      p.baixados = Math.min(ativo._total, p.baixados + passo);
      p.velocidade_bps = passo;
      if (!ativo._indet) {
        p.total = ativo._total;
        p.percentual = p.baixados / ativo._total * 100;
        p.eta_s = Math.max(0, Math.round((ativo._total - p.baixados) / passo));
      }
      if (p.baixados >= ativo._total) {
        if (ativo._falhar) {
          ativo.estado = 'falhou';
          ativo.motivo_falha = 'rede';
          ativo.mensagem_falha = 'A conexão caiu durante o download (timeout depois de 3 tentativas).';
          ativo.progresso = null;
          registrar(ativo, 'falhou');
        } else {
          var ext = config.perfis.filter(function (x) { return x.nome === ativo.perfil; })[0].container;
          var pasta = config.projetos.filter(function (x) { return x.nome === ativo.projeto; })[0].pasta.replace(/\//g, '\\');
          ativo.estado = 'concluido';
          ativo.caminho_final = pasta + '\\20260901 - ' + ativo.video.titulo.slice(0, 58).replace(/[\\/:*?"<>|]/g, '') + ' [' + ativo.video.id + '].' + ext;
          ativo.progresso = { baixados: ativo._total, total: ativo._total, percentual: 100, velocidade_bps: null, eta_s: 0 };
          registrar(ativo, 'concluido');
        }
      }
    }, 1000);
  }

  function registrar(job, status) {
    historico.unshift({
      id: proxSeq++,
      extractor: 'Youtube',
      video_id: job.video.id,
      perfil: job.perfil,
      url_original: '',
      url_canonica: '',
      titulo: job.video.titulo,
      canal: job.video.canal,
      duracao_s: job.video.duracao_s,
      projeto: job.projeto,
      caminho: job.caminho_final,
      tamanho_bytes: status === 'concluido' ? job._total : null,
      resolucao: status === 'concluido' ? '1920x1080' : null,
      status: status,
      motivo_falha: job.motivo_falha,
      mensagem_falha: job.mensagem_falha,
      criado_em: job.criado_em,
      concluido_em: agora()
    });
  }

  function semAcento(s) { return String(s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase(); }

  function consultaHistorico(qs) {
    var p = new URLSearchParams(qs || '');
    var termo = semAcento(p.get('termo'));
    var projeto = p.get('projeto');
    var limite = Math.min(Number(p.get('limite') || 100), 1000);
    return { registros: historico.filter(function (r) {
      if (termo && semAcento(r.titulo).indexOf(termo) === -1) return false;
      if (projeto && r.projeto !== projeto) return false;
      return true;
    }).slice(0, limite) };
  }

  function erro(status, msg) { var e = new Error(msg); e.status = status; return e; }

  // dois registros de partida, para o histórico não abrir vazio na demonstração
  historico.push({
    id: 0, extractor: 'Youtube', video_id: 'aB3dEf7Hi9k', perfil: 'preview_leve',
    titulo: 'Scrim antiga — mapa 2, ângulo do observador (arquivo de referência)',
    canal: 'Liga Sul Esports', duracao_s: 3110, projeto: 'cliente_x',
    caminho: 'D:\\FOOTAGE\\cliente_x\\20260812 - Scrim antiga mapa 2 angulo do observador [aB3dEf7Hi9k].mp4',
    tamanho_bytes: 214958080, resolucao: '854x480', status: 'concluido',
    motivo_falha: null, mensagem_falha: null,
    criado_em: '2026-08-12T14:02:11+00:00', concluido_em: '2026-08-12T14:06:40+00:00'
  });
  historico.push({
    id: -1, extractor: 'Youtube', video_id: 'zz9PlaqWx0y', perfil: 'edicao_4k',
    titulo: 'Abertura do campeonato em 4K — pirotecnia e entrada dos times',
    canal: 'Arena PT', duracao_s: 289, projeto: 'pessoal',
    caminho: null, tamanho_bytes: null, resolucao: null, status: 'interrompido',
    motivo_falha: null, mensagem_falha: null,
    criado_em: '2026-08-10T09:31:00+00:00', concluido_em: null
  });

  function chamar(metodo, caminho, corpo) {
    return new Promise(function (resolve, reject) {
      setTimeout(function () {
        try {
          var partes = caminho.split('?');
          var rota = partes[0];
          if (metodo === 'GET' && rota === '/api/config') return resolve(config);
          if (metodo === 'POST' && rota === '/api/inspecionar') return resolve(inspecionar(corpo.links));
          if (metodo === 'POST' && rota === '/api/fila') return resolve(enfileira(corpo));
          if (metodo === 'GET' && rota === '/api/fila') return resolve({ jobs: JSON.parse(JSON.stringify(jobs)) });
          if (metodo === 'DELETE' && rota.indexOf('/api/fila/') === 0) {
            return resolve(cancela(decodeURIComponent(rota.slice('/api/fila/'.length))));
          }
          if (metodo === 'GET' && rota === '/api/historico') return resolve(consultaHistorico(partes[1]));
          reject(erro(404, 'Rota não encontrada: ' + caminho));
        } catch (e) { reject(e); }
      }, rota_demora(caminho));
    });
  }

  function rota_demora(caminho) { return caminho.indexOf('/api/inspecionar') === 0 ? 700 : 60; }

  return { chamar: chamar };
})();

/* ------------------------------------------------------------ */
document.addEventListener('DOMContentLoaded', iniciar);
