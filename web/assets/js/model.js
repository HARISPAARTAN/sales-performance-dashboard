// Pure filter and aggregation code of the replica (no DOM access). It reads the cubes of replica.json and
// mirrors tools/reference.py: amounts in integer cents, date filters as sets of month indexes
// (1 = 2023-01), time-intelligence items over whole months with sales, DAX-like blanks (null).
// tests/replica/model.test.mjs checks every view against tests/replica/expected.json.

export const FIRST_YEAR = 2023;
export const YEARS = [2023, 2024, 2025];
export const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export const TABS = ['overview', 'trends', 'products', 'regions', 'customers', 'targets'];
export const ITEMS = ['Current', 'PY', 'YoY', 'YoY %', 'YTD', 'PYTD', 'R12'];
export const ANALYSE = ['Category', 'Region', 'Segment', 'Channel'];
export const CROSS_DIMS = ['Region', 'Category'];

export function defaultState() {
  return {
    tab: 'overview',
    years: [2025],
    monthFrom: 1,
    monthTo: 12,
    regions: [],
    categories: [],
    analyseBy: 'Category',
    cross: null,
    drill: null,
  };
}

// A stored state may be stale or edited by hand: keep only values the replica knows.
export function normaliseState(raw, data) {
  const base = defaultState();
  if (!raw || typeof raw !== 'object') return base;
  const pick = (list, allowed) => (Array.isArray(list) ? [...new Set(list.filter((v) => allowed.includes(v)))] : []);
  const month = (v, fallback) => (Number.isInteger(v) && v >= 1 && v <= 12 ? v : fallback);
  const out = {
    tab: TABS.includes(raw.tab) ? raw.tab : base.tab,
    years: Array.isArray(raw.years) ? pick(raw.years, YEARS).sort((a, b) => a - b) : base.years,
    monthFrom: month(raw.monthFrom, base.monthFrom),
    monthTo: month(raw.monthTo, base.monthTo),
    regions: pick(raw.regions, data.dims.regions),
    categories: pick(raw.categories, data.dims.categories),
    analyseBy: ANALYSE.includes(raw.analyseBy) ? raw.analyseBy : base.analyseBy,
    cross: null,
    drill: null,
  };
  if (out.monthFrom > out.monthTo) [out.monthFrom, out.monthTo] = [out.monthTo, out.monthFrom];
  const cross = raw.cross;
  if (cross && CROSS_DIMS.includes(cross.dim)) {
    const allowed = cross.dim === 'Region' ? data.dims.regions : data.dims.categories;
    if (allowed.includes(cross.value)) out.cross = { dim: cross.dim, value: cross.value };
  }
  if (data.dims.categories.includes(raw.drill)) out.drill = raw.drill;
  return out;
}

export function monthIndex(year, month) {
  return (year - FIRST_YEAR) * 12 + month;
}

export function monthYear(m) {
  return { year: FIRST_YEAR + Math.floor((m - 1) / 12), month: ((m - 1) % 12) + 1 };
}

export function monthLabel(m) {
  const { year, month } = monthYear(m);
  return `${MONTH_NAMES[month - 1]} ${year}`;
}

export function monthsOf(state) {
  const years = state.years.length ? state.years : YEARS;
  const out = new Set();
  for (const y of years) for (let m = state.monthFrom; m <= state.monthTo; m += 1) out.add(monthIndex(y, m));
  return out;
}

// One line for the phone filter disclosure: "2025 · Jan–Dec · all regions · all categories".
export function summary(state) {
  const years = state.years.length ? state.years.join(', ') : 'All years';
  const months = state.monthFrom === state.monthTo
    ? MONTH_NAMES[state.monthFrom - 1]
    : `${MONTH_NAMES[state.monthFrom - 1]}–${MONTH_NAMES[state.monthTo - 1]}`;
  const regions = state.regions.length ? state.regions.join(', ') : 'all regions';
  const categories = state.categories.length ? state.categories.join(', ') : 'all categories';
  return `${years} · ${months} · ${regions} · ${categories}`;
}

export function sub(a, b) {
  if (a === null && b === null) return null;
  return (a ?? 0) - (b ?? 0);
}

