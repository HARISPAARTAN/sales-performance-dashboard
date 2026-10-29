// The replica's page code: state, filters, tabs, tiles, tables and charts. All numbers come from model.js
// (pure, tested against the Python reference) and are formatted with the kit's fmt helpers.
import { createStore, fmt, initTabs, mountBanner, mountThemeToggle, renderKpi, renderTable } from '../../kit/kit.js';
import { registerThemes } from '../../kit/echarts-theme.js';
import * as charts from './charts.js';
import { ANALYSE, CROSS_DIMS, MONTH_NAMES, TABS, YEARS, createModel, defaultState, monthLabel, normaliseState, summary } from './model.js';

const REPO = 'https://github.com/HARISPAARTAN/sales-performance-dashboard';
const store = createStore('sales-performance-dashboard');
const $ = (id) => document.getElementById(id);
const motionQuery = typeof matchMedia === 'function' ? matchMedia('(prefers-reduced-motion: reduce)') : null;
const motion = () => !(motionQuery && motionQuery.matches);
const PP = new Set(['margin', 'discount']);
const NOTES = {
  customers: 'The category filter does not apply on this tab: customers are listed with all their sales.',
  targets: 'Targets are set per region and month; the category filter does not apply here.',
};

let model;
let state;
let host;
const tables = {};

// ---------------------------------------------------------------- formatting

const eurM = (cents) => (cents === null || cents === undefined ? fmt.dec(null) : `€ ${fmt.dec(cents / 1e8, 2)} m`);
const money = charts.moneyText;
const signedPct = (x) => `${x > 0 ? '+' : ''}${fmt.pct(x)}`;

function colours() {
  const css = getComputedStyle(document.documentElement);
  const token = (name) => css.getPropertyValue(`--${name}`).trim();
  return {
    text: token('text'),
    muted: token('muted'),
    border: token('border'),
    surface: token('surface'),
    accent: token('accent'),
    ok: token('ok'),
    warn: token('warn'),
    chart: [1, 2, 3, 4, 5, 6, 7, 8].map((n) => token(`chart-${n}`)),
  };
}

// A tile of model.js ({value, py, delta, note}) as kit KPI data; percentages compare in pp, the rest in %.
function tileData(label, tile, show, { key = '', caption = '' } = {}) {
  if (tile.delta === null || tile.delta === undefined) {
    return { label, value: show(tile.value), delta: { kind: 'neutral', text: 'n/a vs PY' }, caption: tile.note ?? caption };
  }
  const pp = PP.has(key);
  const text = pp ? `${fmt.pp(tile.delta / 100)} vs PY` : `${signedPct(tile.delta)} vs PY`;
  let kind = tile.delta > 0 ? 'up' : tile.delta < 0 ? 'down' : 'neutral';
  if (key === 'discount') kind = 'neutral'; // a higher discount is not good news: no green or red
  return { label, value: show(tile.value), delta: { kind, text }, caption };
}

function tiles(el, list) {
  el.replaceChildren(...list.map((data) => {
    const box = document.createElement('div');
    renderKpi(box, data);
    return box.firstElementChild;
  }));
}

// ---------------------------------------------------------------- state

function save() {
  const { tab, years, monthFrom, monthTo, regions, categories, analyseBy } = state;
  store.save({ tab, years, monthFrom, monthTo, regions, categories, analyseBy });
}

function update(changes) {
  state = normaliseState({ ...state, ...changes }, model.data);
  if ('cross' in changes) state.cross = changes.cross;
  if ('drill' in changes) state.drill = changes.drill;
  save();
  render();
}

function tabFromHash() {
  const name = location.hash.replace('#', '');
  return TABS.includes(name) ? name : null;
}

// ---------------------------------------------------------------- filter bar

function chip(year) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'pf-chip';
  button.textContent = String(year);
  button.dataset.year = String(year);
  button.addEventListener('click', () => {
    const years = state.years.includes(year) ? state.years.filter((y) => y !== year) : [...state.years, year];
    update({ years });
  });
  return button;
}

function checkboxes(list, values, key) {
  list.replaceChildren(...values.map((value) => {
    const label = document.createElement('label');
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.value = value;
    input.addEventListener('change', () => {
      const chosen = [...list.querySelectorAll('input:checked')].map((i) => i.value);
      update({ [key]: chosen });
    });
    label.append(input, document.createTextNode(value));
    return label;
  }));
}

