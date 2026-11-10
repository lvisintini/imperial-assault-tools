// IA tile connections: how many connector tabs each map tile has (the same on both sides), one key per tile. A digit
// (numpad or top row) sets the tile's number and moves on; ← → move without changing anything. Every change is saved
// to staging/tile-connections/entries.json on the server; the last step reviews them all and confirms, and
// ia tile-connections writes them into the data repo's map-tiles.json.

import {fill, h, request} from './dom.js';

const main = document.querySelector('#main');
const progressEl = document.querySelector('#progress');
const ADVANCE_MS = 150;

let panel = null;     // GET /api/tile-connections
let index = 0;        // the tile shown
let view = 'entry';   // 'entry' or 'confirm'
let busy = false;     // between a digit and the move to the next tile
let error = null;

const image = (size, path) => `/data-images/${size}/${path}`;
const tiles = () => panel.tiles;
const valueOf = tile => panel.entries.tiles[tile.id]?.connections;
const hasValue = tile => valueOf(tile) !== undefined;
const missing = () => tiles().filter(t => !hasValue(t));
const firstMissing = () => Math.max(0, tiles().findIndex(t => !hasValue(t)));

function progress() {
  const done = tiles().length - missing().length;
  progressEl.textContent = `${done} of ${tiles().length} tiles entered${panel.entries.confirmed ? ' · confirmed' : ''}`;
}

async function setValue(tile, value) {
  const before = panel.entries.tiles[tile.id];
  if (value === null) delete panel.entries.tiles[tile.id];
  else panel.entries.tiles[tile.id] = {connections: value};
  panel.entries.confirmed = false;
  try {
    await request('PUT', `/api/tile-connections/${encodeURIComponent(tile.id)}`, {connections: value});
    error = null;
  } catch (e) {
    if (before) panel.entries.tiles[tile.id] = before; else delete panel.entries.tiles[tile.id];
    error = `Not saved: ${e.message}`;
  }
}

function go(to) {
  if (to >= tiles().length) { view = 'confirm'; render(); return; }
  view = 'entry';
  index = Math.max(0, Math.min(tiles().length - 1, to));
  render();
}

function preload(i) {
  const tile = tiles()[i];
  if (tile) for (const path of [tile.side_a, tile.side_b]) new Image().src = image('large', path);
}

// Entry: one tile at a time

function strip() {
  return h('div', {class: 'strip', role: 'list'}, tiles().map((tile, i) => h('button', {
    type: 'button', role: 'listitem', title: `${tile.name}${hasValue(tile) ? `: ${valueOf(tile)}` : ''}`,
    class: `cell${hasValue(tile) ? ' filled' : ''}${i === index && view === 'entry' ? ' here' : ''}`,
    onclick: () => go(i),
  }, hasValue(tile) ? String(valueOf(tile)) : '')));
}

function renderEntry() {
  const tile = tiles()[index];
  preload(index + 1);
  fill(main,
    h('div', {class: 'entry-head'},
      h('div', {},
        h('h1', {}, tile.name),
        h('p', {class: 'meta'}, `Tile ${index + 1} of ${tiles().length} · ${tile.squares} squares`)),
      h('div', {class: `value${hasValue(tile) ? '' : ' empty'}`, id: 'value'}, hasValue(tile) ? String(valueOf(tile)) : '–')),
    h('div', {class: 'sides'},
      h('figure', {class: 'side-a'}, h('img', {src: image('large', tile.side_a), alt: `${tile.name} side A`}),
        h('figcaption', {}, 'Side A')),
      h('figure', {class: 'side-b'}, h('img', {src: image('large', tile.side_b), alt: `${tile.name} side B`}),
        h('figcaption', {}, 'Side B'))),
    h('p', {class: 'keys muted'},
      h('kbd', {}, '0'), '–', h('kbd', {}, String(panel.limit)), ' set the tabs and move on · ',
      h('kbd', {}, '←'), ' ', h('kbd', {}, '→'), ' back / forward · ',
      h('kbd', {}, 'Enter'), ' keep and move on · ', h('kbd', {}, 'Backspace'), ' clear · ',
      h('kbd', {}, 'Home'), ' first tile left · ', h('kbd', {}, 'End'), ' review'),
    error ? h('p', {class: 'problems'}, error) : null,
    strip(),
  );
}

// Confirmation: every tile, then Confirm

function thumb(tile, flag) {
  return h('a', {href: '#', class: `confirm-tile${hasValue(tile) ? '' : ' missing'}${flag ? ' flagged' : ''}`,
    onclick: e => { e.preventDefault(); go(tiles().indexOf(tile)); }},
    h('img', {src: image('small', tile.side_a), alt: '', loading: 'lazy'}),
    h('span', {class: 'name'}, tile.name),
    h('span', {class: 'number'}, hasValue(tile) ? String(valueOf(tile)) : '–'),
    flag ? h('span', {class: 'flag'}, flag) : null);
}

