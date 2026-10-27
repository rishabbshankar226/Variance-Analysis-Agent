// @ts-check
/**
 * Variance Analysis Agent: chat page.
 *
 * Plain browser JavaScript, no build step. `// @ts-check` and the JSDoc types let an editor (or an
 * optional local `tsc --noEmit --checkJs`) type-check it. The pure helpers are exported so Node can
 * test them; everything that touches the page starts only when a `document` exists.
 */

/**
 * @typedef {Object} ChatReply  One JSON reply from the server.
 * @property {string} [text]
 * @property {Array<Record<string, string>>} [table]
 * @property {string[]} [chips]
 * @property {string} [phase]
 * @property {string} [error]
 * @property {string} [download_url]
 * @property {string} [download_filename]
 * @property {'error'} [level]  set when the reply refuses or could not do what was asked
 * @property {Record<string, unknown>} [view]  a designed view of the same reply (see chat/views.py)
 * @property {ChatReply} [initial_response]  Only on /status, when a file was loaded at start-up.
 */

/**
 * @typedef {Object} JsonResult
 * @property {boolean} ok
 * @property {number} status
 * @property {ChatReply | null} data  The parsed body when it was a JSON object.
 */

// ── Limits (mirror variance_agent.limits; a test keeps them equal) ─────────
export const MAX_MESSAGE_CHARS = 128 * 1024;
export const MAX_UPLOAD_BYTES = 32 * 1024 * 1024;

const MESSAGE_TIMEOUT_MS = 60_000; // the server is single-threaded; a PDF read can take ~20 s
const UPLOAD_TIMEOUT_MS = 120_000;
const STATUS_TIMEOUT_MS = 10_000;
const VALID_EXTENSIONS = ['.csv', '.json', '.xlsx', '.xlsm', '.xls', '.pdf', '.htm', '.html'];

// ── Phases (one label for every chat.session.Phase; a test keeps them complete) ──
/** @type {Record<string, string>} */
export const PHASE_LABELS = {
  awaiting_earnings_review:           'Choose a review',
  awaiting_comparison_choice:         'Choose a comparison',
  awaiting_file:                      'Upload a file',
  awaiting_sheet_choice:              'Choose a sheet',
  awaiting_header_choice:             'Choose the header row',
  awaiting_blank_budget_confirmation: 'Confirm blank budgets',
  awaiting_period_choice:             'Choose a period',
  awaiting_intake_confirmation:       'Confirm how the file was read',
  awaiting_period:                    'Set the period',
  awaiting_thresholds:                'Set the thresholds',
  awaiting_currency:                  'Set the currency',
  awaiting_measure_options:           'Confirm a measure',
  resolve_unclassified:               'Label lines',
  exploring:                          'Results',
};

/** @type {Record<string, string>} */
export const PHASE_PLACEHOLDERS = {
  awaiting_earnings_review:           'Review earnings, or upload another file',
  awaiting_comparison_choice:         'Choose a comparison, or all of them',
  awaiting_file:                      'Upload a file above, or ask a question such as what is materiality',
  awaiting_sheet_choice:              'Choose a worksheet from the options above',
  awaiting_header_choice:             'Choose the header row from the options above',
  awaiting_blank_budget_confirmation: 'Choose how to treat the blank values',
  awaiting_period_choice:             'Choose the period to analyze',
  awaiting_intake_confirmation:       'Confirm the summary above, or say what to change',
  awaiting_period:                    'Reporting period, for example Q3 2026',
  awaiting_thresholds:                'Thresholds, for example $10,000 or 5%',
  awaiting_currency:                  'Currency, for example USD',
  awaiting_measure_options:           'Choose a direction, a scale or a threshold',
  resolve_unclassified:               'Revenue, Expense or Skip',
  exploring:                          'Ask about the results, for example why marketing',
};

/**
 * A readable label for any phase, including ones this page has not heard of.
 * @param {string} phase
 * @returns {string}
 */
export function phaseLabel(phase) {
  if (Object.hasOwn(PHASE_LABELS, phase)) return PHASE_LABELS[phase];
  const words = String(phase).replace(/^awaiting_/, '').split('_').filter(Boolean);
  const label = words.join(' ');
  return label ? label[0].toUpperCase() + label.slice(1) : 'Ready';
}

/**
 * @param {string} phase
 * @returns {string}
 */
export function phasePlaceholder(phase) {
  return Object.hasOwn(PHASE_PLACEHOLDERS, phase) ? PHASE_PLACEHOLDERS[phase] : 'Type a message';
}

/**
 * What to show when the page loads, from the server's /status reply. The server's phase always
 * wins: a reload in the middle of an intake must not look like a fresh start.
 * @param {ChatReply | null} status
 * @returns {{kind: 'welcome' | 'restored' | 'resumed', phase: string, reply?: ChatReply}}
 */
export function startupView(status) {
  const phase = status && typeof status.phase === 'string' && status.phase ? status.phase : 'awaiting_file';
  if (phase === 'awaiting_file') return { kind: 'welcome', phase };
  if (status && status.initial_response) return { kind: 'restored', phase, reply: status.initial_response };
  return { kind: 'resumed', phase };
}

/**
 * The text of a warning bubble for a request that did not succeed.
 * @param {number} status HTTP status
 * @param {ChatReply | null} data the parsed JSON body, if there was one
 * @returns {string}
 */
export function describeFailure(status, data) {
  if (data && typeof data.error === 'string' && data.error.trim()) return data.error.trim();
  if (status === 413) return 'That is larger than the server accepts.';
  if (status === 502 || status === 503 || status === 504) {
    return 'The server is not responding (it may be starting up). Please try again in a moment.';
  }
  return `The server could not handle that request (HTTP ${status}).`;
}

/**
 * Fetch a JSON reply with a deadline. Resolves for every HTTP status (check `ok`); rejects with a
 * readable Error only when no usable reply arrived.
 * @param {string} url
 * @param {RequestInit} init
 * @param {number} timeoutMs
 * @param {typeof fetch} [fetchImpl]
 * @returns {Promise<JsonResult>}
 */
export async function requestJson(url, init, timeoutMs, fetchImpl = globalThis.fetch) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetchImpl(url, { ...init, signal: controller.signal });
    /** @type {ChatReply | null} */
    let data = null;
    try {
      const parsed = await response.json();
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) data = parsed;
    } catch (_) {
      data = null; // e.g. an HTML error page from a proxy
    }
    return { ok: response.ok, status: response.status, data };
  } catch (_) {
    if (controller.signal.aborted) {
      throw new Error('The server did not answer in time. Please try again.');
    }
    throw new Error('Could not reach the server. Check your connection and try again.');
  } finally {
    clearTimeout(timer);
  }
}