function menuLabel(values, all, noun) {
  if (!values.length) return all;
  return values.length <= 2 ? values.join(', ') : `${values.length} ${noun}`;
}

function buildFilters() {
  $('year-chips').replaceChildren(...YEARS.map(chip));
  for (const id of ['month-from', 'month-to']) {
    $(id).replaceChildren(...MONTH_NAMES.map((name, i) => new Option(name, String(i + 1))));
  }
  $('month-from').addEventListener('change', (e) => update({ monthFrom: Number(e.target.value) }));
  $('month-to').addEventListener('change', (e) => update({ monthTo: Number(e.target.value) }));
  checkboxes($('region-list'), model.data.dims.regions, 'regions');
  checkboxes($('category-list'), model.data.dims.categories, 'categories');
  $('reset').addEventListener('click', () => {
    closeMenus();
    update({ ...defaultState(), tab: state.tab, cross: null, drill: null });
  });
  $('filters-toggle').addEventListener('click', () => {
    const open = !$('filters').classList.contains('is-open');
    $('filters').classList.toggle('is-open', open);
    $('filters-toggle').setAttribute('aria-expanded', String(open));
  });
  document.addEventListener('click', (e) => {
    for (const menu of document.querySelectorAll('details.menu[open]')) if (!menu.contains(e.target)) menu.open = false;
  });
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    closeMenus();
    hideTip();
  });
}

function closeMenus() {
  for (const menu of document.querySelectorAll('details.menu')) menu.open = false;
}

function syncFilters() {
  for (const button of $('year-chips').children) {
    button.setAttribute('aria-pressed', String(state.years.includes(Number(button.dataset.year))));
  }
  $('month-from').value = String(state.monthFrom);
  $('month-to').value = String(state.monthTo);
  for (const input of $('region-list').querySelectorAll('input')) input.checked = state.regions.includes(input.value);
  for (const input of $('category-list').querySelectorAll('input')) input.checked = state.categories.includes(input.value);
  $('region-label').textContent = menuLabel(state.regions, 'All regions', 'regions');
  $('category-label').textContent = menuLabel(state.categories, 'All categories', 'categories');
  const note = NOTES[state.tab];
  $('category-menu').hidden = Boolean(note);
  $('category-note').hidden = !note;
  $('category-note').textContent = note ?? '';
  $('filter-summary').textContent = summary(state);
  const box = $('cross-chip');
  const active = state.cross ? ['Cross-filter', `${state.cross.dim}: `, state.cross.value]
    : state.drill && state.tab === 'products' ? ['Drill', 'Drill: ', state.drill] : null;
  if (!active) {
    box.className = 'xchip xchip--idle';
    box.textContent = 'none · click a bar';
    return;
  }
  box.className = 'xchip';
  const text = document.createElement('span');
  const strong = document.createElement('b');
  strong.textContent = active[2];
  text.append(document.createTextNode(active[1]), strong);
  const clear = document.createElement('button');
  clear.type = 'button';
  clear.className = 'xchip__clear';
  clear.textContent = '×';
  clear.setAttribute('aria-label', `Clear the ${active[0].toLowerCase()} ${active[2]}`);
  clear.addEventListener('click', () => update({ cross: null, drill: null }));
  box.replaceChildren(text, clear);
}

// ---------------------------------------------------------------- tables

function table(name, el, options, sortKey, dir = 'desc') {
  if (!tables[name]) {
    tables[name] = renderTable(el, options);
    tables[name].sort(sortKey, dir);
  } else {
    tables[name].update(options.rows);
  }
  return tables[name];
}

const num = (format) => ({ align: 'right', format });

function dataBar(max) {
  return (value) => {
    const box = document.createElement('span');
    box.className = 'dbar';
    const bar = document.createElement('i');
    bar.style.width = `${max > 0 ? Math.max(0, (100 * value) / max) : 0}%`;
    const text = document.createElement('span');
    text.textContent = money(value);
    box.append(bar, text);
    return box;
  };
}

function skuButton(value) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'sku';
  button.dataset.sku = value;
  button.textContent = value;
  return button;
}

// ---------------------------------------------------------------- product tooltip

let tipRows = new Map();
let tipAnchor = null;

