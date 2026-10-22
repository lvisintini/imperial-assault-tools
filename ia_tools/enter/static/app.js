// IA data entry: go through a staged product card by card. Every decision is saved to the product's entries.json on
// the server; ia import turns those into dataset records.

const $ = sel => document.querySelector(sel);
const sidebar = $('#sidebar');
const main = $('#main');

const ACTIONS = [
  ['new', 'New record'],
  ['link', 'Same as an existing record'],
  ['attach', 'Extra image for another card'],
  ['skip', 'Skip for now'],
  ['known-skip', 'Never import'],
];

let products = [];

// Ids are numbers in 1.x data and UUID strings from 2.0.0; <select> values are always strings.
const idValue = v => /^\d+$/.test(v) ? Number(v) : v;
let data = null;      // GET /api/products/<slug>
let current = null;   // item key, or 'product' / 'extras' / 'check'
let filter = 'all';

// DOM helper: h('div', {class: 'x', onclick: fn}, child, ...)
function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'class') el.className = v;
    else if (v === true) el.setAttribute(k, '');
    else el.setAttribute(k, v);
  }
  for (const child of children.flat(Infinity)) {
    if (child == null || child === false) continue;
    el.append(child instanceof Node ? child : String(child));
  }
  return el;
}

// Replace an element's children: arrays are flattened and null/false dropped, like h().
function fill(el, ...children) {
  el.replaceChildren(...children.flat(Infinity).filter(c => c != null && c !== false)
    .map(c => (c instanceof Node ? c : String(c))));
  return el;
}

const clone = value => (value === undefined ? undefined : JSON.parse(JSON.stringify(value)));

