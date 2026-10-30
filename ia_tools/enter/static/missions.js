// IA missions: each skirmish mission card's scenario (A or B, as printed), and the story missions' rewards. Every
// change is saved to staging/mission-entries/entries.json on the server; ia missions writes them into the data repo.

import {fill, h, request} from './dom.js';

const $ = sel => document.querySelector(sel);
const sidebar = $('#sidebar');
const main = $('#main');

const FILTERS = [['all', 'All'], ['todo', 'To do'], ['done', 'Done']];

let panel = null;     // GET /api/missions
let view = 'scenarios';
let current = null;   // story mission id
let filter = 'all';

const image = path => `/data-images/small/${path}`;
const scenarioOf = card => panel.scenarios[card.id] || card.scenario;
const entryOf = id => panel.entries[id] || {rows: [], done: false, note: ''};
const rewardKey = row => (row.credits ? 'credits' : `${row.content_type}:${row.content_id}`);
const label = reward => `${reward.name} — ${reward.detail}`;

function filters(rerender) {
  return h('div', {class: 'filters'}, FILTERS.map(([value, text]) => h('button', {type: 'button',
    'aria-pressed': String(filter === value), onclick: () => { filter = value; rerender(); }}, text)));
}

const shown = done => filter === 'all' || (filter === 'done') === done;

function progress() {
  const scenarios = panel.skirmish.filter(scenarioOf).length;
  const done = panel.story.filter(m => panel.entries[m.id]?.done).length;
  $('#progress').textContent = `${scenarios} of ${panel.skirmish.length} scenarios · ${done} of ${panel.story.length} story missions done`;
  for (const tab of ['scenarios', 'rewards']) $(`#tab-${tab}`).setAttribute('aria-current', String(view === tab));
}

// Skirmish scenarios: the cards grouped by map, each with A/B buttons.

function byMap() {
  const groups = new Map();
  for (const card of panel.skirmish) {
    if (!groups.has(card.map)) groups.set(card.map, []);
    groups.get(card.map).push(card);
  }
  return [...groups];
}

const slug = text => `map-${String(text).toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;

async function setScenario(card, value) {
  panel.scenarios[card.id] = value;
  await request('PUT', `/api/missions/scenarios/${encodeURIComponent(card.id)}`, value);
  renderScenarios();
}

function renderScenarios() {
  const groups = byMap().filter(([, cards]) => shown(cards.every(scenarioOf)));
  fill(sidebar, filters(renderScenarios),
    groups.map(([map, cards]) => h('a', {href: '#scenarios', onclick: e => {
      e.preventDefault();
      document.getElementById(slug(map))?.scrollIntoView({behavior: 'smooth'});
    }}, h('span', {class: 'name'}, map),
    h('span', {class: `chip${cards.every(scenarioOf) ? ' new' : ''}`}, cards.map(c => scenarioOf(c) || '·').join(' ')))));
  const scroll = window.scrollY;
  fill(main,
    h('h1', {}, 'Skirmish scenarios'),
    h('p', {class: 'meta'}, 'The letter printed on each card. A map’s cards are usually one A and one B.'),
    groups.map(([map, cards]) => {
      const letters = cards.map(scenarioOf).filter(Boolean);
      const repeated = letters.length !== new Set(letters).size;
      return h('section', {class: 'scenario-map', id: slug(map)},
        h('h2', {}, map, repeated ? h('span', {class: 'chip skip'}, ' same letter twice') : null),
        h('div', {class: 'scenario-grid'}, cards.map(card => h('div', {class: 'scenario-card'},
          h('img', {src: image(card.image), alt: card.name, loading: 'lazy'}),
          h('div', {}, h('strong', {}, card.name), h('span', {class: 'muted'}, ` ${card.products.join(', ')}`)),
          h('div', {class: 'bar'}, ['A', 'B'].map(value => h('button', {type: 'button',
            'aria-pressed': String(scenarioOf(card) === value), onclick: () => setScenario(card,
              scenarioOf(card) === value ? null : value)}, value))),
        ))));
    }),
  );
  window.scrollTo(0, scroll);
  progress();
}

// Story rewards: one mission at a time.

function renderRewardsSidebar() {
  const chip = mission => {
    const entry = panel.entries[mission.id];
    if (panel.problems[mission.id]?.length) return h('span', {class: 'chip skip'}, 'problems');
    if (entry?.done) return h('span', {class: 'chip new'}, entry.rows.length ? `done · ${entry.rows.length}` : 'done · none');
    if (entry?.rows.length) return h('span', {class: 'chip'}, `${entry.rows.length} rows`);
    return h('span', {class: 'chip'}, mission.rows ? `${mission.rows} in data` : '—');
  };
  fill(sidebar, filters(renderRewardsSidebar),
    panel.story.filter(m => shown(!!panel.entries[m.id]?.done)).map(m => h('a', {href: `#rewards/${m.id}`,
      'aria-current': current === m.id ? 'true' : null}, h('span', {class: 'name'}, m.name), chip(m))));
  progress();
}

