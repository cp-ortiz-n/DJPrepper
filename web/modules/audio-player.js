import {clock, escapeHtml} from './ui.js';

const engine = new Audio();
engine.preload = 'none';
let owner = null;

function render(player = owner) {
  if (!player?.isConnected) return;
  const duration = Number.isFinite(engine.duration) ? engine.duration : Number(player.dataset.duration || 0);
  const seek = player.querySelector('.compact-audio-seek');
  player.querySelector('.compact-audio-time').textContent = `${clock(engine.currentTime || 0)} / ${clock(duration)}`;
  if (seek && !seek.matches(':active')) seek.value = duration ? String(Math.round((engine.currentTime || 0) / duration * 1000)) : '0';
}

export function bindLazyAudio(scope = document) {
  scope.querySelectorAll('audio[data-src]').forEach(audio => {
    if (audio.dataset.lazyBound === 'true') return;
    audio.dataset.lazyBound = 'true';
    const activate = () => {
      if (audio.getAttribute('src')) return;
      audio.src = audio.dataset.src;
      audio.removeAttribute('data-src');
      audio.load();
    };
    audio.addEventListener('pointerdown', activate, {once:true});
    audio.addEventListener('focus', activate, {once:true});
    audio.addEventListener('keydown', activate, {once:true});
  });
}

export function compactAudioMarkup(src, duration = 0, seekable = false) {
  return `<div class="compact-audio${seekable ? ' seekable' : ''}" data-src="${escapeHtml(src)}" data-duration="${Number(duration) || 0}"><button type="button" class="compact-audio-play" aria-label="Play track">▶</button><span class="compact-audio-time">0:00 / ${clock(duration)}</span>${seekable ? '<input class="compact-audio-seek" type="range" min="0" max="1000" value="0" aria-label="Seek through track">' : ''}<button type="button" class="compact-audio-volume" aria-label="Mute track">🔊</button></div>`;
}

export function stopCompactAudio() {
  engine.pause();
  engine.currentTime = 0;
  if (owner?.isConnected) {
    const play = owner.querySelector('.compact-audio-play');
    if (play) { play.textContent = '▶'; play.setAttribute('aria-label', 'Play track'); }
    render(owner);
  }
  owner = null;
}

export function compactAudioIsWithin(selector) { return Boolean(owner?.closest(selector)); }

export function stopNativeAudio(except = null, scope = document) {
  scope.querySelectorAll('audio,video').forEach(media => {
    if (media !== except && !media.paused) media.pause();
  });
}

export function bindCompactAudio(scope = document) {
  scope.querySelectorAll('.compact-audio').forEach(player => {
    if (player.dataset.bound === 'true') return;
    player.dataset.bound = 'true';
    const play = player.querySelector('.compact-audio-play');
    const volume = player.querySelector('.compact-audio-volume');
    const seek = player.querySelector('.compact-audio-seek');
    const activate = () => {
      if (owner === player) return;
      if (owner?.isConnected) {
        const oldPlay = owner.querySelector('.compact-audio-play');
        if (oldPlay) { oldPlay.textContent = '▶'; oldPlay.setAttribute('aria-label', 'Play track'); }
      }
      engine.pause();
      owner = player;
      engine.src = player.dataset.src;
      engine.load();
    };
    play.onclick = async event => {
      event.stopPropagation();
      const wasOwner = owner === player;
      activate();
      if (!wasOwner || engine.paused) {
        stopNativeAudio();
        try { await engine.play(); } catch (_) { play.textContent = '▶'; }
      } else engine.pause();
    };
    volume.onclick = event => {
      event.stopPropagation();
      activate();
      engine.muted = !engine.muted;
      volume.textContent = engine.muted ? '🔇' : '🔊';
      volume.setAttribute('aria-label', engine.muted ? 'Unmute track' : 'Mute track');
    };
    if (seek) {
      seek.onpointerdown = event => event.stopPropagation();
      seek.onclick = event => event.stopPropagation();
      seek.oninput = event => {
        event.stopPropagation();
        activate();
        const duration = Number.isFinite(engine.duration) ? engine.duration : Number(player.dataset.duration || 0);
        if (duration) engine.currentTime = Number(seek.value) / 1000 * duration;
        render(player);
      };
    }
  });
}

engine.addEventListener('play', () => {
  const play = owner?.querySelector('.compact-audio-play');
  if (play) { play.textContent = '❚❚'; play.setAttribute('aria-label', 'Pause track'); }
});
engine.addEventListener('pause', () => {
  const play = owner?.querySelector('.compact-audio-play');
  if (play) { play.textContent = '▶'; play.setAttribute('aria-label', 'Play track'); }
});
engine.addEventListener('ended', () => { engine.currentTime = 0; render(); });
engine.addEventListener('loadedmetadata', () => render());
engine.addEventListener('timeupdate', () => render());
