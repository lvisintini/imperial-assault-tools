// IA map layouts: the tile sides each skirmish and raid map is built from, map by map. Every change is saved to
// staging/map-layouts/entries.json on the server; ia layouts writes the maps marked done into map-layouts.json.

import {fill, h, request} from './dom.js';

const $ = sel => document.querySelector(sel);
const sidebar = $('#sidebar');
const main = $('#main');

const FILTERS = [['all', 'All'], ['todo', 'To do'], ['done', 'Done']];
// A quick-add code: an optional product code (CODES), the tile's number, its side, and optionally "x<count>".
const CODE = /^([a-z]*)\s*0*(\d+)\s*([ab])(?:\s*[x×]\s*(\d+))?$/i;

let panel = null;     // GET /api/layouts
let tiles = null;     // tile id → tile
let current = null;   // map id
let filter = 'all';
let product = null;   // the tile picker's product, or null for all

const entryOf = id => panel.entries[id] || {tiles: [], done: false, note: ''};
const sideImage = (tile, side) => `/data-images/small/${side === 'A' ? tile.side_a : tile.side_b}`;
const codeOf = (tile, side) => `${tile.code ? `${tile.code} ` : ''}${String(tile.number).padStart(2, '0')}${side}`;

function findTile(code, number) {
  const products = Object.entries(panel.codes).filter(([, c]) => c.toLowerCase() === code.toLowerCase()).map(([p]) => p);
  return panel.tiles.find(t => products.includes(t.product) && t.number === number);
}

// Sidebar

function visible(map) {
  const done = !!panel.entries[map.id]?.done;
  return filter === 'all' || (filter === 'done') === done;
}

function renderSidebar() {
  const chip = map => {
    const entry = panel.entries[map.id];
    if (panel.problems[map.id]?.length) return h('span', {class: 'chip skip'}, 'problems');
    if (entry?.done) return h('span', {class: 'chip new'}, 'done');
    if (entry?.tiles.length) return h('span', {class: 'chip'}, `${entry.tiles.length} sides`);
    return h('span', {class: 'chip'}, map.rows ? `${map.rows} in data` : '—');
  };
  fill(sidebar,
    h('div', {class: 'filters'}, FILTERS.map(([value, label]) => h('button', {type: 'button',
      'aria-pressed': String(filter === value), onclick: () => { filter = value; renderSidebar(); }}, label))),
    panel.maps.filter(visible).map(map => h('a', {href: `#${map.id}`, 'aria-current': current === map.id ? 'true' : null},
      h('span', {class: 'name'}, map.name), chip(map))),
  );
  const done = panel.maps.filter(m => panel.entries[m.id]?.done).length;
  $('#progress').textContent = `${done} of ${panel.maps.length} maps done`;
}

// The map

async function save(id, entry) {
  panel.entries[id] = entry;
  const result = await request('PUT', `/api/layouts/${encodeURIComponent(id)}`, entry);
  panel.problems[id] = result.problems;
  renderSidebar();
  if (current === id) renderMap(id);
}

function addSide(id, tile, side, count = 1) {
  const entry = structuredClone(entryOf(id));
  const row = entry.tiles.find(r => r.tile_id === tile.id && r.side === side);
  if (row) row.count += count;
  else entry.tiles.push({tile_id: tile.id, side, count});
  return save(id, entry);
}

function quickAdd(id, text, report) {
  const unknown = [];
  const adds = [];
  for (const token of text.split(',').map(s => s.trim()).filter(Boolean)) {
    const match = token.match(CODE);
    const tile = match && findTile(match[1], Number(match[2]));
    if (!tile) unknown.push(token);
    else adds.push([tile, match[3].toUpperCase(), Number(match[4] || 1)]);
  }
  if (unknown.length) {
    report.textContent = `Unknown: ${unknown.join(', ')}`;
    return false;
  }
  const entry = structuredClone(entryOf(id));
  for (const [tile, side, count] of adds) {
    const row = entry.tiles.find(r => r.tile_id === tile.id && r.side === side);
    if (row) row.count += count;
    else entry.tiles.push({tile_id: tile.id, side, count});
  }
  save(id, entry);
  return true;
}