async function request(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: body === undefined ? {} : {'Content-Type': 'application/json'},
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${method} ${url}: HTTP ${res.status}`);
  return res.json();
}

// Data helpers

const items = () => data.manifest.items;
const productName = () => data.manifest.product ?? 'Several products';  // a folder of gaps has no product of its own
const proposals = () => data.manifest.edits || [];  // changes to existing records (ia propose)
const itemByKey = key => items().find(i => i.key === key);
const entryOf = key => data.entries.items[key];
const typeOf = key => (entryOf(key) || data.suggestions[key] || {}).content_type || itemByKey(key).guess.content_type;

function stagedRecords(parentType) {
  // New records of a type staged in this product, for foreign-key pickers: [{value: '@key', label}]
  const out = [];
  for (const [key, entry] of Object.entries(data.entries.items)) {
    if (entry.action === 'new' && entry.content_type === parentType) {
      out.push({value: `@${key}`, label: `${entry.record?.name || key} (staged)`});
    }
  }
  for (const [key, extra] of Object.entries(data.entries.extra || {})) {
    if (extra.content_type === parentType) out.push({value: `@${key}`, label: `${extra.record?.name || key} (staged)`});
  }
  return out;
}

// Form built from the server's field specs (derived from the data repo's schemas). Mutates record in place.

function buildForm(contentType, record) {
  const form = data.forms[contentType];
  if (!form) return h('p', {class: 'muted'}, 'Choose a content type.');
  const grid = h('div', {class: 'form'});
  for (const field of form.fields) {
    const id = `f-${field.name}`;
    grid.append(h('label', {for: id}, field.name.replaceAll('_', ' '), field.required ? h('span', {class: 'req'}, ' *') : ''));
    grid.append(fieldInput(field, id, record));
    if (field.description) grid.append(h('div', {class: 'help'}, field.description));
  }
  return grid;
}

function fieldInput(field, id, record) {
  // Blank nullable fields are null, so required-but-nullable fields (e.g. reinforce_cost) validate.
  if (record[field.name] === undefined && field.nullable && field.kind !== 'multi' && field.kind !== 'list') {
    record[field.name] = null;
  }
  const value = record[field.name];
  // Nullable arrays need at least one item (e.g. traits), so an empty one is null.
  const set = v => { record[field.name] = Array.isArray(v) && !v.length && field.nullable ? null : v; };
  let input;
  switch (field.kind) {
    case 'boolean':
      if (value === undefined) set(false);
      input = h('input', {type: 'checkbox', id, checked: !!value, onchange: e => set(e.target.checked)});
      break;
    case 'integer':
      input = h('input', {type: 'number', id, min: field.minimum, value: value ?? '',
        oninput: e => set(e.target.value === '' ? (field.nullable ? null : undefined) : Number(e.target.value))});
      break;
    case 'select': {
      input = h('select', {id, onchange: e => set(e.target.value === '' ? (field.nullable ? null : undefined) : e.target.value)},
        h('option', {value: ''}, field.nullable ? '— none —' : '— choose —'),
        field.options.map(o => h('option', {value: o, selected: o === value}, o)));
      break;
    }
    case 'multi': {
      if (!Array.isArray(value)) set([]);
      input = h('div', {class: 'multi', id}, field.options.map(o => h('label', {},
        h('input', {type: 'checkbox', checked: (record[field.name] || []).includes(o), onchange: e => {
          const list = (record[field.name] || []).filter(x => x !== o);
          if (e.target.checked) list.push(o);
          set(field.options.filter(x => list.includes(x)));
        }}), ' ', o)));
      break;
    }
    case 'list':
      input = h('input', {type: 'text', id, value: (value || []).join(', '), placeholder: 'comma-separated',
        oninput: e => set(e.target.value.split(',').map(s => s.trim()).filter(Boolean))});
      break;
    case 'fk': {
      const options = [
        ...(data.records[field.parent] || []).map(r => ({value: String(r.id), label: r.name})),
        ...stagedRecords(field.parent),
      ];
      input = h('select', {id, onchange: e => {
        const v = e.target.value;
        set(v === '' ? undefined : v.startsWith('@') ? v : idValue(v));
      }}, h('option', {value: ''}, '— choose —'),
      options.map(o => h('option', {value: o.value, selected: String(value) === o.value}, o.label)));
      break;
    }
    default:
      input = h('input', {type: 'text', id, value: value ?? '', oninput: e => set(e.target.value === '' && field.nullable ? null : e.target.value)});
  }
  return input;
}

// Sidebar

const FILTERS = [['all', 'All'], ['undecided', 'Undecided'], ['new', 'New'], ['link', 'Linked'], ['skip', 'Skipped']];

function visible(item) {
  const entry = entryOf(item.key);
  if (filter === 'all') return true;
  if (filter === 'undecided') return !entry;
  if (filter === 'skip') return entry && (entry.action === 'skip' || entry.action === 'known-skip');
  if (filter === 'new') return entry && (entry.action === 'new' || entry.action === 'attach');
  return entry && entry.action === filter;
}

function renderSidebar() {
  const groups = new Map();
  for (const item of items().filter(visible)) {
    const type = typeOf(item.key) || 'unclassified';
    if (!groups.has(type)) groups.set(type, []);
    groups.get(type).push(item);
  }
  const link = (key, label, chip) => h('a', {href: `#${data.slug}/${key}`, 'aria-current': current === key ? 'true' : null},
    h('span', {class: 'name'}, label), chip);
  fill(sidebar, 
    h('div', {class: 'filters'}, FILTERS.map(([value, label]) => h('button', {type: 'button',
      'aria-pressed': String(filter === value), onclick: () => { filter = value; renderSidebar(); }}, label))),
    h('h3', {}, 'Product'),
    link('product', data.entries.product ? `${productName()} ✓` : productName()),
    link('extras', `Records without an image (${Object.keys(data.entries.extra || {}).length})`),
    proposals().length ? link('edits', `Edits to existing records (${proposals().filter(e => data.entries.edits?.[e.key]).length}/${proposals().length})`) : null,
    [...groups].map(([type, list]) => [
      h('h3', {}, `${type} (${list.length})`),
      list.map(item => {
        const entry = entryOf(item.key);
        return link(item.key, item.name || item.key, h('span', {class: `chip ${entry?.action || ''}`}, entry?.action || '—'));
      }),
    ]),
  );
  const decided = items().filter(i => entryOf(i.key)).length + proposals().filter(e => data.entries.edits?.[e.key]).length;
  const total = items().length + proposals().length;
  $('#progress').textContent = `${decided} of ${total} decided`;
  const option = [...$('#product-select').options].find(o => o.value === data.slug);
  if (option) option.textContent = `${data.manifest.product ?? data.slug} (${decided}/${total})`;
}

