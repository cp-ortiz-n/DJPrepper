export const SET_STORAGE_KEY = 'dj-library-studio-sets-v1';
export const SET_PROPOSAL_STRATEGIES = [
  {id:'safe',label:'Safe Flow',summary:'Smooth, dependable transitions',detail:'Prioritizes tempo, harmony, vocal space, and consistent mixability.'},
  {id:'journey',label:'Energy Journey',summary:'A deliberate rise, peak, and release',detail:'Follows the requested energy curve while preserving workable transitions.'},
  {id:'adventurous',label:'Adventurous Mix',summary:'Bolder contrasts and less obvious choices',detail:'Rewards variety, genre movement, and surprising but defensible transitions.'},
];

export function createSetBuilderState() {
  return {
    library:[], plan:[], requiredIds:new Set(), excludedIds:new Set(), lockedIds:new Set(),
    bound:false, genreSelectionOrder:[], generationNonce:0, proposals:[], activeProposal:'',
    history:[], future:[], compactMode:localStorage.getItem('set-builder-compact') === 'true',
    transitionSettings:{},
  };
}

export function setTrackId(track) { return String(track.source_name || '').toLowerCase(); }
export function trackMatchesSetGenre(track, genre) { return track._genre===genre || track._genre.startsWith(`${genre} / `); }
export function setTrackDetailedGenres(track) { return String(track._detailedGenre||'').split(',').map(value=>value.trim()).filter(Boolean); }
export function trackMatchesSetDetailedGenre(track, genre) {
  return setTrackDetailedGenres(track).some(value=>value.toLowerCase()===String(genre||'').toLowerCase());
}

export function targetSetEnergy(index, count, brief) {
  const progress = count <= 1 ? 0 : index / (count - 1);
  const base = {balanced:.5,'dance-party':.7,'warm-up':.32,'peak-time':.78,melodic:.52,'vocal-safe':.48,ambient:.24,closing:.55}[brief.vibe] ?? .5;
  if (brief.curve === 'rise') return Math.min(.92, base - .12 + progress * .45);
  if (brief.curve === 'peak-release') return progress < .72 ? Math.min(.92, base - .12 + progress * .62) : Math.max(.35, .92 - (progress - .72) * 1.45);
  if (brief.curve === 'waves') return Math.max(.2, Math.min(.92, base + Math.sin(progress * Math.PI * 4 - Math.PI / 2) * .22 + progress * .12));
  return base;
}