function sparkline(points) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 280 46');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', 'Revenue by month, sparkline');
  const values = points.map((p) => p[1] ?? 0);
  const top = Math.max(1, ...values);
  const step = values.length > 1 ? 272 / (values.length - 1) : 0;
  const line = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
  line.setAttribute('fill', 'none');
  line.setAttribute('stroke', 'var(--accent)');
  line.setAttribute('stroke-width', '2');
  line.setAttribute('points', values.map((v, i) => `${(4 + i * step).toFixed(1)},${(42 - (38 * v) / top).toFixed(1)}`).join(' '));
  svg.append(line);
  return svg;
}

function showTip(target) {
  const row = tipRows.get(target.dataset.sku);
  if (!row) return;
  const tip = $('tip');
  const title = document.createElement('h3');
  title.textContent = row.name;
  const grid = document.createElement('div');
  grid.className = 'tip__grid';
  const cells = [
    ['Revenue', money(row.revenue)],
    ['Gross margin %', fmt.pct(row.margin)],
    ['Units', fmt.int(row.units)],
    ['Rank', `${fmt.int(row.rank)} of ${fmt.int(tipRows.size)}`],
  ];
  for (const [label, value] of cells) {
    const cell = document.createElement('div');
    const name = document.createElement('span');
    name.textContent = label;
    const strong = document.createElement('b');
    strong.textContent = value;
    cell.append(name, strong);
    grid.append(cell);
  }
  const caption = document.createElement('p');
  caption.className = 'pf-kpi__caption';
  caption.textContent = 'Revenue by month in the selection';
  tip.replaceChildren(title, grid, sparkline(model.productMonths(state, row.product)), caption);
  tip.hidden = false;
  tipAnchor = target;
  placeTip();
}

// Next to the SKU, inside the viewport; it follows the SKU when the page scrolls (focus scrolls it into view).
function placeTip() {
  if (!tipAnchor) return;
  const tip = $('tip');
  const box = tipAnchor.getBoundingClientRect();
  const left = Math.min(window.innerWidth - tip.offsetWidth - 16, box.right + 12);
  const top = Math.min(window.innerHeight - tip.offsetHeight - 16, box.top - 8);
  tip.style.left = `${Math.max(16, left)}px`;
  tip.style.top = `${Math.max(16, top)}px`;
}

function hideTip() {
  tipAnchor = null;
  $('tip').hidden = true;
}

function bindTip(el) {
  const enter = (e) => {
    const target = e.target.closest?.('.sku');
    if (target) showTip(target);
  };
  const leave = (e) => {
    if (e.target.closest?.('.sku')) hideTip();
  };
  el.addEventListener('mouseover', enter);
  el.addEventListener('focusin', enter);
  el.addEventListener('mouseout', leave);
  el.addEventListener('focusout', leave);
  window.addEventListener('scroll', placeTip, { passive: true });
}

// ---------------------------------------------------------------- tabs

function toggleCross(dim, value) {
  const same = state.cross && state.cross.dim === dim && state.cross.value === value;
  update({ cross: same ? null : { dim, value } });
}

function renderOverview(c) {
  const view = model.view(state, 'overview');
  const t = view.tiles;
  tiles($('overview-tiles'), [
    tileData('Revenue', t.revenue, eurM, { caption: 'same months of the previous year as PY' }),
    tileData('Gross margin %', t.margin, (v) => fmt.pct(v), { key: 'margin', caption: 'net of discount' }),
    tileData('Orders', t.orders, (v) => fmt.int(v), { caption: 'distinct order numbers' }),
    tileData('Average order value', t.aov, money, { caption: 'revenue ÷ orders' }),
    tileData('Discount %', t.discount, (v) => fmt.pct(v), { key: 'discount', caption: 'of list value' }),
  ]);
  host.draw($('chart-revenue-py'), charts.revenuePy(view.months, c, motion()));
  host.draw($('chart-revenue-margin'), charts.revenueMargin(view.months, c, motion()));
  const segctl = $('analyse-by');
  segctl.replaceChildren(...ANALYSE.map((name) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = name;
    button.setAttribute('aria-pressed', String(state.analyseBy === name));
    button.addEventListener('click', () => update({ analyseBy: name, cross: null }));
    return button;
  }));
  $('analyse-title').textContent = `Revenue by ${state.analyseBy.toLowerCase()}`;
  const crossable = CROSS_DIMS.includes(state.analyseBy);
  $('analyse-hint').textContent = crossable
    ? 'Click a bar to cross-filter the page; click it again to clear · hover shows gross margin %'
    : 'Cross-filtering works for Region and Category · hover shows gross margin %';
  const selected = state.cross && state.cross.dim === state.analyseBy ? state.cross.value : null;
  host.draw($('chart-analyse'), charts.revenueBars(view.analyse, c, { selected, motion: motion() }), crossable
    ? (p) => toggleCross(state.analyseBy, p.name)
    : null);
}