function rowsPanel(id) {
  const entry = entryOf(id);
  const change = f => { const next = structuredClone(entry); f(next); save(id, next); };
  const rows = entry.tiles.map((row, i) => {
    const tile = tiles.get(row.tile_id);
    if (!tile) return h('div', {class: 'tile-row'}, h('span', {class: 'problems'}, `Unknown tile ${row.tile_id}`));
    return h('div', {class: 'tile-row'},
      h('img', {src: sideImage(tile, row.side), alt: '', loading: 'lazy'}),
      h('span', {class: 'name'}, `${tile.name}${row.side}`, h('span', {class: 'muted'}, ` ${codeOf(tile, row.side)} · ${tile.copies} in the boxes`)),
      h('button', {type: 'button', 'aria-label': 'One fewer', onclick: () => change(e => {
        if (e.tiles[i].count > 1) e.tiles[i].count -= 1; else e.tiles.splice(i, 1);
      })}, '−'),
      h('strong', {class: 'count'}, `×${row.count}`),
      h('button', {type: 'button', 'aria-label': 'One more', onclick: () => change(e => { e.tiles[i].count += 1; })}, '+'),
      h('button', {type: 'button', 'aria-label': 'Remove', onclick: () => change(e => { e.tiles.splice(i, 1); })}, '✕'),
    );
  });
  const report = h('span', {class: 'muted'});
  const input = h('input', {type: 'text', placeholder: '05A, TS 1B, JR3A x2', 'aria-label': 'Quick add', onkeydown: e => {
    if (e.key === 'Enter' && quickAdd(id, e.target.value, report)) e.target.value = '';
  }});
  const problems = panel.problems[id] || [];
  return h('div', {class: 'panel'},
    h('h2', {}, `Tile sides (${entry.tiles.reduce((n, r) => n + r.count, 0)})`),
    rows.length ? rows : h('p', {class: 'muted'}, 'None yet: add them with the codes below or from the tiles further down.'),
    h('div', {class: 'bar'}, input, report),
    h('p', {class: 'help muted'}, 'Codes as Vassal names the pieces: ',
      Object.entries(panel.codes).map(([p, c]) => `${c || '(none)'} ${p}`).join(' · '), '. Separate several with commas.'),
    h('div', {class: 'bar'},
      h('label', {}, h('input', {type: 'checkbox', checked: !!entry.done, onchange: e => change(n => { n.done = e.target.checked; })}), ' Done'),
      h('input', {type: 'text', value: entry.note || '', placeholder: 'Note (not imported)', 'aria-label': 'Note',
        onchange: e => change(n => { n.note = e.target.value; })}),
    ),
    problems.length ? h('ul', {class: 'problems'}, problems.map(p => h('li', {}, p))) : null,
  );
}

function picker(id) {
  const shown = panel.tiles.filter(t => !product || t.product === product);
  return h('div', {class: 'panel'},
    h('h2', {}, 'Tiles'),
    h('div', {class: 'filters'},
      [[null, 'All'], ...panel.products.map(p => [p, p])].map(([value, label]) => h('button', {type: 'button',
        'aria-pressed': String(product === value), onclick: () => { product = value; renderMap(id); }}, label))),
    h('div', {class: 'tile-grid'}, shown.map(tile => h('div', {class: 'tile-card'},
      h('div', {class: 'muted'}, `${tile.name} ×${tile.copies}`),
      ['A', 'B'].map(side => h('button', {type: 'button', class: 'tile-side', title: `Add ${tile.name}${side}`,
        onclick: () => addSide(id, tile, side)},
      h('img', {src: sideImage(tile, side), alt: '', loading: 'lazy'}), h('span', {}, side))),
    ))),
  );
}

function renderMap(id) {
  const map = panel.maps.find(m => m.id === id);
  if (!map) return fill(main, h('p', {class: 'muted'}, 'Pick a map on the left.'));
  const scroll = window.scrollY;
  const focused = document.activeElement?.getAttribute('aria-label');
  fill(main,
    h('h1', {}, map.name),
    h('p', {class: 'meta'}, [map.missions.join(' · '), map.products.join(', ')].filter(Boolean).join(' — '),
      map.rows ? ` — ${map.rows} rows in the data now, replaced when this map is imported` : ''),
    h('div', {class: 'layout-editor'},
      h('figure', {class: 'map-image'}, map.image
        ? h('img', {src: `/data-images/small/${map.image}`, alt: map.name})
        : h('p', {class: 'muted'}, 'No image yet.')),
      rowsPanel(id),
    ),
    picker(id),
  );
  window.scrollTo(0, scroll);
  if (focused) main.querySelector(`[aria-label="${focused}"]`)?.focus();
}

// Routing: #<map id>

function route() {
  current = location.hash.slice(1) || panel.maps[0]?.id;
  renderSidebar();
  renderMap(current);
}

async function start() {
  panel = await request('GET', '/api/layouts');
  tiles = new Map(panel.tiles.map(t => [t.id, t]));
  window.addEventListener('hashchange', route);
  route();
}

start().catch(error => {
  console.error(error);
  fill(main, h('p', {class: 'problems'}, String(error)));
});
