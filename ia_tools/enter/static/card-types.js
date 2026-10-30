// IA card types: whether each reward Feat and Imperial class card is a Feat or a Group Attachment, proposed from the
// wiki's card text. Every change is saved to staging/card-types/entries.json on the server; ia card-types writes them into
// the data repo once every card is done.

import {fill, h, request} from './dom.js';

const $ = sel => document.querySelector(sel);
const sidebar = $('#sidebar');
const main = $('#main');

const FILTERS = [['all', 'All'], ['todo', 'To do'], ['flagged', 'Flagged'], ['done', 'Done']];

let panel = null;      // GET /api/card-types
let collection = null; // content type shown
let filter = 'todo';
let typeFilter = null; // a type, or null for all

const image = path => `/data-images/small/${path}`;
// What a card shows: its entry, or the proposal until it has one.
const valueOf = card => panel.entries[card.id] || {type: card.proposal.type, done: false};
const isDone = card => !!panel.entries[card.id]?.done;

function visible(card) {
  if (card.content_type !== collection) return false;
  if (typeFilter && valueOf(card).type !== typeFilter) return false;
  if (filter === 'todo') return !isDone(card);
  if (filter === 'flagged') return card.proposal.flags.length > 0 || (panel.problems[card.id] || []).length > 0;
  if (filter === 'done') return isDone(card);
  return true;
}

function progress() {
  const done = panel.cards.filter(isDone).length;
  $('#progress').textContent = `${done} of ${panel.cards.length} cards done`;
  fill($('#tabs'), Object.keys(panel.collections).map(type => {
    const cards = panel.cards.filter(c => c.content_type === type);
    return h('a', {href: `#${type}`, 'aria-current': String(type === collection)},
      `${type.replace(/-cards$/, '')} ${cards.filter(isDone).length}/${cards.length}`);
  }));
}

function renderSidebar() {
  const cards = panel.cards.filter(c => c.content_type === collection);
  const counts = new Map();
  for (const card of cards) counts.set(valueOf(card).type, (counts.get(valueOf(card).type) || 0) + 1);
  fill(sidebar,
    h('div', {class: 'filters'}, FILTERS.map(([value, text]) => h('button', {type: 'button',
      'aria-pressed': String(filter === value), onclick: () => { filter = value; render(); }}, text))),
    [[null, `All types (${cards.length})`], ...panel.collections[collection].filter(t => counts.has(t))
      .map(t => [t, `${t} (${counts.get(t)})`])].map(([value, text]) => h('a', {href: `#${collection}`,
      'aria-current': typeFilter === value ? 'true' : null, onclick: e => {
        e.preventDefault(); typeFilter = value; render();
      }}, h('span', {class: 'name'}, text))),
  );
  progress();
}

async function save(card, entry) {
  panel.entries[card.id] = entry;
  const result = await request('PUT', `/api/card-types/${encodeURIComponent(card.id)}`, entry);
  panel.problems[card.id] = result.problems;
}

async function change(card, f) {
  const next = structuredClone(valueOf(card));
  f(next);
  await save(card, next);
  render();
}

function tile(card) {
  const value = valueOf(card);
  const problems = panel.problems[card.id] || [];
  return h('div', {class: `type-card${isDone(card) ? ' done' : ''}`},
    h('img', {src: image(card.image), alt: card.name, loading: 'lazy'}),
    h('div', {}, h('strong', {}, card.name), card.owner ? h('span', {class: 'muted'}, ` ${card.owner}`) : null),
    h('select', {'aria-label': `${card.name} type`, onchange: e => change(card, n => { n.type = e.target.value; })},
      panel.collections[card.content_type].map(t => h('option', {value: t, selected: t === value.type}, t))),
    card.proposal.lines.length
      ? h('ul', {class: 'lines'}, card.proposal.lines.map(line => h('li', {}, line)))
      : null,
    card.proposal.flags.map(flag => h('p', {class: 'flag'}, flag)),
    problems.length ? h('ul', {class: 'problems'}, problems.map(p => h('li', {}, p))) : null,
    h('label', {}, h('input', {type: 'checkbox', checked: isDone(card),
      onchange: e => change(card, n => { n.done = e.target.checked; })}), ' Done'),
  );
}

async function confirmShown(cards) {
  for (const card of cards) if (!isDone(card)) await save(card, {...structuredClone(valueOf(card)), done: true});
  render();
}

function render() {
  renderSidebar();
  const cards = panel.cards.filter(visible);
  const scroll = window.scrollY;
  fill(main,
    h('h1', {}, collection),
    h('p', {class: 'meta'}, 'Proposed from the wiki’s card text (shown under each card). ',
      'A Group Attachment is attached to an Imperial deployment group; every other card here is a Feat. ',
      'Tick Done when a card is right, or confirm all the cards shown once you’ve looked at them.'),
    h('div', {class: 'bar'}, h('button', {type: 'button', disabled: !cards.some(c => !isDone(c)),
      onclick: () => confirmShown(cards)}, `Mark the ${cards.filter(c => !isDone(c)).length} shown as done`)),
    cards.length ? h('div', {class: 'type-grid'}, cards.map(tile)) : h('p', {class: 'muted'}, 'No cards here.'),
  );
  window.scrollTo(0, scroll);
}

// Routing: #<collection>

function route() {
  const wanted = location.hash.slice(1);
  collection = wanted in panel.collections ? wanted : Object.keys(panel.collections)[0];
  typeFilter = null;
  render();
}

async function start() {
  panel = await request('GET', '/api/card-types');
  window.addEventListener('hashchange', route);
  route();
}

start().catch(error => {
  console.error(error);
  fill(main, h('p', {class: 'problems'}, String(error)));
});