function renderTrends(c) {
  const view = model.view(state, 'trends');
  const t = view.tiles;
  tiles($('trends-tiles'), [
    tileData('Revenue YTD', { value: t.ytd.value, delta: t.ytd.delta, note: t.ytd.delta === null ? 'no full previous year in the data' : null }, eurM, { caption: 'year to date, vs PY' }),
    { label: 'Revenue PYTD', value: eurM(t.pytd.value), caption: 'previous year to date' },
    { label: 'Revenue R12', value: eurM(t.r12.value), caption: t.r12.value === null ? 'needs 12 months of data' : 'rolling 12 months' },
    tileData('Units', t.units, (v) => fmt.int(v), { caption: 'pieces' }),
  ]);
  host.draw($('chart-trend'), charts.trend(view.rows, c, motion()));
  host.draw($('chart-units'), charts.stacked(view.units, model.data.dims.categories, c, { motion: motion() }));
  const rows = view.rows.map(([m, current, py, yoy, yoyPct, ytd, pytd, r12]) => ({ m, current, py, yoy, yoyPct, ytd, pytd, r12 }));
  table('ti', $('table-ti'), {
    caption: 'Revenue by month and calculation item',
    columns: [
      { key: 'm', label: 'Month', format: (m) => monthLabel(m) },
      { key: 'current', label: 'Current', ...num(money) },
      { key: 'py', label: 'PY', ...num(money) },
      { key: 'yoy', label: 'YoY', ...num(money) },
      { key: 'yoyPct', label: 'YoY %', ...num((v) => fmt.pct(v)) },
      { key: 'ytd', label: 'YTD', ...num(money) },
      { key: 'pytd', label: 'PYTD', ...num(money) },
      { key: 'r12', label: 'R12', ...num(money) },
    ],
    rows,
  }, 'm', 'asc');
}

function renderProducts(c) {
  const view = model.view(state, 'products');
  const t = view.tiles;
  tiles($('products-tiles'), [
    tileData('Revenue', t.revenue, eurM),
    tileData('Units', t.units, (v) => fmt.int(v), { caption: 'pieces' }),
    tileData('Gross margin %', t.margin, (v) => fmt.pct(v), { key: 'margin', caption: 'net of discount' }),
    { label: 'Products for 80 %', value: fmt.int(t.products80), caption: `of ${fmt.int(view.table.count)} products with sales` },
  ]);
  host.draw($('chart-pareto'), charts.pareto(view.pareto, c, motion()));
  const rows = model.productRows(state);
  tipRows = new Map(rows.map((r) => [r.sku, r]));
  const max = Math.max(0, ...rows.map((r) => r.revenue));
  table('products', $('table-products'), {
    caption: 'Products ranked by revenue',
    pageSize: 25,
    columns: [
      { key: 'rank', label: 'Rank', ...num((v) => fmt.int(v)) },
      { key: 'sku', label: 'SKU', format: skuButton },
      { key: 'name', label: 'Product' },
      { key: 'category', label: 'Category' },
      { key: 'revenue', label: 'Revenue', ...num(dataBar(max)) },
      { key: 'margin', label: 'Margin %', ...num((v) => fmt.pct(v)) },
      { key: 'units', label: 'Units', ...num((v) => fmt.int(v)) },
      { key: 'cumulative', label: 'Cumulative %', ...num((v) => fmt.pct(v)) },
      { key: 'cls', label: 'Class', format: (v) => {
        const span = document.createElement('span');
        span.className = 'pclass';
        span.textContent = v;
        return span;
      } },
    ],
    rows,
  }, 'revenue');
  const select = $('drill-select');
  select.replaceChildren(new Option('All categories', ''), ...model.data.dims.categories.map((name) => new Option(name, name)));
  select.value = state.drill ?? '';
  const crumbs = $('crumbs');
  if (state.drill) {
    const back = document.createElement('button');
    back.type = 'button';
    back.textContent = 'All categories';
    back.addEventListener('click', () => update({ drill: null }));
    const sep = document.createElement('span');
    sep.setAttribute('aria-hidden', 'true');
    sep.textContent = '›';
    const current = document.createElement('span');
    current.className = 'cur';
    current.setAttribute('aria-current', 'location');
    current.textContent = state.drill;
    crumbs.replaceChildren(back, sep, current);
  } else {
    const current = document.createElement('span');
    current.className = 'cur';
    current.textContent = 'All categories';
    crumbs.replaceChildren(current);
  }
  host.draw($('chart-category'), charts.revenueBars(view.bars, c, { motion: motion() }), state.drill
    ? null
    : (p) => update({ drill: p.name }));
}

