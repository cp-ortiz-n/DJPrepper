import test from 'node:test';
import assert from 'node:assert/strict';

class FakeAudio {
  static instances = [];
  constructor() {
    this.paused = true;
    this.currentTime = 0;
    this.duration = 180;
    this.muted = false;
    this.listeners = new Map();
    FakeAudio.instances.push(this);
  }
  addEventListener(name, callback) { this.listeners.set(name, callback); }
  dispatch(name) { this.listeners.get(name)?.(); }
  load() {}
  pause() { this.paused = true; this.dispatch('pause'); }
  async play() { this.paused = false; this.dispatch('play'); }
}

globalThis.Audio = FakeAudio;

const button = label => ({textContent:'▶', attributes:{'aria-label':label}, setAttribute(name, value) { this.attributes[name] = value; }});
const player = src => {
  const play = button('Play track');
  const volume = button('Mute track');
  const time = {textContent:''};
  return {
    dataset:{src,duration:'180'}, isConnected:true,
    querySelector(selector) { return {'.compact-audio-play':play,'.compact-audio-volume':volume,'.compact-audio-time':time}[selector] || null; },
    closest() { return null; },
    parts:{play,volume,time},
  };
};

const nativeAudio = () => ({paused:false,pauseCount:0,pause() { this.paused=true; this.pauseCount += 1; }});
const pageNative = nativeAudio();
const inspectorNative = nativeAudio();
const inspector = {hidden:false,dataset:{returnId:'9'},querySelectorAll(selector) { return selector === 'audio,video' ? [inspectorNative] : []; }};
globalThis.document = {
  querySelector(selector) { return selector === '#downloaded-inspector' ? inspector : null; },
  querySelectorAll(selector) { return selector === 'audio,video' ? [pageNative] : []; },
};

const playback = await import('../../web/playback.js');

test('starting another preview transfers the single playback owner', async () => {
  const first = player('/first.wav');
  const second = player('/second.wav');
  playback.bindCompactAudio({querySelectorAll:selector => selector === '.compact-audio' ? [first, second] : []});

  await first.parts.play.onclick({stopPropagation() {}});
  assert.equal(first.parts.play.attributes['aria-label'], 'Pause track');
  assert.equal(pageNative.pauseCount, 1);

  await second.parts.play.onclick({stopPropagation() {}});
  assert.equal(first.parts.play.attributes['aria-label'], 'Play track');
  assert.equal(second.parts.play.attributes['aria-label'], 'Pause track');
  assert.equal(FakeAudio.instances[0].src, '/second.wav');
});

test('closing Quick View stops its native audio', () => {
  playback.closeDownloadedInspector();
  assert.equal(inspector.hidden, true);
  assert.equal(inspectorNative.paused, true);
  assert.equal(inspectorNative.pauseCount, 1);
});