async function save(id, entry) {
  panel.entries[id] = entry;
  const result = await request('PUT', `/api/missions/rewards/${encodeURIComponent(id)}`, entry);
  panel.problems[id] = result.problems;
  renderRewardsSidebar();
  if (current === id) renderMission(id);
}

function rewardsPanel(id) {
  const entry = entryOf(id);
  const change = f => { const next = structuredClone(entry); f(next); save(id, next); };
  const rows = entry.rows.map((row, i) => {
    const reward = row.credits ? null : panel.rewards[rewardKey(row)];
    return h('div', {class: 'tile-row'},
      reward ? h('img', {src: image(reward.image), alt: '', loading: 'lazy'}) : h('span', {class: 'credits'}, '¢'),
      h('span', {class: 'name'}, row.credits ? 'Credits' : reward ? reward.name : `Unknown ${rewardKey(row)}`,
        reward ? h('span', {class: 'muted'}, ` ${reward.detail}`) : null),
      h('label', {}, h('input', {type: 'checkbox', checked: !!row.choice,
        onchange: e => change(n => { n.rows[i].choice = e.target.checked; })}), ' choice'),
      h('button', {type: 'button', 'aria-label': 'Remove', onclick: () => change(n => { n.rows.splice(i, 1); })}, '✕'),
    );
  });
  const byLabel = new Map(Object.values(panel.rewards).map(r => [label(r), r]));
  const report = h('span', {class: 'muted'});
  const input = h('input', {type: 'text', list: 'reward-options', placeholder: 'Find a reward or deployment card',
    'aria-label': 'Add a card', onchange: e => {
      const reward = byLabel.get(e.target.value);
      if (!reward) { report.textContent = 'Pick a card from the list'; return; }
      change(n => { n.rows.push({content_type: reward.content_type, content_id: reward.id, credits: false, choice: false}); });
    }});
  const problems = panel.problems[id] || [];
  return h('div', {class: 'panel'},
    h('h2', {}, `Rewards (${entry.rows.length})`),
    rows.length ? rows : h('p', {class: 'muted'}, 'None yet. A mission that gives no card or credits is marked done with none.'),
    h('div', {class: 'bar'}, input,
      h('button', {type: 'button', disabled: entry.rows.some(r => r.credits),
        onclick: () => change(n => { n.rows.push({content_type: null, content_id: null, credits: true, choice: false}); })},
      'Add credits'), report),
    h('p', {class: 'help muted'}, 'Rows marked choice are alternatives: the winner picks one of them. The others are all received.'),
    h('div', {class: 'bar'},
      h('label', {}, h('input', {type: 'checkbox', checked: !!entry.done, onchange: e => change(n => { n.done = e.target.checked; })}), ' Done'),
      h('input', {type: 'text', value: entry.note || '', placeholder: 'Note (not imported)', 'aria-label': 'Note',
        onchange: e => change(n => { n.note = e.target.value; })}),
    ),
    problems.length ? h('ul', {class: 'problems'}, problems.map(p => h('li', {}, p))) : null,
  );
}

function renderMission(id) {
  const mission = panel.story.find(m => m.id === id);
  if (!mission) return fill(main, h('p', {class: 'muted'}, 'Pick a story mission on the left.'));
  const focused = document.activeElement?.getAttribute('aria-label');
  fill(main,
    h('h1', {}, mission.name),
    h('p', {class: 'meta'}, mission.products.join(', '),
      mission.rows ? ` — ${mission.rows} rows in the data now, replaced when written` : ''),
    h('div', {class: 'layout-editor'},
      h('figure', {class: 'map-image'}, h('img', {src: image(mission.image), alt: mission.name})),
      rewardsPanel(id),
    ),
    h('datalist', {id: 'reward-options'}, Object.values(panel.rewards).map(r => h('option', {value: label(r)}))),
  );
  if (focused) main.querySelector(`[aria-label="${focused}"]`)?.focus();
}

// Routing: #scenarios, #rewards/<mission id>

function route() {
  const [name, id] = location.hash.slice(1).split('/');
  view = name === 'rewards' ? 'rewards' : 'scenarios';
  if (view === 'scenarios') return renderScenarios();
  current = id || panel.story[0]?.id;
  renderRewardsSidebar();
  renderMission(current);
}

async function start() {
  panel = await request('GET', '/api/missions');
  window.addEventListener('hashchange', route);
  route();
}

start().catch(error => {
  console.error(error);
  fill(main, h('p', {class: 'problems'}, String(error)));
});