function renderRegions(c) {
  const view = model.view(state, 'regions');
  const t = view.tiles;
  tiles($('regions-tiles'), [
    tileData('Revenue', t.revenue, eurM),
    tileData('Gross margin %', t.margin, (v) => fmt.pct(v), { key: 'margin', caption: 'net of discount' }),
    tileData('Active customers', t.active, (v) => fmt.int(v), { caption: 'customers with an order' }),
    tileData('Average order value', t.aov, money, { caption: 'revenue ÷ orders' }),
  ]);
  const selected = state.cross && state.cross.dim === 'Region' ? state.cross.value : null;
  host.draw($('chart-regions'), charts.regionBars(view.bars, c, { selected, motion: motion() }), (p) => toggleCross('Region', p.name));
  host.draw($('chart-region-months'), charts.stacked(view.months, model.data.dims.regions, c, { money: true, motion: motion() }));
  host.draw($('chart-scatter'), charts.scatter(view.countries, model.data.dims.regions, c, motion()));
  const rows = view.countries.map(([country, region, revenue, margin, discount, active, aov]) => ({ country, region, revenue, margin, discount, active, aov }));
  table('countries', $('table-countries'), {
    caption: 'Countries by revenue',
    columns: [
      { key: 'country', label: 'Country' },
      { key: 'region', label: 'Region' },
      { key: 'revenue', label: 'Revenue', ...num(money) },
      { key: 'margin', label: 'Margin %', ...num((v) => fmt.pct(v)) },
      { key: 'discount', label: 'Discount %', ...num((v) => fmt.pct(v)) },
      { key: 'active', label: 'Customers', ...num((v) => fmt.int(v)) },
      { key: 'aov', label: 'AOV', ...num(money) },
    ],
    rows,
  }, 'revenue');
}

let customerRows = [];

function filteredCustomers() {
  const query = $('customer-search').value.trim().toLowerCase();
  if (!query) return customerRows;
  return customerRows.filter((r) => [r.code, r.name, r.country, r.rep].some((v) => v.toLowerCase().includes(query)));
}

function renderCustomers() {
  const view = model.view(state, 'customers');
  const t = view.tiles;
  tiles($('customers-tiles'), [
    tileData('Active customers', t.active, (v) => fmt.int(v), { caption: 'customers with an order' }),
    tileData('Revenue', t.revenue, eurM),
    tileData('Orders', t.orders, (v) => fmt.int(v), { caption: 'distinct order numbers' }),
    tileData('Average order value', t.aov, money, { caption: 'revenue ÷ orders' }),
  ]);
  customerRows = view.rows;
  table('customers', $('table-customers'), {
    caption: 'Customers by revenue',
    pageSize: 25,
    emptyText: 'No customer matches the search',
    columns: [
      { key: 'code', label: 'Code' },
      { key: 'name', label: 'Customer' },
      { key: 'segment', label: 'Segment' },
      { key: 'channel', label: 'Channel' },
      { key: 'country', label: 'Country' },
      { key: 'rep', label: 'Sales rep' },
      { key: 'net', label: 'Revenue', ...num(money) },
      { key: 'margin', label: 'Margin %', ...num((v) => fmt.pct(v)) },
      { key: 'orders', label: 'Orders', ...num((v) => fmt.int(v)) },
      { key: 'aov', label: 'AOV', ...num(money) },
      { key: 'discount', label: 'Discount %', ...num((v) => fmt.pct(v)) },
    ],
    rows: filteredCustomers(),
  }, 'net');
}

