import test from 'node:test';
import assert from 'node:assert/strict';

import {createRequestStateController} from '../web/request-state-controller.js';

function deferred() {
  let resolve;
  const promise=new Promise(done=>{resolve=done;});
  return {promise,resolve};
}

function response(payload) {
  return {ok:true,json:async()=>payload};
}

function storage(seed={}) {
  const values=new Map(Object.entries(seed));
  return {
    values,
    getItem:key=>values.get(key)??null,
    setItem:(key,value)=>values.set(key,String(value)),
  };
}

test('new request cancels the prior request and rejects a stale response', async () => {
  const first=deferred();
  const second=deferred();
  const signals=[];
  const controller=createRequestStateController({
    namespace:'music',state:{search:'',page:1},defaults:{search:'',page:1},
    storage:storage(),location:null,history:null,
    fetchImpl:(_url,options)=>{signals.push(options.signal);return signals.length===1?first.promise:second.promise;},
  });
  const older=controller.request('/first');
  const newer=controller.request('/second');
  assert.equal(signals[0].aborted,true);
  second.resolve(response({tracks:['new']}));
  assert.deepEqual(await newer,{status:'applied',payload:{tracks:['new']}});
  first.resolve(response({tracks:['old']}));
  // A transport that ignores AbortSignal can still finish; sequence rejection
  // guarantees that its older payload is never rendered.
  assert.equal((await older).status,'stale');
});

test('loading state belongs only to the newest request', async () => {
  const first=deferred(); const second=deferred(); const changes=[]; let calls=0;
  const controller=createRequestStateController({
    namespace:'dj',state:{page:1},defaults:{page:1},storage:storage(),location:null,history:null,
    fetchImpl:()=>++calls===1?first.promise:second.promise,
    onLoading:value=>changes.push(value),
  });
  const older=controller.request('/first');
  const newer=controller.request('/second');
  first.resolve(response({page:1}));
  await older;
  assert.deepEqual(changes,[true,true]);
  second.resolve(response({page:2}));
  await newer;
  assert.deepEqual(changes,[true,true,false]);
});

test('state restores from session then URL and persists pagination and filters', () => {
  const saved=storage({'audioextender:music:request-state':JSON.stringify({search:'session',page:3,pageSize:25})});
  const replacements=[];
  const state={search:'',page:1,pageSize:50,genre:'all'};
  const controller=createRequestStateController({
    namespace:'music',state,defaults:{search:'',page:1,pageSize:50,genre:'all'},storage:saved,
    location:{href:'http://localhost/?v=music&music_search=url-value&music_page=4#tracks'},
    history:{state:null,replaceState:(_state,_title,url)=>replacements.push(url)},
  });
  assert.deepEqual(state,{search:'url-value',page:4,pageSize:25,genre:'all'});
  controller.update({genre:'Electronic / House'});
  assert.equal(state.page,1);
  const persisted=JSON.parse(saved.getItem('audioextender:music:request-state'));
  assert.equal(persisted.genre,'Electronic / House');
  assert.match(replacements.at(-1),/music_genre=Electronic(?:\+|%20)%2F(?:\+|%20)House/);
  assert.match(replacements.at(-1),/v=music/);
  assert.match(replacements.at(-1),/#tracks$/);
});

test('debounce commits only the latest filter callback', async () => {
  const controller=createRequestStateController({
    namespace:'dj',state:{search:'',page:1},defaults:{search:'',page:1},
    storage:storage(),location:null,history:null,debounceMs:5,
  });
  const calls=[];
  controller.debounce(()=>calls.push('old'));
  controller.debounce(()=>calls.push('new'));
  await new Promise(resolve=>setTimeout(resolve,20));
  assert.deepEqual(calls,['new']);
});
