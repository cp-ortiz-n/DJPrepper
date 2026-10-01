export const LIBRARY_ROLE_INFO = {
  'warm-up':['Warm-up','Lower-pressure selections that build the room without spending peak energy too early.'],
  'peak-time':['Peak-time','High-impact tracks suited to the busiest, most energetic part of a set.'],
  closing:['Closing','Tracks with an ending, mood, or mix-out shape that can resolve a set.'],
  'vocal-safe':['Vocal-safe','More instrumental space, useful for layering without clashing with another vocal.'],
  melodic:['Melodic','Clear tonal or harmonic identity; key compatibility matters more when mixing these.'],
  ambient:['Ambient','Sparse or atmospheric material useful for openings, resets, and transitions.'],
  'live timing':['Live timing','Tempo may drift; ride the pitch or mix shorter instead of trusting a rigid beat grid.'],
};

const CAMELOT_KEYS = {
  'A minor':'8A','E minor':'9A','B minor':'10A','F# minor':'11A','C# minor':'12A','G# minor':'1A','D# minor':'2A','A# minor':'3A','F minor':'4A','C minor':'5A','G minor':'6A','D minor':'7A',
  'C major':'8B','G major':'9B','D major':'10B','A major':'11B','E major':'12B','B major':'1B','F# major':'2B','C# major':'3B','G# major':'4B','D# major':'5B','A# major':'6B','F major':'7B',
};

export function createLibraryUiState(pageSize = Number(localStorage.getItem('dj-library-page-size') || 50)) {
  return {search:'',role:'all',category:'all',detailedGenre:'all',preset:'all',sort:'newest',result:'all',quality:'all',bpmMin:'',bpmMax:'',key:'all',energy:'all',vocals:'all',timing:'all',page:1,pageSize};
}

export function libraryRoles(song) {
  if (Array.isArray(song._roles) && song._roles.length) return song._roles;
  const style = String(song.detected_style || '').toLowerCase();
  const timing = String(song.timing || '').toLowerCase();
  const bpm = Number(song.bpm || 0);
  const roles = new Set();
  if (style.includes('ambient') || style.includes('sparse')) roles.add('ambient');
  if (style.includes('melodic') || style.includes('harmonic') || Number(song.key_confidence || 0) >= .65) roles.add('melodic');
  if (style.includes('vocal-safe') || Math.max(song.intro?.instrumentalness || 0, song.outro?.instrumentalness || 0) >= .72) roles.add('vocal-safe');
  if (timing.includes('live') || timing.includes('variable') || Number(song.tempo_drift || 0) >= .08) roles.add('live timing');
  if (style.includes('peak') || style.includes('high-energy') || (bpm >= 122 && !roles.has('ambient'))) roles.add('peak-time');
  if (style.includes('slow') || style.includes('subtle') || bpm && bpm < 120 || roles.has('ambient')) roles.add('warm-up');
  if (style.includes('closing') || Number(song.dj_readiness?.outro_mixable_bars || 0) >= 8 || song.outro?.section === 'closing') roles.add('closing');
  if (!roles.size) roles.add(bpm >= 122 ? 'peak-time' : 'warm-up');
  return [...roles];
}

export function normalizedKey(value) {
  return String(value || '').replace(/^Db /,'C# ').replace(/^Eb /,'D# ').replace(/^Gb /,'F# ').replace(/^Ab /,'G# ').replace(/^Bb /,'A# ');
}
export function camelotKey(value) { return CAMELOT_KEYS[normalizedKey(value)] || '—'; }
export function libraryKeyMode() { return localStorage.getItem('audioextender-key-view') || 'both'; }
export function formatLibraryKey(value, mode=libraryKeyMode()) {
  const standard = value || 'Unknown key';
  const camelot = camelotKey(value);
  if (mode === 'standard') return standard;
  if (mode === 'camelot') return camelot === '—' ? 'Unknown Camelot' : camelot;
  return camelot === '—' ? standard : `${standard} · ${camelot}`;
}

