// web/assets/js/model.js on web/assets/data/replica.json must reproduce tests/replica/expected.json, which
// tools/build_replica_data.py computes with tools/reference.py from the order lines.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createModel, defaultState, monthsOf, normaliseState, summary, sub, div, TABS } from '../../web/assets/js/model.js';

const root = new URL('../../', import.meta.url);
const data = JSON.parse(readFileSync(new URL('web/assets/data/replica.json', root), 'utf8'));
const expected = JSON.parse(readFileSync(new URL('tests/replica/expected.json', root), 'utf8'));
const model = createModel(data);

// Compare the keys the reference wrote; numbers to a relative 1e-9 (the reference divides in float64 too).
function close(actual, wanted, path) {
  if (wanted === null || typeof wanted !== 'object') {
    if (typeof wanted === 'number' && typeof actual === 'number') {
      const scale = Math.max(1, Math.abs(wanted));
      assert.ok(Math.abs(actual - wanted) <= 1e-9 * scale, `${path}: ${actual} != ${wanted}`);
    } else {
      assert.equal(actual, wanted, path);
    }
    return;
  }
  assert.ok(actual !== null && typeof actual === 'object', `${path}: expected an object or array, got ${actual}`);
  if (Array.isArray(wanted)) {
    assert.ok(Array.isArray(actual), `${path}: expected an array`);
    assert.equal(actual.length, wanted.length, `${path}: length`);
  }
  for (const key of Object.keys(wanted)) close(actual[key], wanted[key], `${path}.${key}`);
}

test('the expected file holds the 12 states of the spec', () => {
  assert.equal(expected.states.length, 12);
  assert.deepEqual(expected.states[0].state, defaultState());
});

for (const entry of expected.states) {
  test(`state "${entry.name}": every tab matches the reference`, () => {
    for (const tab of TABS) close(model.view(entry.state, tab), entry.views[tab], `${entry.name}.${tab}`);
  });
}

test('month indexes of a state', () => {
  assert.deepEqual([...monthsOf(defaultState())], [25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36]);
  assert.deepEqual([...monthsOf({ ...defaultState(), years: [], monthFrom: 12, monthTo: 12 })], [12, 24, 36]);
});

test('blank arithmetic follows DAX', () => {
  assert.equal(sub(null, null), null);
  assert.equal(sub(null, 5), -5);
  assert.equal(sub(7, null), 7);
  assert.equal(div(1, 0), null);
  assert.equal(div(null, 2), null);
  assert.equal(div(1, 4), 0.25);
});

test('a stored state is cleaned before use', () => {
  const raw = {
    tab: 'nowhere',
    years: [2025, 2019, 2025],
    monthFrom: 9,
    monthTo: 3,
    regions: ['Nordics', 'Atlantis'],
    categories: ['Tents'],
    analyseBy: 'Colour',
    cross: { dim: 'Region', value: 'Iberia' },
    drill: 'Kites',
  };
  assert.deepEqual(normaliseState(raw, data), {
    ...defaultState(),
    years: [2025],
    monthFrom: 3,
    monthTo: 9,
    regions: ['Nordics'],
    categories: ['Tents'],
    cross: { dim: 'Region', value: 'Iberia' },
  });
  assert.deepEqual(normaliseState('not an object', data), defaultState());
  assert.deepEqual(normaliseState({ years: [] }, data).years, []);
});

test('the phone filter summary', () => {
  assert.equal(summary(defaultState()), '2025 · Jan–Dec · all regions · all categories');
  assert.equal(
    summary({ ...defaultState(), years: [], monthFrom: 9, monthTo: 9, regions: ['DACH'], categories: ['Tents', 'Cooking'] }),
    'All years · Sep · DACH · Tents, Cooking',
  );
});

test('the products table pages through every product with revenue', () => {
  const rows = model.productRows(defaultState());
  const products = model.view(defaultState(), 'products');
  assert.equal(rows.length, products.table.count);
  assert.ok(rows.every((r, i) => i === 0 || rows[i - 1].revenue >= r.revenue));
  assert.equal(model.productMonths(defaultState(), rows[0].product).length, 9);
});