function renderTargets(c) {
  const view = model.view(state, 'targets');
  const t = view.tiles;
  const attainment = t.attainment === null
    ? { kind: 'neutral', text: 'n/a: no target to date' }
    : { kind: t.attainment >= 1 ? 'up' : 'down', text: `${fmt.pp(t.attainment - 1)} vs target` };
  tiles($('targets-tiles'), [
    { label: 'Target to date', value: eurM(t.ttd), caption: 'target of the months with sales' },
    tileData('Revenue', t.revenue, eurM),
    { label: 'Target attainment %', value: fmt.pct(t.attainment), delta: attainment, caption: 'revenue ÷ target to date' },
    { label: 'Target gap', value: eurM(t.gap), caption: 'revenue − target to date' },
    { label: 'Target (full period)', value: eurM(t.target), caption: 'every selected month' },
  ]);
  host.draw($('chart-target'), charts.targetCombo(view.months, c, motion()));
  host.draw($('chart-attainment'), charts.attainment(view.regions, c, motion()));
  const months = [...new Set(view.matrix.map((r) => r[1]))].sort((a, b) => a - b);
  const head = $('table-attainment').tHead.rows[0];
  const th = (text) => {
    const cell = document.createElement('th');
    cell.scope = 'col';
    cell.textContent = text;
    return cell;
  };
  head.replaceChildren(th('Region'), ...charts.monthLabels(months).map(th));
  const body = $('table-attainment').tBodies[0];
  const regions = [...new Set(view.matrix.map((r) => r[0]))];
  body.replaceChildren(...regions.map((region) => {
    const tr = document.createElement('tr');
    const name = document.createElement('th');
    name.scope = 'row';
    name.textContent = region;
    tr.append(name);
    for (const m of months) {
      const value = view.matrix.find((r) => r[0] === region && r[1] === m)?.[2] ?? null;
      const td = document.createElement('td');
      td.className = 'v';
      td.textContent = fmt.pct(value);
      td.style.background = charts.cellShade(value);
      tr.append(td);
    }
    return tr;
  }));
}

const RENDER = { overview: renderOverview, trends: renderTrends, products: renderProducts, regions: renderRegions, customers: renderCustomers, targets: renderTargets };

function render() {
  syncFilters();
  hideTip();
  RENDER[state.tab](colours());
}

// ---------------------------------------------------------------- start

async function start() {
  mountBanner({ repoUrl: REPO });
  mountThemeToggle($('theme-toggle'));
  const app = $('app');
  try {
    if (!globalThis.echarts) throw new Error('the chart library did not load');
    const response = await fetch('assets/data/replica.json');
    if (!response.ok) throw new Error(`replica.json answered ${response.status}`);
    model = createModel(await response.json());
  } catch (error) {
    $('loading').className = 'app-error';
    $('loading').textContent = `The data could not be loaded (${error.message}). Reload the page to try again.`;
    app.dataset.state = 'error';
    return;
  }
  $('loading').remove();
  $('data-until').textContent = `Data until ${fmt.date(model.data.meta.dataUntil)}`;
  const themes = registerThemes(globalThis.echarts);
  host = charts.createChartHost(globalThis.echarts, themes, globalThis.pfTheme?.get() ?? 'dark');
  document.addEventListener('pf:theme', (e) => {
    host.setMode(e.detail.theme);
    render();
  });
  state = normaliseState(store.load(), model.data);
  state.tab = tabFromHash() ?? state.tab;
  buildFilters();
  bindTip($('table-products'));
  $('customer-search').addEventListener('input', () => tables.customers?.update(filteredCustomers()));
  $('drill-select').addEventListener('change', (e) => update({ drill: e.target.value || null }));
  $('about-open').addEventListener('click', () => $('about').showModal());
  $('forget').addEventListener('click', () => {
    store.clear();
    state = { ...defaultState(), tab: state.tab };
    render();
  });
  const tabs = initTabs($('tabs'), {
    onChange: (id) => {
      const tab = id.replace('tab-', '');
      if (tab === state.tab) return;
      history.replaceState(null, '', `#${tab}`);
      update({ tab, cross: null, drill: null });
    },
  });
  window.addEventListener('hashchange', () => {
    const tab = tabFromHash();
    if (tab && tab !== state.tab) tabs.select(`tab-${tab}`);
  });
  tabs.select(`tab-${state.tab}`);
  if (!location.hash) history.replaceState(null, '', `#${state.tab}`);
  render();
  app.dataset.state = 'ready';
}

start();