// Views

function show(key) {
  current = key;
  renderSidebar();
  if (key === 'product') return renderProduct();
  if (key === 'extras') return renderExtras();
  if (key === 'edits') return renderEdits();
  if (key === 'check') return renderCheck();
  if (itemByKey(key)) return renderItem(key);
  fill(main, h('p', {class: 'muted'}, 'Pick an image on the left.'));
}

function imageFigures(item, draft) {
  const type = draft.content_type;
  const back = type === 'card-backs' ? draft.record?.content_type ?? item.guess.back_content_type : null;
  const sized = type && (type !== 'card-backs' || back);
  const refKey = type === 'card-backs' ? `card-backs:${back}` : type;
  const ref = data.references[refKey];
  return h('div', {class: 'images'},
    h('figure', {}, h('img', {src: `/originals/${data.slug}/${item.file}`, alt: ''}),
      h('figcaption', {}, `Original · ${item.width}×${item.height} ${item.format}`)),
    sized && h('figure', {}, h('img', {src: `/preview/${data.slug}/${item.key}?type=${encodeURIComponent(type)}&back=${encodeURIComponent(back || '')}`, alt: ''}),
      h('figcaption', {}, `As it will be imported (${type})`)),
    ref && h('figure', {}, h('img', {src: `/data-images/large/${ref}`, alt: ''}),
      h('figcaption', {}, `Existing ${refKey} for comparison`)),
  );
}

function productField(draft) {
  // The image's own product, when it isn't the folder's, and (data 2.0.0) how many copies of the card it has.
  return h('div', {class: 'form'}, h('label', {for: 'source_id'}, 'product'),
    h('select', {id: 'source_id', onchange: e => {
      if (e.target.value) draft.source_id = idValue(e.target.value); else delete draft.source_id;
    }},
      h('option', {value: ''}, data.manifest.product ? `this folder's (${data.manifest.product})` : '— choose —'),
      data.records.sources.map(s => h('option', {value: s.id, selected: s.id === draft.source_id}, `${s.name} (#${s.id})`))),
    copiesField(draft));
}

function copiesField(draft) {
  // Data 2.0.0: how many of it the product has (source-contents.quantity); unset is 1.
  return data.quantities && [h('label', {}, 'copies'),
    h('input', {type: 'number', min: 1, value: draft.quantity ?? 1, onchange: e => {
      const n = Number(e.target.value);
      if (Number.isInteger(n) && n > 1) draft.quantity = n; else delete draft.quantity;
    }})];
}