export function songEnergy(song) {
  if (Number.isFinite(Number(song._energy))) return Number(song._energy);
  const values = (song.section_profiles || []).map(section => Number(String(section.reason || '').match(/energy\s+([\d.]+)/i)?.[1])).filter(Number.isFinite);
  if (values.length) return values.reduce((sum,value) => sum + value, 0) / values.length;
  const style = String(song.detected_style || '').toLowerCase();
  return style.includes('high-energy') || style.includes('peak') ? .8 : style.includes('ambient') || style.includes('sparse') ? .25 : .5;
}
export function energyBand(value) { return value >= .67 ? 'high' : value < .4 ? 'low' : 'medium'; }
export function vocalProfile(song) {
  if (song._vocals) return song._vocals;
  const instrumental = Math.max(Number(song.intro?.instrumentalness || 0), Number(song.outro?.instrumentalness || 0));
  return instrumental >= .72 ? 'vocal-safe' : instrumental < .45 ? 'vocal-forward' : 'mixed';
}
export function timingProfile(song) {
  if (song._timing) return song._timing;
  const timing = String(song.timing || '').toLowerCase();
  return timing.includes('live') || timing.includes('variable') || Number(song.tempo_drift || 0) >= .08 ? 'variable' : 'steady';
}
export function effectivePreset(song, job) {
  const analyzed = String(song.preset || '');
  const resolved = analyzed.includes('→') ? analyzed.split('→').at(-1).trim() : analyzed.trim();
  return String(resolved || job?.preset || 'default').toLowerCase();
}

export function harmonicCompatibility(left, right) {
  const notes = {C:0,'C#':1,Db:1,D:2,'D#':3,Eb:3,E:4,F:5,'F#':6,Gb:6,G:7,'G#':8,Ab:8,A:9,'A#':10,Bb:10,B:11};
  const parse = value => {
    const match = String(value || '').match(/^([A-G](?:#|b)?)\s+(major|minor)/i);
    return match ? {pitch:notes[match[1]], mode:match[2].toLowerCase()} : null;
  };
  const a = parse(left); const b = parse(right);
  if (!a || !b) return {score:10,label:'key unknown'};
  const distance = Math.min((a.pitch-b.pitch+12)%12,(b.pitch-a.pitch+12)%12);
  if (a.pitch === b.pitch && a.mode === b.mode) return {score:40,label:'same key'};
  if (a.mode !== b.mode && ((a.mode === 'minor' && (a.pitch+3)%12 === b.pitch) || (b.mode === 'minor' && (b.pitch+3)%12 === a.pitch))) return {score:36,label:'relative key'};
  if (distance === 5 && a.mode === b.mode) return {score:30,label:'neighboring key'};
  if (a.pitch === b.pitch) return {score:24,label:'parallel key'};
  return {score:0,label:'distant key'};
}

export function compatibility(left, right) {
  const bpmA = Number(left.bpm || 0); const bpmB = Number(right.bpm || 0);
  const ratios = [bpmB, bpmB / 2, bpmB * 2].filter(Boolean);
  const difference = bpmA ? Math.min(...ratios.map(value => Math.abs(value - bpmA) / bpmA)) : 1;
  const tempoScore = Math.max(0, 45 * (1 - difference / .08));
  const key = harmonicCompatibility(left.key, right.key);
  const keyScore = key.score * .875;
  const energyScore = Math.max(0, 10 * (1 - Math.abs(songEnergy(left) - songEnergy(right)) / .55));
  const sharedRoles = libraryRoles(left).filter(role => libraryRoles(right).includes(role));
  const roleScore = Math.min(10, sharedRoles.length * 5);
  return {score:Math.round(tempoScore + keyScore + energyScore + roleScore), difference, key:key.label, components:{tempo:Math.round(tempoScore),key:Math.round(keyScore),energy:Math.round(energyScore),role:Math.round(roleScore)}, sharedRoles};
}
