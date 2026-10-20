import {$, clock, escapeHtml} from './shared-components.js';

const compactAudioEngine = new Audio();
compactAudioEngine.preload = 'none';
let compactAudioOwner = null;

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

export function compactAudioMarkup(src, duration=0, seekable=false) {
  return `<div class="compact-audio${seekable?' seekable':''}" data-src="${escapeHtml(src)}" data-duration="${Number(duration)||0}"><button type="button" class="compact-audio-play" aria-label="Play track">▶</button><span class="compact-audio-time">0:00 / ${clock(duration)}</span>${seekable?'<input class="compact-audio-seek" type="range" min="0" max="1000" value="0" aria-label="Seek through track">':''}<button type="button" class="compact-audio-volume" aria-label="Mute track">🔊</button></div>`;
}

function renderCompactAudio(player=compactAudioOwner) {
  if (!player?.isConnected) return;
  const duration=Number.isFinite(compactAudioEngine.duration)?compactAudioEngine.duration:Number(player.dataset.duration||0);
  const time=player.querySelector('.compact-audio-time');
  const seek=player.querySelector('.compact-audio-seek');
  time.textContent=`${clock(compactAudioEngine.currentTime||0)} / ${clock(duration)}`;
  if(seek&&!seek.matches(':active'))seek.value=duration?String(Math.round((compactAudioEngine.currentTime||0)/duration*1000)):'0';
}

export function stopCompactAudio() {
  compactAudioEngine.pause();
  compactAudioEngine.currentTime=0;
  if(compactAudioOwner?.isConnected){
    const play=compactAudioOwner.querySelector('.compact-audio-play');
    if(play){play.textContent='▶';play.setAttribute('aria-label','Play track');}
    renderCompactAudio(compactAudioOwner);
  }
  compactAudioOwner=null;
}

export function compactAudioIsWithin(selector) {
  return Boolean(compactAudioOwner?.closest(selector));
}

export function stopNativeAudio(except = null, scope = document) {
  scope.querySelectorAll('audio,video').forEach(media => {
    if (media !== except && !media.paused) media.pause();
  });
}

export function closeDownloadedInspector({restoreFocus=false} = {}) {
  const inspector=$('#downloaded-inspector');
  if (!inspector || inspector.hidden) return;
  stopNativeAudio(null, inspector);
  inspector.hidden=true;
  if (restoreFocus) document.querySelector(`.downloaded-card[data-id="${inspector.dataset.returnId}"]`)?.focus();
}

export function bindCompactAudio(scope = document) {
  scope.querySelectorAll('.compact-audio').forEach(player => {
    if (player.dataset.bound === 'true') return;
    player.dataset.bound = 'true';
    const play=player.querySelector('.compact-audio-play');
    const volume=player.querySelector('.compact-audio-volume');
    const seek=player.querySelector('.compact-audio-seek');
    const activate=()=>{
      if(compactAudioOwner===player)return;
      if(compactAudioOwner?.isConnected){
        const oldPlay=compactAudioOwner.querySelector('.compact-audio-play');
        if(oldPlay){oldPlay.textContent='▶';oldPlay.setAttribute('aria-label','Play track');}
      }
      compactAudioEngine.pause();
      compactAudioOwner=player;
      compactAudioEngine.src=player.dataset.src;
      compactAudioEngine.load();
    };
    play.onclick=async event=>{
      event.stopPropagation();
      const wasOwner=compactAudioOwner===player;
      activate();
      if(!wasOwner||compactAudioEngine.paused){
        stopNativeAudio();
        try{await compactAudioEngine.play();}catch(_){play.textContent='▶';}
      }else compactAudioEngine.pause();
    };
    volume.onclick=event=>{
      event.stopPropagation();
      activate();
      compactAudioEngine.muted=!compactAudioEngine.muted;
      volume.textContent=compactAudioEngine.muted?'🔇':'🔊';
      volume.setAttribute('aria-label',compactAudioEngine.muted?'Unmute track':'Mute track');
    };
    if(seek){
      seek.onpointerdown=event=>event.stopPropagation();
      seek.onclick=event=>event.stopPropagation();
      seek.oninput=event=>{
        event.stopPropagation();
        activate();
        const duration=Number.isFinite(compactAudioEngine.duration)?compactAudioEngine.duration:Number(player.dataset.duration||0);
        if(duration)compactAudioEngine.currentTime=Number(seek.value)/1000*duration;
        renderCompactAudio(player);
      };
    }
  });
}

compactAudioEngine.addEventListener('play',()=>{
  const play=compactAudioOwner?.querySelector('.compact-audio-play');
  if(play){play.textContent='❚❚';play.setAttribute('aria-label','Pause track');}
});
compactAudioEngine.addEventListener('pause',()=>{
  const play=compactAudioOwner?.querySelector('.compact-audio-play');
  if(play){play.textContent='▶';play.setAttribute('aria-label','Play track');}
});
compactAudioEngine.addEventListener('ended',()=>{compactAudioEngine.currentTime=0;renderCompactAudio();});
compactAudioEngine.addEventListener('loadedmetadata',()=>renderCompactAudio());
compactAudioEngine.addEventListener('timeupdate',()=>renderCompactAudio());