function renderItem(key) {
  const item = itemByKey(key);
  const draft = clone(entryOf(key) || data.suggestions[key] || {action: 'new', record: {}});
  draft.record ??= {};
  const status = h('div');

  const imagesSlot = h('div');
  const body = h('div');
  const refreshImages = () => fill(imagesSlot, imageFigures(item, draft));

  function renderBody() {
    const parts = [];
    if (draft.action === 'new') {
      parts.push(h('div', {class: 'form'},
        h('label', {for: 'type'}, 'content type'),
        h('select', {id: 'type', onchange: e => { draft.content_type = e.target.value; draft.record = {}; renderBody(); refreshImages(); }},
          h('option', {value: ''}, '— choose —'),
          data.entry_types.map(t => h('option', {value: t, selected: t === draft.content_type}, t)))));
      const imageFields = data.forms[draft.content_type]?.images || [];
      if (imageFields.length > 1) {
        draft.field ??= imageFields[0];
        parts.push(h('div', {class: 'form'}, h('label', {for: 'field'}, 'this image is'),
          h('select', {id: 'field', onchange: e => { draft.field = e.target.value; }},
            imageFields.map(f => h('option', {value: f, selected: f === draft.field}, f)))));
      }
      parts.push(h('div', {class: 'form'}, h('label', {for: 'file'}, 'file name'),
        h('input', {type: 'text', id: 'file', value: draft.file || '', placeholder: 'automatic, from the name',
          oninput: e => { draft.file = e.target.value.trim() || undefined; }}),
        h('div', {class: 'help'}, 'Only needed when the automatic name would be wrong (e.g. form cards).')));
      parts.push(productField(draft), h('hr'), buildForm(draft.content_type, draft.record));
    } else if (draft.action === 'link') {
      draft.content_type ??= item.guess.content_type;
      const records = data.records[draft.content_type] || [];
      parts.push(h('div', {class: 'form'},
        h('label', {for: 'type'}, 'content type'),
        h('select', {id: 'type', onchange: e => { draft.content_type = e.target.value; delete draft.id; renderBody(); }},
          Object.keys(data.records).map(t => h('option', {value: t, selected: t === draft.content_type}, t))),
        h('label', {for: 'record'}, 'record'),
        h('select', {id: 'record', onchange: e => { draft.id = idValue(e.target.value); }},
          h('option', {value: ''}, '— choose —'),
          records.map(r => h('option', {value: r.id, selected: r.id === draft.id}, `${r.name} (#${r.id})`)))),
        productField(draft),
        h('p', {class: 'muted'}, 'Adds a source-contents row linking the product to the record. Nothing else changes.'));
    } else if (draft.action === 'attach') {
      const targets = Object.entries(data.entries.items).filter(([k, e]) => e.action === 'new' && k !== key);
      const targetType = data.entries.items[draft.to]?.content_type;
      parts.push(h('div', {class: 'form'},
        h('label', {for: 'to'}, 'card'),
        h('select', {id: 'to', onchange: e => { draft.to = e.target.value; renderBody(); }},
          h('option', {value: ''}, '— choose —'),
          targets.map(([k, e]) => h('option', {value: k, selected: k === draft.to}, `${e.record?.name || k} (${e.content_type})`))),
        h('label', {for: 'field'}, 'as field'),
        h('select', {id: 'field', onchange: e => { draft.field = e.target.value; }},
          (data.forms[targetType]?.images || []).map(f => h('option', {value: f, selected: f === draft.field}, f)))));
    } else {
      parts.push(h('p', {class: 'muted'}, draft.action === 'known-skip'
        ? 'Never imported. Its hash goes into known-skipped-sha512.txt, so audits stop flagging it.'
        : 'Left out of this import. You can come back to it later.'));
    }
    fill(body, ...parts);
  }

  async function save(next) {
    const entry = clone(draft);
    if (entry.action !== 'new') delete entry.record;
    const result = await request('PUT', `/api/products/${data.slug}/items/${key}`, entry);
    data.entries.items[key] = entry;
    renderSidebar();
    fill(status, result.problems.length
      ? h('ul', {class: 'problems'}, result.problems.map(p => h('li', {}, p)))
      : h('span', {class: 'ok'}, 'Saved.'));
    if (next && !result.problems.length) {
      const order = [...sidebar.querySelectorAll('a')].map(a => a.getAttribute('href').split('/')[1]);
      const after = order.slice(order.indexOf(key) + 1).find(k => itemByKey(k) && !entryOf(k));
      if (after) location.hash = `${data.slug}/${after}`;
    }
  }

  // A card back's preview size depends on the content type it's the back of.
  body.addEventListener('change', e => { if (e.target.id === 'f-content_type') refreshImages(); });
  renderBody();
  refreshImages();
  fill(main, 
    h('h1', {}, item.name || item.key),
    h('p', {class: 'meta'}, item.path.join(' / '), ' · ', `${Math.round(item.bytes / 1024)} kB`, ' · ',
      h('a', {href: item.url, target: '_blank', rel: 'noopener'}, 'on boardwars')),
    item.matches.length ? h('p', {class: 'meta'}, 'Name matches: ',
      item.matches.map(m => `${m.content_type} #${m.id} ${m.name}`).join('; ')) : null,
    imagesSlot,
    h('div', {class: 'panel'},
      h('div', {class: 'actions'}, ACTIONS.map(([value, label]) => h('label', {},
        h('input', {type: 'radio', name: 'action', value, checked: draft.action === value,
          onchange: () => { draft.action = value; renderBody(); }}), label))),
      body,
      h('div', {class: 'bar'},
        h('button', {type: 'button', onclick: () => save(false)}, 'Save'),
        h('button', {type: 'button', class: 'primary', onclick: () => save(true)}, 'Save & next undecided'),
        h('span', {class: 'muted'}, 'Ctrl+Enter')),
      status),
  );
  main.onkeydown = e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); save(true); } };
}