function flagOf(tile) {
  const outline = panel.outline[tile.id];
  if (!hasValue(tile)) return 'no number yet';
  if (outline != null && outline !== valueOf(tile)) return `look again: the outline shows ${outline}`;
  return null;
}

function renderConfirm() {
  const left = missing();
  const flagged = tiles().filter(t => hasValue(t) && flagOf(t));
  const products = [...new Set(tiles().map(t => t.product))];
  fill(main,
    h('h1', {}, 'Review and confirm'),
    h('p', {class: 'meta'},
      `${tiles().length - left.length} of ${tiles().length} tiles have a number. `,
      flagged.length ? `${flagged.length} differ from a count of the tabs on their outline: worth a second look. ` : '',
      'Click a tile to go back to it; ', h('kbd', {}, '←'), ' goes back to the last one.'),
    h('div', {class: 'bar'},
      h('button', {type: 'button', class: 'primary', disabled: left.length > 0 || panel.entries.confirmed,
        onclick: confirm}, panel.entries.confirmed ? 'Confirmed' : `Confirm all ${tiles().length}`),
      panel.entries.confirmed ? h('span', {class: 'ok'}, 'Confirmed: run ia tile-connections to write them.') : null,
      left.length ? h('span', {class: 'problems'}, `${left.length} tiles still need a number.`) : null),
    error ? h('p', {class: 'problems'}, error) : null,
    left.length ? [h('h2', {}, 'No number yet'), h('div', {class: 'confirm-grid'}, left.map(t => thumb(t, flagOf(t))))] : null,
    flagged.length ? [h('h2', {}, 'Look again'), h('div', {class: 'confirm-grid'}, flagged.map(t => thumb(t, flagOf(t))))] : null,
    products.map(product => {
      const mine = tiles().filter(t => t.product === product);
      return [h('h2', {}, `${product} `, h('span', {class: 'muted'}, String(mine.length))),
        h('div', {class: 'confirm-grid'}, mine.map(t => thumb(t, hasValue(t) ? flagOf(t) : null)))];
    }),
  );
}

async function confirm() {
  try {
    const result = await request('PUT', '/api/tile-connections/confirmed', true);
    panel.entries.confirmed = result.confirmed;
    error = null;
  } catch (e) {
    error = `Not confirmed: ${e.message}`;
  }
  render();
}

function render() {
  progress();
  if (view === 'confirm') renderConfirm(); else renderEntry();
}

// Keys

function digitOf(e) {
  if (/^[0-9]$/.test(e.key)) return Number(e.key);
  const numpad = /^Numpad([0-9])$/.exec(e.code);  // NumLock off
  return numpad ? Number(numpad[1]) : null;
}

async function onKey(e) {
  if (e.ctrlKey || e.metaKey || e.altKey || busy) return;
  if (view === 'confirm') {
    if (e.key === 'ArrowLeft' || e.key === 'PageUp' || e.key === 'Escape') { e.preventDefault(); go(tiles().length - 1); }
    else if (e.key === 'Home') { e.preventDefault(); go(firstMissing()); }
    return;
  }
  const tile = tiles()[index];
  const digit = digitOf(e);
  if (digit !== null && digit <= panel.limit) {
    e.preventDefault();
    if (e.repeat) return;
    busy = true;
    await setValue(tile, digit);
    render();
    document.querySelector('#value')?.classList.add('flash');
    setTimeout(() => { busy = false; if (!error) go(index + 1); }, ADVANCE_MS);
    return;
  }
  switch (e.key) {
    case 'ArrowRight': case 'PageDown': e.preventDefault(); go(index + 1); break;
    case 'ArrowLeft': case 'PageUp': e.preventDefault(); go(index - 1); break;
    case 'Enter': e.preventDefault(); if (hasValue(tile)) go(index + 1); break;
    case 'Backspace': case 'Delete': e.preventDefault(); await setValue(tile, null); render(); break;
    case 'Home': e.preventDefault(); go(firstMissing()); break;
    case 'End': e.preventDefault(); go(tiles().length); break;
  }
}

async function start() {
  panel = await request('GET', '/api/tile-connections');
  document.addEventListener('keydown', onKey);
  if (missing().length) go(firstMissing());
  else { view = 'confirm'; render(); }
}

start().catch(e => {
  console.error(e);
  fill(main, h('p', {class: 'problems'}, String(e)));
});