// ── Text handling ───────────────────────────────────────────────────────────

/**
 * Escape text for use as HTML element content.
 * @param {string} text
 * @returns {string}
 */
export function escapeHtml(text) {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/**
 * The server escapes source labels for Markdown/HTML documents (R&D_Costs -> R&amp;D\_Costs).
 * The chat UI escapes HTML itself, so undo the server's entity escapes exactly once here.
 * @param {string} text
 * @returns {string}
 */
export function decodeServerEscapes(text) {
  return text.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
}

// Markdown backslash escapes (\_ \* \| ...). A function so every use gets a fresh /g regex.
const mdEscapes = () => /\\([\\`*_{}[\]()#+\-.!|~>])/g;

/**
 * Table cells are set with textContent, so they need plain text with no escapes at all.
 * @param {unknown} text
 * @returns {string}
 */
export function plainText(text) {
  return decodeServerEscapes(String(text)).replace(mdEscapes(), '$1');
}

/**
 * Minimal Markdown to HTML (no library). The result is built from escaped text and fixed tags
 * only, and uses classes rather than inline styles so the page's CSP can forbid both.
 * @param {string} text
 * @returns {string}
 */
export function renderMarkdown(text) {
  let html = escapeHtml(decodeServerEscapes(text));

  // Markdown backslash escapes (\_ \* \| ...) become literal characters, not formatting
  /** @type {string[]} */
  const literals = [];
  html = html.replace(mdEscapes(), (_, ch) => {
    literals.push(ch);
    return '\u0000' + (literals.length - 1) + '\u0000';
  });

  html = html.replace(/^---+$/gm, '<hr class="md-hr">');
  html = html.replace(/^###\s+(.+)$/gm, '<h4 class="md-h4">$1</h4>');
  html = html.replace(/^##\s+(.+)$/gm, '<h3 class="md-h3">$1</h3>');
  html = html.replace(/^#\s+(.+)$/gm, '<h2 class="md-h2">$1</h2>');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>'); // after bold so ** is not eaten
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/^[•-]\s+(.+)$/gm, '<div class="md-bullet">• $1</div>');
  html = html.replace(/\n/g, '<br>');
  // A block (a bullet, a heading or a rule) already ends its line: drop the break after it.
  html = html.replace(/(<\/div>|<\/h[234]>|<hr class="md-hr">)<br>/g, '$1');

  return html.replace(/\u0000(\d+)\u0000/g, (_, i) => literals[Number(i)]);
}

const PREVIEW_CHARS = 4000;

/**
 * What to echo back of a very long paste: the first part and how much was left out. The full text
 * is still what gets sent.
 * @param {string} text
 * @returns {string}
 */
export function previewText(text) {
  if (text.length <= PREVIEW_CHARS) return text;
  return `${text.slice(0, PREVIEW_CHARS)}\n… (${(text.length - PREVIEW_CHARS).toLocaleString('en-US')} more characters)`;
}

/**
 * Parse a displayed amount such as "$(1,234.50)" or "12.5%" to a number (0 when there is none).
 * @param {unknown} val
 * @returns {number}
 */
export function parseNumericVal(val) {
  if (!val) return 0;
  let s = String(val).trim();
  const isNegParen = s.startsWith('(') && s.endsWith(')');
  if (isNegParen) s = s.slice(1, -1);
  s = s.replace(/[$,€£¥%\s]/g, '');
  const num = parseFloat(s);
  if (isNaN(num)) return 0;
  return isNegParen ? -num : num;
}

// ── Icons ───────────────────────────────────────────────────────────────────
// One drawn set on a 20-unit grid, stroked at one width (chat.css `.icon`) and shown at two sizes.
// The page carries no emoji, arrows or dingbats: they render differently on every system.

/** @typedef {{d: string, fill?: boolean}} IconPart */

/** @type {Record<string, IconPart[]>} */
export const ICONS = {
  mark: [{ d: 'M3.75 7.75h5.5v9.5h-5.5z' }, { d: 'M11 3h6v15h-6z', fill: true }, { d: 'M1 18.25h18' }],
  sort: [{ d: 'M7 8l3-3 3 3' }, { d: 'M7 12l3 3 3-3' }],
  'sort-asc': [{ d: 'M7 12l3-3 3 3' }],
  'sort-desc': [{ d: 'M7 8l3 3 3-3' }],
  search: [{ d: 'M9 15a6 6 0 1 0 0-12 6 6 0 0 0 0 12z' }, { d: 'M17 17l-3.75-3.75' }],
  download: [{ d: 'M10 3v10' }, { d: 'M6 9.5l4 4 4-4' }, { d: 'M4 17h12' }],
  upload: [{ d: 'M10 13V3' }, { d: 'M6 6.5l4-4 4 4' }, { d: 'M4 17h12' }],
  help: [{ d: 'M10 18a8 8 0 1 0 0-16 8 8 0 0 0 0 16z' }, { d: 'M7.75 7.75a2.25 2.25 0 1 1 3.25 2c-.6.35-1 .8-1 1.5v.5' },
    { d: 'M10 14.25v.5' }],
  restart: [{ d: 'M4 10a6 6 0 1 0 1.76-4.24' }, { d: 'M4 3v3.5h3.5' }],
  more: [{ d: 'M8 5l5 5-5 5' }],
};

/** The two sizes an icon is drawn at, in CSS pixels. */
export const ICON_SIZES = [16, 20];

/**
 * The parts of a named icon, checked: an unknown name or size is a bug, not a blank space.
 * @param {string} name
 * @param {number} size
 * @returns {IconPart[]}
 */
export function iconParts(name, size) {
  if (!Object.hasOwn(ICONS, name)) throw new Error(`Unknown icon: ${name}`);
  if (!ICON_SIZES.includes(size)) throw new Error(`Icons are drawn at ${ICON_SIZES.join(' or ')} px, not ${size}`);
  return ICONS[name];
}

const SVG_NS = 'http://www.w3.org/2000/svg';

/**
 * A decorative SVG icon, built with createElementNS (the CSP allows no inline markup or style).
 * @param {string} name
 * @param {number} size
 * @returns {SVGSVGElement}
 */
export function createIcon(name, size) {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('class', 'icon');
  svg.setAttribute('viewBox', '0 0 20 20');
  svg.setAttribute('width', String(size));
  svg.setAttribute('height', String(size));
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  for (const part of iconParts(name, size)) {
    const path = document.createElementNS(SVG_NS, 'path');
    path.setAttribute('d', part.d);
    path.setAttribute('vector-effect', 'non-scaling-stroke');
    if (part.fill) path.setAttribute('class', 'icon-fill');
    svg.appendChild(path);
  }
  return svg;
}

/**
 * Retire the suggestion chips of earlier turns: only the latest turn's chips respond (T7). Earlier
 * chips stay on the page as a record of what was offered, since a reply may say "choose one below",
 * but they are disabled, so assistive technology announces them as unavailable, and they are styled
 * as plain text. Table drill-downs and download links in earlier results are not chips and stay live.
 * @param {Iterable<{classList: {add: (name: string) => void}, setAttribute: (name: string, value: string) => void,
 *   querySelectorAll: (selector: string) => Iterable<{disabled: boolean}>}>} groups  the live `.chips` groups
 * @returns {number} how many chips were retired
 */
export function retireChips(groups) {
  let retired = 0;
  for (const group of groups) {
    group.classList.add('is-retired');
    group.setAttribute('aria-label', 'Earlier suggestions, no longer available');
    for (const chip of group.querySelectorAll('button')) {
      chip.disabled = true;
      retired += 1;
    }
  }
  return retired;
}

// ── Designed views ──────────────────────────────────────────────────────────

/**
 * @typedef {Object} IntakeView  How the file was read, one fact per row (chat/views.py).
 * @property {'intake'} kind
 * @property {string} title
 * @property {string | null} lead  the server's Markdown, shown above the panel
 * @property {Array<{label: string, value: string}>} rows
 * @property {Array<{title: string, items: string[], more: number}>} notes
 * @property {string} question
 */

/** @param {unknown} value @returns {value is string} */
const isString = (value) => typeof value === 'string';

/**
 * Whether a reply's `view` is an intake panel this page can draw. Anything else falls back to
 * the reply's text, which always carries the same facts.
 * @param {unknown} view
 * @returns {view is IntakeView}
 */
export function isIntakeView(view) {
  if (!view || typeof view !== 'object') return false;
  const v = /** @type {Record<string, unknown>} */ (view);
  return v.kind === 'intake' && isString(v.title) && isString(v.question)
    && (v.lead === null || isString(v.lead))
    && Array.isArray(v.rows) && v.rows.length > 0
    && v.rows.every((r) => r && isString(r.label) && isString(r.value))
    && Array.isArray(v.notes)
    && v.notes.every((n) => n && isString(n.title) && Array.isArray(n.items) && n.items.every(isString)
      && Number.isInteger(n.more) && n.more >= 0);
}

/**
 * @typedef {Object} Figure  One headline figure; every string is formatted by the engine.
 * @property {string} label
 * @property {string} value
 * @property {string | null} compare
 * @property {string | null} change
 * @property {string | null} status  a status word
 * @property {'favorable' | 'unfavorable' | 'neutral' | null} tone
 */

/**
 * @typedef {Object} FiguresView  Results, a drill-down, a scenario (chat/views.py).
 * @property {'figures'} kind
 * @property {string} title
 * @property {string | null} lead
 * @property {Array<{label: string, value: string}>} context
 * @property {Figure[]} figures
 * @property {Array<{title: string, rows: Array<{label: string, value: string}>}>} sections
 * @property {string[]} notes
 * @property {string | null} table_title
 * @property {Array<{title: string, columns: Array<{key: string, label: string}>}>} column_groups
 */

/** @param {unknown} rows */
const isPairs = (rows) => Array.isArray(rows) && rows.every((r) => r && isString(r.label) && isString(r.value));
/** @param {unknown} value */
const isOptString = (value) => value === null || isString(value);
const TONE_NAMES = ['favorable', 'unfavorable', 'neutral'];

/**
 * @param {unknown} view
 * @returns {view is FiguresView}
 */
export function isFiguresView(view) {
  if (!view || typeof view !== 'object') return false;
  const v = /** @type {Record<string, unknown>} */ (view);
  return v.kind === 'figures' && isString(v.title) && isOptString(v.lead) && isOptString(v.table_title)
    && isPairs(v.context)
    && Array.isArray(v.figures) && v.figures.every((f) => f && isString(f.label) && isString(f.value)
      && isOptString(f.compare) && isOptString(f.change) && isOptString(f.status)
      && (f.tone === null || TONE_NAMES.includes(f.tone)))
    && Array.isArray(v.sections) && v.sections.every((sec) => sec && isString(sec.title) && isPairs(sec.rows))
    && Array.isArray(v.notes) && v.notes.every(isString)
    && Array.isArray(v.column_groups) && v.column_groups.every((g) => g && isString(g.title)
      && Array.isArray(g.columns) && g.columns.every((c) => c && isString(c.key) && isString(c.label)));
}

// ── Tables ──────────────────────────────────────────────────────────────────

/**
 * Status words for the engine's status values. This mirrors `status_label` in
 * chat/responses.py, and a test keeps the two equal. The record keeps the engine's value.
 * @type {Record<string, string>}
 */
export const STATUS_WORDS = {
  F: 'Favorable',
  U: 'Unfavorable',
  Neutral: 'Neutral',
  Unclassified: 'Unclassified',
};

/**
 * Tones of the engine's status values and of the earnings outcomes `display_outcome` gives
 * (Beat, Miss, In line), which are shown as they are.
 * @type {Record<string, 'favorable' | 'unfavorable' | 'neutral'>}
 */
const STATUS_TONES = {
  F: 'favorable', U: 'unfavorable', Neutral: 'neutral', Beat: 'favorable', Miss: 'unfavorable', 'In line': 'neutral',
};

/**
 * The word and tone a status cell shows. Values the page does not know are shown as they are.
 * @param {string} value
 * @returns {{word: string, tone: 'favorable' | 'unfavorable' | 'neutral' | null}}
 */
export function statusWord(value) {
  return {
    word: Object.hasOwn(STATUS_WORDS, value) ? STATUS_WORDS[value] : value,
    tone: Object.hasOwn(STATUS_TONES, value) ? STATUS_TONES[value] : null,
  };
}

/**
 * The heading a column shows, in sentence case. The key stays as the server sent it.
 * @param {string} key
 * @returns {string}
 */
export function columnLabel(key) {
  const variance = /^Var \((.+)\)$/.exec(key);
  if (variance) return variance[1] === '%' ? 'Variance %' : 'Variance';
  return key.split(' ').map((word, i) => (i > 0 && /^[A-Z][a-z]+$/.test(word) ? word.toLowerCase() : word)).join(' ');
}

const AMOUNT = /^[(\-\u2212+]?\s*[$\u20ac\u00a3\u00a5]?\s*\(?\d[\d,]*(\.\d+)?\)?\s*(%|bps|pts|\/sh|units?)?$/i;
const EMPTY_CELL = new Set(['', '\u2014', '-', 'N/A']);

/**
 * Whether a column holds figures (right-aligned, sorted by value): every filled cell is an amount.
 * @param {unknown[]} values
 * @returns {boolean}
 */
export function isNumericColumn(values) {
  const filled = values.map((v) => String(v ?? '').trim()).filter((v) => !EMPTY_CELL.has(v));
  return filled.length > 0 && filled.every((v) => AMOUNT.test(v));
}

/**
 * The column order a narrow screen shows: the line, its status and its variance first, so the
 * reason to open the table is visible without scrolling; every other column follows in its order.
 * @param {string[]} columns
 * @returns {string[]}
 */
export function phoneColumnOrder(columns) {
  const first = columns.slice(0, 1);
  const lead = columns.filter((col, i) => i > 0 && (col === 'Status' || col.endsWith(' outcome')
    || /^Var \(/.test(col) || col === 'Variance' || col.endsWith(' variance')));
  return [...first, ...lead, ...columns.filter((col, i) => i > 0 && !lead.includes(col))];
}

// ── The page ────────────────────────────────────────────────────────────────

function boot() {
  // ── State ────────────────────────────────────────────────
  let currentPhase = 'awaiting_file';
  let busy = false;

  // Visitors share one hosted session, so this browser remembers whether its
  // visitor has seen the welcome intro that opens the first file.
  const INTRO_SEEN_KEY = 'variance-agent:intro-seen';
  let introSeen = false;
  try { introSeen = localStorage.getItem(INTRO_SEEN_KEY) === '1'; } catch (_) { /* storage blocked */ }
  function markIntroSeen() {
    introSeen = true;
    try { localStorage.setItem(INTRO_SEEN_KEY, '1'); } catch (_) { /* storage blocked */ }
  }

  /**
   * @param {string} id
   * @returns {HTMLElement}
   */
  function byId(id) {
    const el = document.getElementById(id);
    if (!el) throw new Error(`Missing element #${id}`);
    return el;
  }

  const messagesEl = byId('messages');
  const inputEl = /** @type {HTMLTextAreaElement} */ (byId('input'));
  const sendBtn = /** @type {HTMLButtonElement} */ (byId('send-btn'));
  const phaseLabelEl = byId('phase-label');

  // ── Init ─────────────────────────────────────────────────
  async function init() {
    inputEl.addEventListener('keydown', (e) => {
      // Enter sends; Shift+Enter adds a line. Enter that confirms an IME composition (keyCode 229
      // on Safari) belongs to the IME and must not send.
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
        e.preventDefault();
        sendMessage();
      }
    });
    inputEl.addEventListener('input', autoGrow);
    sendBtn.addEventListener('click', sendMessage);

    const markEl = document.querySelector('.header-icon');
    if (markEl) markEl.appendChild(createIcon('mark', 20));
    byId('btn-quick-help').prepend(createIcon('help', 16));
    byId('btn-quick-reset').prepend(createIcon('restart', 16));

    byId('btn-quick-help').addEventListener('click', () => sendText('help'));
    byId('btn-quick-reset').addEventListener('click', () => sendText('reset'));

    /** @type {ChatReply | null} */
    let status = null;
    try {
      status = (await requestJson('/status', {}, STATUS_TIMEOUT_MS)).data;
    } catch (_) { /* start from the welcome screen */ }

    const view = startupView(status);
    updatePhase(view.phase);
    if (view.kind === 'restored' && view.reply) {
      markIntroSeen();
      addAgentMessage(view.reply.text, view.reply.table, view.reply.chips, false, view.reply.level, view.reply.view);
    } else if (view.kind === 'resumed') {
      addAgentMessage(
        'Welcome back. This server already has an analysis in progress (step: **' +
        phaseLabel(view.phase) + '**). Carry on where it left off, or start over.',
        null, ['help', 'reset'], false
      );
    } else {
      addAgentMessage(
        '**Upload a budget-versus-actual file to start.**\n\n' +
        'It needs an Actual column and a Budget, Forecast or Prior Period column. I show how I read ' +
        'the file, ask for the period and the materiality thresholds, then compare each line.',
        null, ['Supported file formats', 'What is materiality?', 'Budget vs forecast'], true
      );
    }
  }

  // ── Phase management ─────────────────────────────────────
  /** @param {string} phase */
  function updatePhase(phase) {
    currentPhase = phase;
    phaseLabelEl.textContent = phaseLabel(phase);
    inputEl.placeholder = phasePlaceholder(phase);
    autoGrow(); // a long placeholder wraps on a phone; leave room for it
  }

  /** @param {boolean} value */
  function setBusy(value) {
    busy = value;
    sendBtn.disabled = value;
    inputEl.setAttribute('aria-busy', String(value));
    document.body.classList.toggle('is-busy', value);
  }

  /** Grow the message box with its content, up to its CSS max-height. */
  function autoGrow() {
    inputEl.style.height = 'auto';
    // The box is border-box, so its height must include the border that scrollHeight leaves out.
    const border = inputEl.offsetHeight - inputEl.clientHeight;
    inputEl.style.height = (inputEl.scrollHeight + border) + 'px';
  }

  // ── Message rendering ────────────────────────────────────
  /**
   * @param {string | undefined} text
   * @param {Array<Record<string, string>> | null | undefined} table
   * @param {string[] | null | undefined} chips
   * @param {boolean} [showDropZone]
   * @param {'error'} [level]  set for a reply that refuses or could not do what was asked
   * @param {unknown} [view]  a designed view of the same reply, drawn in place of the text
   * @returns {HTMLElement} the new message
   */
  function addAgentMessage(text, table, chips, showDropZone, level, view) {
    const msg = document.createElement('div');
    msg.className = 'message agent';

    const sender = document.createElement('div');
    sender.className = 'message-sender';
    sender.textContent = 'Agent';
    msg.appendChild(sender);

    const body = document.createElement('div');
    body.className = 'message-body';

    if (level === 'error') body.classList.add('is-error');

    if (isIntakeView(view) || isFiguresView(view)) {
      if (view.lead) {
        const lead = document.createElement('div');
        lead.className = 'view-lead';
        lead.innerHTML = renderMarkdown(view.lead); // the server's own text, escaped by renderMarkdown
        body.appendChild(lead);
      }
      body.appendChild(isIntakeView(view) ? renderIntakePanel(view) : renderFiguresView(view));
      body.classList.add('has-view');
    } else {
      body.innerHTML = renderMarkdown(text || '');
    }
    msg.appendChild(body);

    if (table && table.length > 0) {
      body.appendChild(renderTable(table, isFiguresView(view) ? view.column_groups : []));
    }

    if (showDropZone) {
      body.appendChild(createDropZone());
    }

    if (chips && chips.length > 0) {
      const chipsEl = document.createElement('div');
      chipsEl.className = 'chips';
      chips.forEach((chipText) => {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'chip';
        chip.textContent = chipText;
        chip.addEventListener('click', () => sendText(chipText));
        chipsEl.appendChild(chip);
      });
      msg.appendChild(chipsEl);
    }

    messagesEl.appendChild(msg);
    scrollToBottom();
    return msg;
  }

  /**
   * The intake panel. Every label and value is the file's own text, so it is set with textContent.
   * @param {IntakeView} view
   * @returns {HTMLElement}
   */
  function renderIntakePanel(view) {
    const panel = document.createElement('section');
    panel.className = 'panel intake-panel';
    const title = document.createElement('h3');
    title.className = 'panel-title';
    title.textContent = view.title;
    panel.setAttribute('aria-label', view.title);
    panel.appendChild(title);

    const facts = document.createElement('dl');
    facts.className = 'facts';
    view.rows.forEach((row) => {
      const fact = document.createElement('div');
      fact.className = 'fact';
      const dt = document.createElement('dt');
      dt.textContent = row.label;
      const dd = document.createElement('dd');
      dd.textContent = row.value;
      fact.append(dt, dd);
      facts.appendChild(fact);
    });
    panel.appendChild(facts);

    view.notes.forEach((note) => {
      const block = document.createElement('div');
      block.className = 'panel-note';
      const heading = document.createElement('h4');
      heading.textContent = note.title;
      const list = document.createElement('ul');
      note.items.forEach((item) => {
        const li = document.createElement('li');
        li.textContent = item;
        list.appendChild(li);
      });
      if (note.more > 0) {
        const li = document.createElement('li');
        li.className = 'more';
        li.textContent = `and ${note.more} more`;
        list.appendChild(li);
      }
      block.append(heading, list);
      panel.appendChild(block);
    });

    const question = document.createElement('p');
    question.className = 'panel-question';
    question.textContent = view.question;
    panel.appendChild(question);
    return panel;
  }

  /**
   * A text element, or nothing for an empty string.
   * @param {string} tag
   * @param {string} className
   * @param {string | null} text
   * @returns {HTMLElement | null}
   */
  function textEl(tag, className, text) {
    if (!text) return null;
    const el = document.createElement(tag);
    el.className = className;
    el.textContent = text;
    return el;
  }

  /**
   * A status word with its marker: a dot for favorable, a square for unfavorable, a ring for neutral.
   * @param {string} word
   * @param {string | null} tone
   * @returns {HTMLElement}
   */
  function statusEl(word, tone) {
    const el = document.createElement('span');
    el.className = 'status' + (tone ? ` is-${tone}` : '');
    el.textContent = word;
    return el;
  }

  /**
   * Results, a drill-down or a scenario: the title and context, the headline figures, the
   * sections and notes, and the title of the table that follows. Every string is set as text.
   * @param {FiguresView} view
   * @returns {HTMLElement}
   */
  function renderFiguresView(view) {
    const root = document.createElement('section');
    root.className = 'figures-view';
    root.setAttribute('aria-label', view.title);

    const head = document.createElement('div');
    head.className = 'view-head';
    const title = document.createElement('h3');
    title.className = 'view-title';
    title.textContent = view.title;
    head.appendChild(title);
    if (view.context.length) {
      const context = document.createElement('dl');
      context.className = 'view-context';
      view.context.forEach((item) => {
        const pairEl = document.createElement('div');
        const dt = document.createElement('dt');
        dt.textContent = item.label;
        const dd = document.createElement('dd');
        dd.textContent = item.value;
        pairEl.append(dt, dd);
        context.appendChild(pairEl);
      });
      head.appendChild(context);
    }
    root.appendChild(head);

    if (view.figures.length) {
      const strip = document.createElement('div');
      strip.className = 'headline';
      view.figures.forEach((fig) => {
        const cell = document.createElement('div');
        cell.className = 'figure' + (fig.tone ? ` is-${fig.tone}` : '');
        for (const el of [
          textEl('span', 'figure-label', fig.label),
          textEl('span', 'figure-value', fig.value),
          textEl('span', 'figure-meta', fig.compare),
          textEl('span', 'figure-meta', fig.change),
        ]) if (el) cell.appendChild(el);
        if (fig.status) cell.appendChild(statusEl(fig.status, fig.tone));
        strip.appendChild(cell);
      });
      root.appendChild(strip);
    }

    view.sections.forEach((section) => {
      const block = document.createElement('div');
      block.className = 'view-section';
      const heading = document.createElement('h4');
      heading.textContent = section.title;
      const facts = document.createElement('dl');
      facts.className = 'facts';
      section.rows.forEach((row) => {
        const fact = document.createElement('div');
        fact.className = 'fact';
        const dt = document.createElement('dt');
        dt.textContent = row.label;
        const dd = document.createElement('dd');
        dd.className = 'num';
        dd.textContent = row.value;
        fact.append(dt, dd);
        facts.appendChild(fact);
      });
      block.append(heading, facts);
      root.appendChild(block);
    });

    view.notes.forEach((note) => {
      const el = textEl('p', 'view-note', note);
      if (el) root.appendChild(el);
    });
    const tableTitle = textEl('h4', 'table-title', view.table_title);
    if (tableTitle) root.appendChild(tableTitle);
    return root;
  }

  /** @param {string} text */
  function addUserMessage(text) {
    retireChips(Array.from(messagesEl.querySelectorAll('.chips:not(.is-retired)')));
    const msg = document.createElement('div');
    msg.className = 'message user';

    const sender = document.createElement('div');
    sender.className = 'message-sender';
    sender.textContent = 'You';
    msg.appendChild(sender);

    const body = document.createElement('div');
    body.className = 'message-body';
    body.textContent = previewText(text);
    msg.appendChild(body);

    messagesEl.appendChild(msg);
    scrollToBottom();
  }

  /**
   * @param {HTMLElement} msg  The agent message to attach the link to.
   * @param {string} url
   * @param {string | undefined} filename
   */
  function addDownloadLink(msg, url, filename) {
    const link = document.createElement('a');
    link.className = 'download-btn';
    link.href = url;
    link.download = filename || '';
    link.appendChild(createIcon('download', 16));
    link.appendChild(document.createTextNode('Download ' + (filename || 'file')));
    msg.appendChild(link);
  }

  // ── Table rendering ──────────────────────────────────────
  /**
   * The table, its filter (for long tables) and the narrow-screen cue, in one framed block.
   * @param {Array<Record<string, string>>} initialRows
   * @param {Array<{title: string, columns: Array<{key: string, label: string}>}>} [groups]
   *   columns set under a spanning head, each with a short label
   * @returns {HTMLElement}
   */
  function renderTable(initialRows, groups = []) {
    const wrapper = document.createElement('div');
    wrapper.className = 'data-table-wrapper';
    wrapper.setAttribute('role', 'region');
    wrapper.setAttribute('aria-label', 'Data table');
    wrapper.tabIndex = 0; // a scrollable region must be reachable by keyboard

    if (!initialRows || initialRows.length === 0) return wrapper;

    const table = document.createElement('table');
    table.className = 'data-table';

    let currentRows = [...initialRows];
    /** @type {string | null} */
    let sortCol = null;
    let sortAsc = true;

    // A column that is empty in every row says nothing; leave it out of the display.
    const shown = Object.keys(initialRows[0]).filter((col) =>
      col === 'Line Item' || initialRows.some((r) => String(r[col] ?? '').trim() !== ''));
    // Column groups need their columns side by side, so a grouped table keeps its order.
    const narrow = typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 640px)').matches;
    const columns = narrow && groups.length === 0 ? phoneColumnOrder(shown) : shown;
    /** @type {Record<string, {group: string, label: string}>} */
    const grouped = {};
    groups.forEach((g) => g.columns.forEach((c) => { grouped[c.key] = { group: g.title, label: c.label }; }));
    const numeric = new Set(columns.filter((col) => col !== 'Status' && isNumericColumn(initialRows.map((r) => r[col]))));
    /** @param {string} col */
    function isNumericCol(col) {
      return numeric.has(col);
    }
    // Bars go under the first currency variance column only, scaled to that column.
    const barCol = columns.find((col) => /^Var \((?!%)/.test(col) || col.includes('Impact')) || null;

    // Toolbar: quick filter search & row count indicator
    let filterQuery = '';
    const toolbar = document.createElement('div');
    toolbar.className = 'table-toolbar';

    const search = document.createElement('label');
    search.className = 'table-search';
    search.appendChild(createIcon('search', 16));
    const searchInput = document.createElement('input');
    searchInput.type = 'search';
    searchInput.className = 'table-search-input';
    searchInput.placeholder = 'Filter rows';
    searchInput.title = 'Filter rows by account name, type, amount, or status';
    searchInput.setAttribute('aria-label', 'Filter rows');
    search.appendChild(searchInput);

    const countSpan = document.createElement('span');
    countSpan.className = 'table-row-count';
    countSpan.setAttribute('aria-live', 'polite');
    countSpan.textContent = `${initialRows.length} rows`;

    toolbar.appendChild(search);
    toolbar.appendChild(countSpan);
    const block = document.createElement('div');
    block.className = 'table-block';
    if (initialRows.length > 8) block.appendChild(toolbar); // a short table needs no filter

    // Header
    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    /** @type {Record<string, HTMLTableCellElement>} */
    const thMap = {};

    columns.forEach((col) => {
      const th = document.createElement('th');
      th.className = 'sortable' + (isNumericCol(col) ? ' num' : '');
      th.setAttribute('aria-sort', 'none');

      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'th-btn';
      button.title = 'Click to sort';

      const labelSpan = document.createElement('span');
      labelSpan.textContent = Object.hasOwn(grouped, col) ? grouped[col].label : columnLabel(col);
      if (Object.hasOwn(grouped, col)) button.setAttribute('aria-label', `${grouped[col].group} ${grouped[col].label}`);
      button.appendChild(labelSpan);

      const iconSpan = document.createElement('span');
      iconSpan.className = 'sort-icon';
      iconSpan.setAttribute('aria-hidden', 'true');
      iconSpan.appendChild(createIcon('sort', 16));
      button.appendChild(iconSpan);
      th.appendChild(button);

      button.addEventListener('click', () => {
        if (sortCol === col) {
          sortAsc = !sortAsc;
        } else {
          sortCol = col;
          sortAsc = !isNumericCol(col);
        }

        columns.forEach((c) => {
          thMap[c].classList.remove('sorted-asc', 'sorted-desc');
          thMap[c].setAttribute('aria-sort', 'none');
          const ic = thMap[c].querySelector('.sort-icon');
          if (ic) ic.replaceChildren(createIcon('sort', 16));
        });

        th.classList.add(sortAsc ? 'sorted-asc' : 'sorted-desc');
        th.setAttribute('aria-sort', sortAsc ? 'ascending' : 'descending');
        iconSpan.replaceChildren(createIcon(sortAsc ? 'sort-asc' : 'sort-desc', 16));

        updateTable();
      });

      thMap[col] = th;
      headerRow.appendChild(th);
    });
    if (columns.some((col) => Object.hasOwn(grouped, col))) {
      // One spanning head per comparison over its columns; other columns get an empty cell.
      const groupRow = document.createElement('tr');
      groupRow.className = 'group-row';
      let i = 0;
      while (i < columns.length) {
        const name = Object.hasOwn(grouped, columns[i]) ? grouped[columns[i]].group : '';
        let span = 1;
        while (name && i + span < columns.length && Object.hasOwn(grouped, columns[i + span])
          && grouped[columns[i + span]].group === name) span += 1;
        const th = document.createElement('th');
        th.colSpan = span;
        th.scope = 'colgroup';
        th.textContent = name;
        if (name) th.className = 'group-head';
        groupRow.appendChild(th);
        i += span;
      }
      thead.appendChild(groupRow);
    }
    thead.appendChild(headerRow);
    table.appendChild(thead);

    function updateTable() {
      const filtered = initialRows.filter((row) => {
        if (!filterQuery) return true;
        return columns.some((col) => String(row[col] || '').toLowerCase().includes(filterQuery));
      });

      const column = sortCol;
      if (column) {
        filtered.sort((a, b) => {
          const valA = a[column] || '';
          const valB = b[column] || '';
          if (isNumericCol(column)) {
            const numA = parseNumericVal(valA);
            const numB = parseNumericVal(valB);
            return sortAsc ? numA - numB : numB - numA;
          }
          const strA = String(valA).toLowerCase();
          const strB = String(valB).toLowerCase();
          if (strA < strB) return sortAsc ? -1 : 1;
          if (strA > strB) return sortAsc ? 1 : -1;
          return 0;
        });
      }

      currentRows = filtered;
      countSpan.textContent = filterQuery
        ? `${currentRows.length} of ${initialRows.length} rows`
        : `${currentRows.length} rows`;
      renderBody();
    }

    searchInput.addEventListener('input', () => {
      filterQuery = searchInput.value.toLowerCase().trim();
      updateTable();
    });

    // Body
    const tbody = document.createElement('tbody');
    function renderBody() {
      tbody.textContent = '';

      let maxVar = 0;
      if (barCol) {
        currentRows.forEach((row) => {
          maxVar = Math.max(maxVar, Math.abs(parseNumericVal(row[barCol])));
        });
      }

      currentRows.forEach((row) => {
        const tr = document.createElement('tr');
        const status = row['Status'] || '';

        columns.forEach((col) => {
          const td = document.createElement('td');
          const val = row[col] || '';
          if (isNumericCol(col)) td.className = 'num';
          if (col === 'Status' || (Object.hasOwn(grouped, col) && grouped[col].label === 'Outcome')) {
            const shown = statusWord(plainText(val));
            td.appendChild(statusEl(shown.word, shown.tone));
          } else if (col === 'Line Item') {
            const name = plainText(val);
            const link = document.createElement('button');
            link.type = 'button';
            link.className = 'item-link';
            link.textContent = name;
            link.title = `Click to drill down: Why ${name}?`;
            link.addEventListener('click', () => {
              const question = `Why ${name}?`;
              sendText(question);
            });
            td.appendChild(link);
          } else if (col === barCol) {
            const numVal = parseNumericVal(val);
            const absVal = Math.abs(numVal);
            const pct = maxVar > 0 ? Math.min(100, Math.round((absVal / maxVar) * 100)) : 0;

            const cellWrapper = document.createElement('div');
            cellWrapper.className = 'variance-cell';

            const valSpan = document.createElement('span');
            valSpan.className = 'variance-val';
            valSpan.textContent = plainText(val);
            cellWrapper.appendChild(valSpan);

            if (maxVar > 0 && absVal > 0) {
              const barTrack = document.createElement('div');
              barTrack.className = 'variance-bar-track';
              barTrack.setAttribute('aria-hidden', 'true');
              const barFill = document.createElement('div');
              const tone = statusWord(status).tone;
              barFill.className = 'variance-bar-fill ' +
                (tone === 'favorable' ? 'bar-favorable' : tone === 'unfavorable' ? 'bar-unfavorable' : 'bar-neutral');
              barFill.style.width = Math.max(5, pct) + '%'; // CSSOM, which a strict CSP allows
              barTrack.appendChild(barFill);
              cellWrapper.appendChild(barTrack);
            }
            td.appendChild(cellWrapper);
          } else {
            td.textContent = plainText(val);
          }
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
    }

    renderBody();
    table.appendChild(tbody);

    wrapper.appendChild(table);
    const scroller = wrapper;

    // On a narrow screen the first column stays put and a cue says more columns exist (T8).
    const cue = document.createElement('div');
    cue.className = 'table-cue';
    cue.setAttribute('aria-hidden', 'true');
    cue.appendChild(document.createTextNode('More columns'));
    cue.appendChild(createIcon('more', 16));
    block.append(wrapper, cue);
    const updateCue = () => {
      const overflow = scroller.scrollWidth > scroller.clientWidth + 1;
      const atEnd = scroller.scrollLeft + scroller.clientWidth >= scroller.scrollWidth - 1;
      block.classList.toggle('has-more', overflow && !atEnd);
    };
    scroller.addEventListener('scroll', updateCue, { passive: true });
    window.addEventListener('resize', updateCue);
    requestAnimationFrame(updateCue);
    return block;
  }

  // ── Drop zone ────────────────────────────────────────────
  function createDropZone() {
    const zone = document.createElement('div');
    zone.className = 'drop-zone';
    zone.setAttribute('role', 'button');
    zone.setAttribute('aria-label', 'Upload a file: press Enter to browse, or drop one here');
    zone.tabIndex = 0;

    const zoneIcon = document.createElement('div');
    zoneIcon.className = 'drop-zone-icon';
    zoneIcon.appendChild(createIcon('upload', 20));
    const zoneTitle = document.createElement('div');
    zoneTitle.className = 'drop-zone-title';
    zoneTitle.textContent = 'Drop a file here, or choose one';
    const zoneSubtitle = document.createElement('div');
    zoneSubtitle.className = 'drop-zone-subtitle';
    zoneSubtitle.textContent = 'CSV, JSON, Excel (.xlsx, .xlsm) or a PDF 10-K or 10-Q, up to ' +
      `${MAX_UPLOAD_BYTES / 1048576} MB`;
    zone.append(zoneIcon, zoneTitle, zoneSubtitle);

    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = VALID_EXTENSIONS.join(',');
    fileInput.tabIndex = -1;
    zone.appendChild(fileInput);

    zone.addEventListener('click', (e) => {
      if (e.target !== fileInput) fileInput.click();
    });

    zone.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        fileInput.click();
      }
    });

    zone.addEventListener('dragover', (e) => {
      e.preventDefault();
      zone.classList.add('dragover');
    });

    zone.addEventListener('dragleave', () => {
      zone.classList.remove('dragover');
    });

    zone.addEventListener('drop', (e) => {
      e.preventDefault();
      zone.classList.remove('dragover');
      const files = e.dataTransfer ? e.dataTransfer.files : null;
      if (files && files.length > 0) uploadFile(files[0]);
    });

    fileInput.addEventListener('change', () => {
      if (fileInput.files && fileInput.files.length > 0) uploadFile(fileInput.files[0]);
    });

    return zone;
  }

  // The working indicator: nothing for the first 100 ms, then a line saying what is happening,
  // and after a second a flat skeleton where the reply will go.
  /** @type {ReturnType<typeof setTimeout> | undefined} */
  let indicatorTimer;
  /** @type {ReturnType<typeof setTimeout> | undefined} */
  let skeletonTimer;

  /** @param {string} [what]  shown beside the dots, for example "Reading the file" */
  function showTypingIndicator(what = 'Working on it') {
    removeTypingIndicator();
    indicatorTimer = setTimeout(() => {
      const msg = document.createElement('div');
      msg.className = 'message agent working';
      msg.id = 'typing-indicator';
      msg.setAttribute('role', 'status');

      const sender = document.createElement('div');
      sender.className = 'message-sender';
      sender.textContent = 'Agent';
      msg.appendChild(sender);

      const body = document.createElement('div');
      body.className = 'message-body typing-dots';
      for (let i = 0; i < 3; i += 1) body.appendChild(document.createElement('span'));
      const label = document.createElement('span');
      label.className = 'working-label';
      label.textContent = what;
      body.appendChild(label);
      msg.appendChild(body);

      const skeleton = document.createElement('div');
      skeleton.className = 'skeleton';
      skeleton.setAttribute('aria-hidden', 'true');
      for (let i = 0; i < 3; i += 1) skeleton.appendChild(document.createElement('div'));
      msg.appendChild(skeleton);

      messagesEl.appendChild(msg);
      scrollToBottom();
      skeletonTimer = setTimeout(() => msg.classList.add('is-long'), 900);
    }, 100);
  }

  function removeTypingIndicator() {
    clearTimeout(indicatorTimer);
    clearTimeout(skeletonTimer);
    const el = document.getElementById('typing-indicator');
    if (el) el.remove();
  }

  // ── Requests ─────────────────────────────────────────────
  /**
   * Show the outcome of a request: an error as a warning bubble, otherwise the reply.
   * @param {JsonResult} result
   * @param {boolean} fromUpload  A failed upload offers the drop zone again.
   */
  function showResult(result, fromUpload) {
    const data = result.data;
    if (!result.ok || !data || data.error) {
      addAgentMessage(describeFailure(result.status, data), null, null, fromUpload, 'error');
      return;
    }

    // A table pasted while waiting for a file is this visitor's first file too.
    const leftUploadStep = data.phase && data.phase !== 'awaiting_file';
    if (leftUploadStep && (fromUpload || currentPhase === 'awaiting_file')) markIntroSeen();
    if (data.phase) updatePhase(data.phase);

    // A reply asking for a second file (LTM's 10-K, the other half of a pair) shows the drop zone too.
    const showDrop = data.ask_upload === true || (!fromUpload && data.phase === 'awaiting_file');
    const msg = addAgentMessage(data.text, data.table, data.chips, showDrop, data.level, data.view);
    if (data.download_url) {
      addDownloadLink(msg, data.download_url, data.download_filename);
    }
  }

  /**
   * Run one request at a time: the server is single-threaded and the session is shared, so a
   * second click while one is pending waits for nothing and is ignored instead.
   * @param {() => Promise<void>} task
   * @returns {Promise<boolean>} false when another request was still in flight
   */
  async function runExclusive(task) {
    if (busy) return false;
    setBusy(true);
    try {
      await task();
    } finally {
      setBusy(false);
    }
    return true;
  }

  // ── File upload ──────────────────────────────────────────
  /** @param {File} file */
  async function uploadFile(file) {
    if (busy) return;

    const ext = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!VALID_EXTENSIONS.includes(ext)) {
      addAgentMessage(
        'Unsupported file format. Please upload a CSV, JSON, Excel (.xlsx, .xlsm, .xls), PDF or HTML file.',
        null, null, true, 'error'
      );
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      addAgentMessage(
        `That file is ${(file.size / 1048576).toFixed(1)} MB; the limit is ` +
        `${MAX_UPLOAD_BYTES / 1048576} MB.`,
        null, null, true, 'error'
      );
      return;
    }

    await runExclusive(async () => {
      addUserMessage(file.name);
      document.querySelectorAll('.drop-zone').forEach((z) => z.remove());

      const formData = new FormData();
      formData.append('file', file, file.name);
      formData.append('first_visit', introSeen ? '0' : '1');

      showTypingIndicator('Reading the file');
      try {
        const result = await requestJson(
          '/upload', { method: 'POST', body: formData }, UPLOAD_TIMEOUT_MS
        );
        removeTypingIndicator();
        showResult(result, true);
        inputEl.focus();
      } catch (err) {
        removeTypingIndicator();
        addAgentMessage('Upload failed: ' + errorMessage(err), null, null, true, 'error');
      }
    });
  }

  // ── Sending messages ─────────────────────────────────────
  /** Send what is in the message box. */
  async function sendMessage() {
    if (busy) return; // keep the draft; it is sent when the user presses Enter again
    // trim() only touches the ends: line breaks inside a pasted table must reach the server.
    const text = inputEl.value.trim();
    if (!text) return;
    if (text.length > MAX_MESSAGE_CHARS) {
      addAgentMessage(
        `That message is too long (${text.length.toLocaleString('en-US')} characters; the ` +
        `limit is ${MAX_MESSAGE_CHARS.toLocaleString('en-US')}). Upload large data as a file instead.`,
        null, null, false, 'error'
      );
      return;
    }
    inputEl.value = '';
    autoGrow();
    await sendText(text);
  }

  /**
   * Send a message that is not in the box (a chip, a table row, Help or Reset).
   * @param {string} text
   */
  async function sendText(text) {
    await runExclusive(async () => {
      addUserMessage(text);
      await postMessage(text);
    });
  }

  /** @param {string} text */
  async function postMessage(text) {
    showTypingIndicator();
    try {
      const result = await requestJson('/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, first_visit: !introSeen }),
      }, MESSAGE_TIMEOUT_MS);
      removeTypingIndicator();
      showResult(result, false);
    } catch (err) {
      removeTypingIndicator();
      addAgentMessage(errorMessage(err), null, null, false, 'error');
    }
  }

  /**
   * @param {unknown} err
   * @returns {string}
   */
  function errorMessage(err) {
    return err instanceof Error ? err.message : String(err);
  }

  // ── Utilities ────────────────────────────────────────────
  function scrollToBottom() {
    requestAnimationFrame(() => {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    });
  }

  init();
}

if (typeof document !== 'undefined') boot();