function renderProduct() {
  if (!data.manifest.product) {
    fill(main, h('h1', {}, items().length ? productName() : data.slug),
      h('p', {class: 'meta'}, items().length
        ? 'These images come from different products: each image\'s page has its own product field.'
        : 'This folder only changes existing records: see Edits to existing records.'));
    return;
  }
  const existing = data.manifest.existing_product[0];
  const draft = clone(data.entries.product) || (existing
    ? {action: 'existing', id: existing.id}
    : {action: 'new', record: {name: data.manifest.product}, item: items().find(i => i.guess.content_type === 'sources')?.key});
  draft.record ??= {name: data.manifest.product};
  const body = h('div');
  const status = h('div');

  function renderBody() {
    if (draft.action === 'existing') {
      fill(body, h('div', {class: 'form'}, h('label', {for: 'source'}, 'product'),
        h('select', {id: 'source', onchange: e => { draft.id = idValue(e.target.value); }},
          data.records.sources.map(s => h('option', {value: s.id, selected: s.id === draft.id}, `${s.name} (#${s.id})`)))));
    } else {
      fill(body, 
        h('div', {class: 'form'}, h('label', {for: 'item'}, 'product image'),
          h('select', {id: 'item', onchange: e => { draft.item = e.target.value || undefined; renderPreview(); }},
            h('option', {value: ''}, '— choose —'),
            items().map(i => h('option', {value: i.key, selected: i.key === draft.item}, `${i.key} ${i.name}`)))),
        preview,
        h('hr'),
        buildForm('sources', draft.record));
      renderPreview();
    }
  }
  const preview = h('div');
  function renderPreview() {
    const item = draft.item && itemByKey(draft.item);
    fill(preview, item ? imageFigures(item, {content_type: 'sources'}) : '');
  }

  renderBody();
  fill(main, 
    h('h1', {}, data.manifest.product),
    h('p', {class: 'meta'}, existing ? `Already in the dataset as #${existing.id} ${existing.name}.` : 'Not in the dataset yet.'),
    h('div', {class: 'panel'},
      h('div', {class: 'actions'}, [['new', 'New product'], ['existing', 'Existing product']].map(([value, label]) =>
        h('label', {}, h('input', {type: 'radio', name: 'paction', checked: draft.action === value,
          onchange: () => { draft.action = value; renderBody(); }}), label))),
      body,
      h('div', {class: 'bar'}, h('button', {type: 'button', class: 'primary', onclick: async () => {
        const entry = draft.action === 'existing' ? {action: 'existing', id: draft.id} : {action: 'new', record: draft.record, item: draft.item};
        const result = await request('PUT', `/api/products/${data.slug}/product`,
          draft.action === 'new' ? {...entry, content_type: 'sources'} : entry);
        data.entries.product = entry;
        renderSidebar();
        fill(status, result.problems.length
          ? h('ul', {class: 'problems'}, result.problems.map(p => h('li', {}, p))) : h('span', {class: 'ok'}, 'Saved.'));
      }}, 'Save')),
      status));
}