export function div(a, b) {
  if (a === null || b === null || b === 0) return null;
  return a / b;
}

function range(first, last) {
  const out = new Set();
  for (let m = first; m <= last; m += 1) out.add(m);
  return out;
}

function decode(cube, extra = []) {
  const length = cube.rows.reduce((a, b) => a + b, 0);
  const month = new Int16Array(length);
  let at = 0;
  cube.rows.forEach((count, i) => {
    month.fill(i + 1, at, at + count);
    at += count;
  });
  const out = { length, month };
  for (const [key, values] of Object.entries(cube)) if (key !== 'rows') out[key] = values;
  for (const key of extra) if (!(key in out)) throw new Error(`cube column ${key} missing`);
  return out;
}

const byValueThenLabel = (a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0);

export function createModel(data) {
  const { dims, meta } = data;
  const lastMonth = meta.lastMonth;
  const S = decode(data.S, ['country', 'cat', 'seg', 'ch', 'net', 'gross', 'cost', 'units']);
  const P = decode(data.P, ['product', 'region', 'net', 'cost', 'units']);
  const C = decode(data.C, ['customer', 'net', 'gross', 'cost', 'orders']);
  const O = decode(data.O, ['customer', 'mask']);
  const countryRegion = dims.countries.map((c) => c[2]);
  const customerCountry = dims.customers.country;
  const customerRegion = customerCountry.map((c) => countryRegion[c]);
  const productSub = dims.products.sub;
  const productCategory = productSub.map((s) => dims.subcategories[s][1]);
  const regionIndex = (name) => dims.regions.indexOf(name);
  const categoryIndex = (name) => dims.categories.indexOf(name);

  // ------------------------------------------------------------ contexts

  function context(state, tab, { cross = true } = {}) {
    let regions = state.regions.length ? new Set(state.regions.map(regionIndex)) : null;
    let categories = state.categories.length ? new Set(state.categories.map(categoryIndex)) : null;
    const own = state.tab === tab;
    if (cross && own && state.cross) {
      if (state.cross.dim === 'Region') regions = new Set([regionIndex(state.cross.value)]);
      else categories = new Set([categoryIndex(state.cross.value)]);
    }
    if (cross && own && tab === 'products' && state.drill) categories = new Set([categoryIndex(state.drill)]);
    if (tab === 'customers' || tab === 'targets') categories = null;
    return { months: monthsOf(state), regions, categories, segment: null, channel: null, sub: null };
  }

  const at = (ctx, months) => ({ ...ctx, months: months instanceof Set ? months : new Set(months) });
  const where = (ctx, changes) => ({ ...ctx, ...changes });
  const pastOf = (months) => [...months].filter((m) => m <= lastMonth).sort((a, b) => a - b);

  // ------------------------------------------------------------ sums over the cubes

  function sumS(ctx, months) {
    let net = 0, gross = 0, cost = 0, units = 0, n = 0;
    for (let i = 0; i < S.length; i += 1) {
      if (!months.has(S.month[i])) continue;
      if (ctx.regions && !ctx.regions.has(countryRegion[S.country[i]])) continue;
      if (ctx.categories && !ctx.categories.has(S.cat[i])) continue;
      if (ctx.segment !== null && S.seg[i] !== ctx.segment) continue;
      if (ctx.channel !== null && S.ch[i] !== ctx.channel) continue;
      net += S.net[i]; gross += S.gross[i]; cost += S.cost[i]; units += S.units[i]; n += 1;
    }
    return n ? { net, gross, cost, units } : null;
  }

  function sumP(ctx, months) {
    let net = 0, cost = 0, units = 0, n = 0;
    for (let i = 0; i < P.length; i += 1) {
      if (!months.has(P.month[i])) continue;
      if (ctx.regions && !ctx.regions.has(P.region[i])) continue;
      const product = P.product[i];
      if (ctx.categories && !ctx.categories.has(productCategory[product])) continue;
      if (ctx.sub !== null && productSub[product] !== ctx.sub) continue;
      net += P.net[i]; cost += P.cost[i]; units += P.units[i]; n += 1;
    }
    return n ? { net, gross: null, cost, units } : null;
  }

  function sumC(ctx, months) {
    let net = 0, gross = 0, cost = 0, orders = 0, n = 0;
    const seen = new Set();
    for (let i = 0; i < C.length; i += 1) {
      if (!months.has(C.month[i])) continue;
      if (ctx.regions && !ctx.regions.has(customerRegion[C.customer[i]])) continue;
      net += C.net[i]; gross += C.gross[i]; cost += C.cost[i]; orders += C.orders[i]; n += 1;
      seen.add(C.customer[i]);
    }
    return n ? { net, gross, cost, orders, active: seen.size } : null;
  }

  function countO(ctx, months) {
    let mask = 0;
    if (ctx.categories) for (const c of ctx.categories) mask |= 1 << c;
    let orders = 0;
    const seen = new Set();
    for (let i = 0; i < O.length; i += 1) {
      if (!months.has(O.month[i])) continue;
      const customer = O.customer[i];
      if (ctx.regions && !ctx.regions.has(customerRegion[customer])) continue;
      if (ctx.categories && (O.mask[i] & mask) === 0) continue;
      orders += 1;
      seen.add(customer);
    }
    return orders ? { orders, active: seen.size } : null;
  }

  // measure(name, ctx, source)(months) -> value or null; source S (sales), P (products) or C (customers)
  function measureFn(name, ctx, source = 'S') {
    const sums = source === 'P' ? sumP : source === 'C' ? sumC : sumS;
    const orders = (months) => (source === 'C' ? sumC(ctx, months) : countO(ctx, months));
    const pick = (field) => (months) => sums(ctx, months)?.[field] ?? null;
    const revenue = pick('net');
    switch (name) {
      case 'Revenue': return revenue;
      case 'Gross sales': return pick('gross');
      case 'Cost': return pick('cost');
      case 'Units': return pick('units');
      case 'Gross margin %': return (months) => {
        const s = sums(ctx, months);
        return s ? div(sub(s.net, s.cost), s.net) : null;
      };
      case 'Discount %': return (months) => {
        const s = sums(ctx, months);
        return s ? div(sub(s.gross, s.net), s.gross) : null;
      };
      case 'Orders': return (months) => orders(months)?.orders ?? null;
      case 'Active customers': return (months) => orders(months)?.active ?? null;
      case 'Average order value': return (months) => div(revenue(months), orders(months)?.orders ?? null);
      default: throw new Error(`unknown measure ${name}`);
    }
  }

  const PCT = new Set(['Gross margin %', 'Discount %', 'Target attainment %']);

  function item(fn, calculation, months, pct) {
    if (calculation === 'Current') return fn(months);
    const past = pastOf(months);
    if (!past.length) return null;
    const last = past[past.length - 1];
    const full = past[0] > 12;
    const cur = () => fn(new Set(past));
    const py = () => fn(new Set(past.map((m) => m - 12)));
    switch (calculation) {
      case 'PY': return py();
      case 'YoY': {
        if (!full) return null;
        const c = cur();
        const p = py();
        if (c === null || p === null) return null;
        return pct ? (c - p) * 100 : c - p;
      }
      case 'YoY %': return !pct && full ? div(sub(cur(), py()), py()) : null;
      case 'YTD': return fn(range(last - ((last - 1) % 12), last));
      case 'PYTD': return fn(range(last - 12 - ((last - 1) % 12), last - 12));
      case 'R12': return last >= 12 ? fn(range(last - 11, last)) : null;
      default: throw new Error(`unknown calculation item ${calculation}`);
    }
  }

  function tile(name, ctx, source = 'S') {
    const fn = measureFn(name, ctx, source);
    const pct = PCT.has(name);
    const delta = item(fn, pct ? 'YoY' : 'YoY %', ctx.months, pct);
    const past = pastOf(ctx.months);
    let note = null;
    if (delta === null) {
      note = past.length ? 'no full previous year in the data' : 'no sales in the selected months';
      if (past.length && past[0] > 12) note = 'no previous-year value';
    }
    return { value: fn(ctx.months), py: item(fn, 'PY', ctx.months, pct), delta, note };
  }

  function bars(ctx, source, dimension, members) {
    const out = [];
    members.forEach((label, index) => {
      let scoped;
      if (dimension === 'Region') {
        if (ctx.regions && !ctx.regions.has(index)) return;
        scoped = where(ctx, { regions: new Set([index]) });
      } else if (dimension === 'Category') {
        if (ctx.categories && !ctx.categories.has(index)) return;
        scoped = where(ctx, { categories: new Set([index]) });
      } else if (dimension === 'Segment') scoped = where(ctx, { segment: index });
      else if (dimension === 'Channel') scoped = where(ctx, { channel: index });
      else scoped = where(ctx, { sub: index });
      const revenue = measureFn('Revenue', scoped, source)(ctx.months);
      if (revenue !== null) out.push([label, revenue, measureFn('Gross margin %', scoped, source)(ctx.months)]);
    });
    return out.sort(byValueThenLabel);
  }

  // ------------------------------------------------------------ targets

  function target(ctx, months) {
    let total = 0, n = 0;
    data.T.forEach((series, region) => {
      if (ctx.regions && !ctx.regions.has(region)) return;
      for (const m of months) {
        if (m >= 1 && m <= series.length) {
          total += series[m - 1] * 100;
          n += 1;
        }
      }
    });
    return n ? total : null;
  }
  const targetToDate = (ctx, months) => target(ctx, new Set(pastOf(months)));
  const attainment = (ctx, months) => div(measureFn('Revenue', ctx)(months), targetToDate(ctx, months));

  // ------------------------------------------------------------ product table

  function productRows(ctx) {
    const by = new Map();
    for (let i = 0; i < P.length; i += 1) {
      if (!ctx.months.has(P.month[i])) continue;
      if (ctx.regions && !ctx.regions.has(P.region[i])) continue;
      const product = P.product[i];
      if (ctx.categories && !ctx.categories.has(productCategory[product])) continue;
      const row = by.get(product) ?? { product, revenue: 0, cost: 0, units: 0 };
      row.revenue += P.net[i]; row.cost += P.cost[i]; row.units += P.units[i];
      by.set(product, row);
    }
    const rows = [...by.values()].map((r) => ({ ...r, sku: dims.products.sku[r.product], name: dims.products.name[r.product] }));
    rows.sort((a, b) => b.revenue - a.revenue || (a.sku < b.sku ? -1 : a.sku > b.sku ? 1 : 0));
    const total = rows.reduce((a, r) => a + r.revenue, 0);
    for (const row of rows) {
      let above = 0, cumulative = 0;
      for (const other of rows) {
        if (other.revenue > row.revenue) above += 1;
        if (other.revenue >= row.revenue) cumulative += other.revenue;
      }
      row.rank = above + 1;
      row.cumulativeCents = cumulative;
      row.cumulative = cumulative / total;
      row.cls = row.cumulative <= 0.8 ? 'A' : row.cumulative <= 0.95 ? 'B' : 'C';
      row.margin = (row.revenue - row.cost) / row.revenue;
      row.category = dims.categories[productCategory[row.product]];
      row.subcategory = dims.subcategories[productSub[row.product]][0];
    }
    return { rows, total };
  }

  function productsFor80(ctx) {
    const { rows, total } = productRows(ctx);
    return rows.filter((r) => r.cumulativeCents <= 0.8 * total).length;
  }

  function productMonths(ctx, product) {
    const out = new Map();
    for (let i = 0; i < P.length; i += 1) {
      if (P.product[i] !== product || !ctx.months.has(P.month[i])) continue;
      if (ctx.regions && !ctx.regions.has(P.region[i])) continue;
      out.set(P.month[i], (out.get(P.month[i]) ?? 0) + P.net[i]);
    }
    return pastOf(ctx.months).map((m) => [m, out.get(m) ?? null]);
  }

  // ------------------------------------------------------------ views (one per tab)

  function overview(state) {
    const ctx = context(state, 'overview');
    const tiles = {
      revenue: tile('Revenue', ctx),
      margin: tile('Gross margin %', ctx),
      orders: tile('Orders', ctx),
      aov: tile('Average order value', ctx),
      discount: tile('Discount %', ctx),
    };
    const revenue = measureFn('Revenue', ctx);
    const margin = measureFn('Gross margin %', ctx);
    const months = pastOf(ctx.months).map((m) => {
      const one = new Set([m]);
      return [m, revenue(one), item(revenue, 'PY', one, false), margin(one)];
    });
    const members = { Category: dims.categories, Region: dims.regions, Segment: dims.segments, Channel: dims.channels };
    const analyse = bars(context(state, 'overview', { cross: false }), 'S', state.analyseBy, members[state.analyseBy]);
    return { tiles, months, analyse };
  }

  function trends(state) {
    const ctx = context(state, 'trends');
    const revenue = measureFn('Revenue', ctx);
    const tiles = {
      ytd: { value: item(revenue, 'YTD', ctx.months, false), delta: item(revenue, 'YoY %', ctx.months, false) },
      pytd: { value: item(revenue, 'PYTD', ctx.months, false) },
      r12: { value: item(revenue, 'R12', ctx.months, false) },
      units: tile('Units', ctx),
    };
    const past = pastOf(ctx.months);
    const rows = past.map((m) => [m, ...ITEMS.map((calc) => item(revenue, calc, new Set([m]), false))]);
    const units = past.map((m) => [
      m,
      dims.categories.map((_, c) => measureFn('Units', where(ctx, { categories: ctx.categories && !ctx.categories.has(c) ? new Set() : new Set([c]) }))(new Set([m]))),
    ]);
    return { tiles, rows, units };
  }

  function products(state) {
    const ctx = context(state, 'products');
    const tiles = {
      revenue: tile('Revenue', ctx, 'P'),
      units: tile('Units', ctx, 'P'),
      margin: tile('Gross margin %', ctx, 'P'),
      products80: productsFor80(ctx),
    };
    const { rows } = productRows(ctx);
    const pareto = rows.slice(0, 40).map((r) => [r.sku, r.revenue, r.cumulative]);
    const top = rows.slice(0, 10).map((r) => [r.rank, r.sku, r.revenue, r.units, r.margin, r.cumulative, r.cls]);
    let chart;
    if (state.tab === 'products' && state.drill) {
      const category = categoryIndex(state.drill);
      const subs = [];
      dims.subcategories.forEach(([name, cat], index) => { if (cat === category) subs.push([name, index]); });
      chart = [];
      for (const [name, index] of subs) {
        const scoped = where(ctx, { sub: index });
        const revenue = measureFn('Revenue', scoped, 'P')(ctx.months);
        if (revenue !== null) chart.push([name, revenue, measureFn('Gross margin %', scoped, 'P')(ctx.months)]);
      }
      chart.sort(byValueThenLabel);
    } else {
      chart = bars(context(state, 'products', { cross: false }), 'P', 'Category', dims.categories);
    }
    return { tiles, pareto, table: { count: rows.length, top }, bars: chart };
  }

  function regions(state) {
    const ctx = context(state, 'regions');
    const tiles = {
      revenue: tile('Revenue', ctx),
      margin: tile('Gross margin %', ctx),
      active: tile('Active customers', ctx),
      aov: tile('Average order value', ctx),
    };
    const source = context(state, 'regions', { cross: false });
    const regionBars = [];
    dims.regions.forEach((name, index) => {
      if (source.regions && !source.regions.has(index)) return;
      const revenue = measureFn('Revenue', where(source, { regions: new Set([index]) }));
      const cur = revenue(source.months);
      const py = item(revenue, 'PY', source.months, false);
      if (cur !== null || py !== null) regionBars.push([name, cur, py]);
    });
    const countries = [];
    dims.countries.forEach(([name, , region], index) => {
      if (ctx.regions && !ctx.regions.has(region)) return;
      let net = 0, gross = 0, cost = 0, n = 0;
      for (let i = 0; i < S.length; i += 1) {
        if (S.country[i] !== index || !ctx.months.has(S.month[i])) continue;
        if (ctx.categories && !ctx.categories.has(S.cat[i])) continue;
        net += S.net[i]; gross += S.gross[i]; cost += S.cost[i]; n += 1;
      }
      if (!n) return;
      let mask = 0;
      if (ctx.categories) for (const c of ctx.categories) mask |= 1 << c;
      let orders = 0;
      const seen = new Set();
      for (let i = 0; i < O.length; i += 1) {
        if (!ctx.months.has(O.month[i]) || customerCountry[O.customer[i]] !== index) continue;
        if (ctx.categories && (O.mask[i] & mask) === 0) continue;
        orders += 1;
        seen.add(O.customer[i]);
      }
      countries.push([name, dims.regions[region], net, (net - cost) / net, (gross - net) / gross, seen.size, net / orders]);
    });
    countries.sort((a, b) => b[2] - a[2] || (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
    const months = pastOf(ctx.months).map((m) => [
      m,
      dims.regions.map((_, r) => (ctx.regions && !ctx.regions.has(r) ? null : measureFn('Revenue', where(ctx, { regions: new Set([r]) }))(new Set([m])))),
    ]);
    return { tiles, bars: regionBars, countries, months };
  }

  function customers(state) {
    const ctx = context(state, 'customers');
    const tiles = {
      active: tile('Active customers', ctx, 'C'),
      revenue: tile('Revenue', ctx, 'C'),
      orders: tile('Orders', ctx, 'C'),
      aov: tile('Average order value', ctx, 'C'),
    };
    const by = new Map();
    for (let i = 0; i < C.length; i += 1) {
      if (!ctx.months.has(C.month[i])) continue;
      const customer = C.customer[i];
      if (ctx.regions && !ctx.regions.has(customerRegion[customer])) continue;
      const row = by.get(customer) ?? { customer, net: 0, gross: 0, cost: 0, orders: 0 };
      row.net += C.net[i]; row.gross += C.gross[i]; row.cost += C.cost[i]; row.orders += C.orders[i];
      by.set(customer, row);
    }
    const rows = [...by.values()].map((r) => ({
      ...r,
      code: dims.customers.code[r.customer],
      name: dims.customers.name[r.customer],
      segment: dims.segments[dims.customers.segment[r.customer]],
      channel: dims.channels[dims.customers.channel[r.customer]],
      country: dims.countries[dims.customers.country[r.customer]][0],
      rep: dims.reps.name[dims.customers.rep[r.customer]],
      margin: (r.net - r.cost) / r.net,
      aov: r.net / r.orders,
      discount: (r.gross - r.net) / r.gross,
    }));
    rows.sort((a, b) => b.net - a.net || (a.code < b.code ? -1 : a.code > b.code ? 1 : 0));
    const top = rows.slice(0, 10).map((r) => [r.code, r.net, r.margin, r.orders, r.aov, r.discount]);
    return { tiles, table: { count: rows.length, top }, rows };
  }

  function targets(state) {
    const ctx = context(state, 'targets');
    const revenue = measureFn('Revenue', ctx);
    const ttd = targetToDate(ctx, ctx.months);
    const rev = revenue(ctx.months);
    const tiles = {
      ttd,
      revenue: tile('Revenue', ctx),
      attainment: div(rev, ttd),
      gap: ttd === null ? null : sub(rev, ttd),
      target: target(ctx, ctx.months),
    };
    const months = [...ctx.months].sort((a, b) => a - b).map((m) => [m, revenue(new Set([m])), target(ctx, new Set([m]))]);
    const order = dims.regions.map((name, index) => [name, index]).filter(([, i]) => !ctx.regions || ctx.regions.has(i));
    const byRegion = order.map(([name, i]) => [name, attainment(where(ctx, { regions: new Set([i]) }), ctx.months)]);
    const matrix = [];
    for (const [name, i] of order) {
      for (const m of pastOf(ctx.months)) matrix.push([name, m, attainment(where(ctx, { regions: new Set([i]) }), new Set([m]))]);
    }
    return { tiles, months, regions: byRegion, matrix };
  }

  const views = { overview, trends, products, regions, customers, targets };

  return {
    data,
    lastMonth,
    views,
    view: (state, tab = state.tab) => views[tab](state),
    productRows: (state) => productRows(context(state, 'products')).rows,
    productMonths: (state, product) => productMonths(context(state, 'products'), product),
    context,
  };
}
