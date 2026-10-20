import assert from 'node:assert/strict';
import test from 'node:test';

import {AuthorizedImportQueue} from '../../../../frontend/features/imports/import-queue.js';

function environment(saved = null) {
  const values = new Map();
  if (saved) values.set('audioextender.authorized-import-queue.v1', JSON.stringify(saved));
  globalThis.localStorage = {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key),
  };
  globalThis.window = {addEventListener: () => {}};
  Object.defineProperty(globalThis, 'navigator', {configurable:true, value:{onLine:true}});
  return values;
}

const select = () => null;
const escapeHtml = value => String(value);

test('restores queue order and converts interrupted items into reconnectable work', () => {
  environment({
    paused:true,
    basePayload:{confirmation:true},
    metadata:{},
    items:[
      {url:'https://soundcloud.com/a/one', status:'processing', importId:'abc', stage:'Downloading', progress:35},
      {url:'https://youtube.com/watch?v=two', status:'waiting', importId:null, stage:'Waiting', progress:0},
    ],
  });
  const queue = new AuthorizedImportQueue({select, escapeHtml, waitForImport:async()=>({}), onComplete:async()=>{}});
  assert.deepEqual(queue.state.items.map(item => item.url), [
    'https://soundcloud.com/a/one',
    'https://youtube.com/watch?v=two',
  ]);
  assert.equal(queue.state.items[0].status, 'waiting');
  assert.equal(queue.state.items[0].importId, 'abc');
  assert.equal(queue.state.items[0].stage, 'Reconnecting to import');
});

test('reordering is persisted while a queue is paused', async () => {
  const values = environment({
    paused:true,
    basePayload:{confirmation:true}, metadata:{},
    items:[
      {url:'first', status:'waiting', importId:null, stage:'Waiting', progress:0},
      {url:'second', status:'waiting', importId:null, stage:'Waiting', progress:0},
    ],
  });
  const queue = new AuthorizedImportQueue({select, escapeHtml, waitForImport:async()=>({}), onComplete:async()=>{}});
  await queue.act(1, 'up');
  const saved = JSON.parse(values.get('audioextender.authorized-import-queue.v1'));
  assert.deepEqual(saved.items.map(item => item.url), ['second', 'first']);
});