function renderExtras() {
  const extras = data.entries.extra ||= {};
  const list = h('div');
  function renderList() {
    fill(list, ...Object.entries(extras).map(([key, extra]) => {
      const draft = clone(extra);
      const status = h('div');
      return h('div', {class: 'panel'},
        h('h2', {}, `${extra.content_type} · ${key}`),
        h('div', {class: 'form'}, copiesField(draft)),
        buildForm(draft.content_type, draft.record),
        h('div', {class: 'bar'},
          h('button', {type: 'button', class: 'primary', onclick: async () => {
            const result = await request('PUT', `/api/products/${data.slug}/extra/${key}`, {...draft, action: 'new'});
            extras[key] = draft;
            fill(status, result.problems.length
              ? h('ul', {class: 'problems'}, result.problems.map(p => h('li', {}, p))) : h('span', {class: 'ok'}, 'Saved.'));
          }}, 'Save'),
          h('button', {type: 'button', onclick: async () => {
            await request('DELETE', `/api/products/${data.slug}/extra/${key}`);
            delete extras[key];
            renderList();
            renderSidebar();
          }}, 'Delete')),
        status);
    }));
  }
  const typeSelect = h('select', {}, data.extra_types.map(t => h('option', {value: t}, t)));
  renderList();
  fill(main, 
    h('h1', {}, 'Records without an image'),
    h('p', {class: 'meta'}, 'Agenda decks and imperial classes have no image of their own; their cards point at them.'),
    h('div', {class: 'bar'}, typeSelect, h('button', {type: 'button', onclick: async () => {
      let n = 1;
      while (extras[`x${n}`]) n += 1;
      const key = `x${n}`;
      extras[key] = {content_type: typeSelect.value, record: {}};
      await request('PUT', `/api/products/${data.slug}/extra/${key}`, extras[key]);
      renderList();
      renderSidebar();
    }}, 'Add')),
    list);
}

function renderEdits() {
  fill(main,
    h('h1', {}, 'Edits to existing records'),
    h('p', {class: 'meta'}, 'Proposed with ia propose. Change the values if you want, then apply or skip each one. ',
      'ia import writes the applied ones.'),
    proposals().map(editPanel));
}

function editPanel(proposal) {
  const decisions = data.entries.edits ||= {};
  const record = data.edit_records[proposal.key];
  const draft = clone(decisions[proposal.key]) || {action: 'apply', changes: clone(proposal.changes), rename_images: true};
  draft.changes ??= clone(proposal.changes);
  const result = h('div');
  const body = h('div');

  function showResult(answer, saved) {
    const moves = Object.entries(answer.images || {});
    fill(result,
      answer.problems.length ? h('ul', {class: 'problems'}, answer.problems.map(p => h('li', {}, p))) : null,
      draft.action === 'apply' ? h('p', {class: 'muted'}, moves.length
        ? moves.map(([field, [from, to]]) => `${field}: ${from} → ${to}`).join('; ')
        : 'Image files keep their names.') : null,
      saved ? h('span', {class: 'ok'}, 'Saved.') : null);
  }
  let timer;
  const refresh = () => {
    clearTimeout(timer);
    timer = setTimeout(async () => showResult(
      await request('POST', `/api/products/${data.slug}/edits/${proposal.key}/preview`, draft), false), 250);
  };

  function renderBody() {
    fill(body,
      draft.action === 'apply' ? [
        Object.keys(proposal.changes).map(field => {
          const id = `edit-${proposal.key}-${field}`;
          const text = typeof proposal.changes[field] === 'string';
          return h('div', {class: 'form'},
            h('label', {for: id}, field),
            h('input', {type: 'text', id, value: text ? draft.changes[field] : JSON.stringify(draft.changes[field]),
              oninput: e => {
                try { draft.changes[field] = text ? e.target.value.trim() : JSON.parse(e.target.value); } catch { return; }
                refresh();
              }}),
            h('div', {class: 'help'}, `Now: ${JSON.stringify(record?.[field])}`));
        }),
        h('label', {}, h('input', {type: 'checkbox', checked: draft.rename_images,
          onchange: e => { draft.rename_images = e.target.checked; refresh(); }}),
          ' Rename the image files to match'),
      ] : h('p', {class: 'muted'}, 'Left as it is.'));
  }

  renderBody();
  refresh();
  return h('div', {class: 'panel'},
    h('h2', {}, `${proposal.content_type} #${proposal.id} · ${record?.name ?? 'missing record'}`),
    proposal.note ? h('p', {class: 'meta'}, proposal.note) : null,
    record?.image ? h('div', {class: 'images'}, h('figure', {},
      h('img', {src: `/data-images/large/${record.image}`, alt: ''}), h('figcaption', {}, record.image))) : null,
    h('div', {class: 'actions'}, [['apply', 'Apply'], ['skip', 'Skip']].map(([value, label]) => h('label', {},
      h('input', {type: 'radio', name: `eaction-${proposal.key}`, checked: draft.action === value,
        onchange: () => { draft.action = value; renderBody(); refresh(); }}), label))),
    body,
    h('div', {class: 'bar'}, h('button', {type: 'button', class: 'primary', onclick: async () => {
      const entry = draft.action === 'apply' ? clone(draft) : {action: 'skip'};
      const answer = await request('PUT', `/api/products/${data.slug}/edits/${proposal.key}`, entry);
      decisions[proposal.key] = entry;
      renderSidebar();
      showResult(answer, true);
    }}, 'Save')),
    result);
}

async function renderCheck() {
  fill(main, h('h1', {}, 'Check import'), h('p', {class: 'muted'}, 'Checking…'));
  const result = await request('POST', `/api/products/${data.slug}/check`);
  fill(main, 
    h('h1', {}, 'Check import'),
    result.ok
      ? [h('p', {class: 'ok'}, 'Ready to import. Ask Claude to run ia import ', data.slug, '.'),
        h('pre', {}, JSON.stringify(result.summary, null, 2)),
        h('details', {}, h('summary', {}, 'Records'), h('pre', {}, JSON.stringify(result.records, null, 2)))]
      : [h('p', {}, `${result.problems.length} problems:`), h('ul', {class: 'problems'}, result.problems.map(p => h('li', {}, p)))],
  );
}

// Routing: #<slug>/<key>

async function route() {
  const [slug, key] = location.hash.slice(1).split('/');
  const target = slug || products[0]?.slug;
  if (!target) {
    fill(main, h('p', {}, 'Nothing staged yet. Run ia scrape <album url> first.'));
    return;
  }
  if (!data || data.slug !== target) {
    data = await request('GET', `/api/products/${encodeURIComponent(target)}`);
    $('#product-select').value = target;
  }
  show(key || (!items().length && proposals().length ? 'edits' : 'product'));
}

async function start() {
  products = await request('GET', '/api/products');
  fill($('#product-select'), ...products.map(p => h('option', {value: p.slug}, `${p.product ?? p.slug} (${p.decided}/${p.items})`)));
  $('#product-select').onchange = e => { location.hash = e.target.value; };
  $('#check').onclick = () => { location.hash = `${data.slug}/check`; };
  window.addEventListener('hashchange', route);
  await route();
}

start().catch(error => {
  console.error(error);
  fill(main, h('p', {class: 'problems'}, String(error)));
});
