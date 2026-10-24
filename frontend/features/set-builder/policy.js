import { explicitGenreMentions } from './journey-policy.js';

export const SET_STORAGE_KEY = 'dj-library-studio-sets-v1';
export const SET_STORAGE_MIGRATION_KEY = 'dj-library-studio-sets-migrated-v2';
export const SET_IDENTITY_STORAGE_KEY = 'dj-library-track-identities-v1';
export const DEFAULT_SET_FALLBACK_POLICY = [
  'Direct genre and identity matches',
  'Requested foundation with matching vocals, rhythm, samples, or cultural identity',
  'Adjacent genres with compatible energy and structure',
  'Neutral bridge tracks that preserve the progression',
  'Pure foundation tracks only when needed for flow and runtime',
];
export { deduplicateSetRecordings, setCatalogTrackId, setRecordingKey, setTrackId } from './recording-identity.js';

export function trackMatchesSetGenre(track, genre) {
  return track._genre === genre || track._genre.startsWith(`${genre} / `);
}

export function setTrackDetailedGenres(track) {
  return String(track._detailedGenre || '')
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean);
}

export function trackMatchesSetDetailedGenre(track, genre) {
  return setTrackDetailedGenres(track).some((value) => value.toLowerCase() === String(genre || '').toLowerCase());
}

export function targetSetEnergy(index, count, brief) {
  const progress = count <= 1 ? 0 : index / (count - 1);
  const journeySections = brief?.identity?.journey?.sections || [];
  if (journeySections.length) {
    let elapsed = 0;
    const percentage = ((Math.max(0, index) + 0.5) / Math.max(1, count)) * 100;
    for (const section of journeySections) {
      const width = Math.max(1, Number(section.durationPercent || 0));
      const end = elapsed + width;
      if (percentage <= end) {
        const local = Math.max(0, Math.min(1, (percentage - elapsed) / width));
        const start = Math.max(1, Math.min(10, Number(section.energyStart || 5))) / 10;
        const endEnergy = Math.max(1, Math.min(10, Number(section.energyEnd || 5))) / 10;
        return start + (endEnergy - start) * local;
      }
      elapsed = end;
    }
  }
  const base =
    {
      balanced: 0.5,
      'dance-party': 0.7,
      'warm-up': 0.32,
      'peak-time': 0.78,
      melodic: 0.52,
      'vocal-safe': 0.48,
      ambient: 0.24,
      closing: 0.55,
    }[brief.vibe] ?? 0.5;
  if (brief.curve === 'rise') return Math.min(0.92, base - 0.12 + progress * 0.45);
  if (brief.curve === 'peak-release')
    return progress < 0.72
      ? Math.min(0.92, base - 0.12 + progress * 0.62)
      : Math.max(0.35, 0.92 - (progress - 0.72) * 1.45);
  if (brief.curve === 'waves')
    return Math.max(
      0.2,
      Math.min(0.92, base + Math.sin(progress * Math.PI * 4 - Math.PI / 2) * 0.22 + progress * 0.12),
    );
  return base;
}

export function genreAllocationTargets(genres, weights, count) {
  const selected = [...(genres || [])];
  if (!selected.length) return {};
  const normalized = selected.map((genre, index) => ({
    genre,
    index,
    weight: Math.max(0, Number(weights?.[genre] || 0)),
  }));
  let total = normalized.reduce((sum, item) => sum + item.weight, 0);
  if (!total) {
    normalized.forEach((item) => {
      item.weight = 1;
    });
    total = normalized.length;
  }
  const rows = normalized.map((item) => {
    const exact = (item.weight / total) * Math.max(0, count);
    return { ...item, exact, target: Math.floor(exact), fraction: exact - Math.floor(exact) };
  });
  let remaining = Math.max(0, count - rows.reduce((sum, item) => sum + item.target, 0));
  [...rows]
    .sort((left, right) => right.fraction - left.fraction || left.index - right.index)
    .forEach((item) => {
      if (remaining > 0) {
        item.target += 1;
        remaining -= 1;
      }
    });
  return Object.fromEntries(rows.map((item) => [item.genre, item.target]));
}

export function parseIdentityTerms(value) {
  return [
    ...new Set(
      String(value || '')
        .split(',')
        .map((term) => term.trim().toLowerCase())
        .filter(Boolean),
    ),
  ];
}

function normalizedIntentPhrase(value) {
  return ` ${String(value || '')
    .toLowerCase()
    .replaceAll('&', ' and ')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
    .replace(/\s+/g, ' ')} `;
}

function trackGenreSearchText(track) {
  return normalizedIntentPhrase(
    `${track?._genre || track?.genre || ''} ${track?._detailedGenre || track?.detailed_genre || ''}`,
  ).trim();
}

export function trackMatchesIntendedGenre(track, term) {
  const wanted = normalizedIntentPhrase(term).trim();
  const metadata = trackGenreSearchText(track);
  if (!wanted) return false;
  if (metadata.includes(wanted)) return true;
  return inferredTrackIdentity(track, track?._manualIdentity || []).some(
    (tag) => normalizedIntentPhrase(tag).trim() === wanted,
  );
}

export function interpretSetIntention(value, catalogVocabulary = []) {
  const text = String(value || '').trim();
  const lower = text.toLowerCase();
  const preferred = [];
  const required = [];
  const avoided = [];
  const rules = [
    [/ecuador|ecuadorian/, 'ecuadorian party'],
    [/colombia|colombian/, 'colombian'],
    [/caribbean/, 'caribbean'],
    [/andean/, 'andean'],
    [/spanish[- ]?(?:language )?vocal|vocals? in spanish|español/, 'spanish vocals'],
    [/dembow/, 'dembow'],
    [/latin percussion|latin rhythm/, 'latin percussion'],
    [/guaracha/, 'guaracha'],
    [/cumbia/, 'cumbia'],
    [/reggaeton|perreo/, 'reggaeton'],
    [/tribal/, 'tribal'],
    [/techno/, 'techno foundation'],
    [/(?:r\s*&\s*b|rnb|rhythm and blues|\brab\b)/, 'r&b'],
    [/(?:hip[- ]?hop)/, 'hip hop'],
    [/(?:^|\W)rap(?:\W|$)/, 'rap'],
    [/(?:chill|kickback|laid[- ]?back|low[- ]?key)/, 'chill kickback'],
    [/(?:party|danc(?:e|ing))/, 'dance-friendly'],
    [/recognizable|familiar|singalong|classic/, 'recognizable material'],
    [/peak[- ]?time|high energy|driving/, 'peak-time energy'],
    [/dark/, 'dark'],
    [/industrial/, 'industrial'],
    [/melodic/, 'melodic'],
    [/hypnotic/, 'hypnotic'],
    [/euphoric/, 'euphoric'],
  ];
  rules.forEach(([pattern, term]) => {
    if (pattern.test(lower)) preferred.push(term);
  });
  if (/(?:must|required|require)[^.]*spanish/.test(lower)) required.push('spanish vocals');
  if (/(?:must|required|require)[^.]*(?:latin percussion|dembow|latin rhythm)/.test(lower))
    required.push('latin rhythmic identity');
  if (/avoid[^.]*(?:generic|instrumental)[^.]*techno|limit[^.]*generic[^.]*techno/.test(lower))
    avoided.push('generic instrumental techno');
  const drift = /do not drift|no genre drift|strict genre/.test(lower)
    ? 'none'
    : /small|slight|close genres only/.test(lower)
      ? 'low'
      : /wide|open genre|context over genre/.test(lower)
        ? 'wide'
        : /allow related genres|allow genre bridges|musical bridges|genre bridges|genre drift|allow[^.]{0,60}bridges/.test(
              lower,
            )
          ? 'moderate'
          : 'none';
  const chill = /(?:chill|kickback|laid[- ]?back|low[- ]?key)/.test(lower);
  const dance = /(?:party|danc(?:e|ing))/.test(lower);
  const vibe =
    chill && dance
      ? 'balanced'
      : /warm[- ]?up/.test(lower)
        ? 'warm-up'
        : dance
          ? 'dance-party'
          : chill
            ? 'warm-up'
            : null;
  const curve = /varying waves|energy waves|wave(?:s|d)? of energy/.test(lower) ? 'waves' : null;
  const opening = /(?:start|open|begin)[^.]{0,80}melodic|melodic[^.]{0,40}(?:start|opening|beginning)/.test(lower)
    ? 'melodic'
    : null;
  const orderedGenres = explicitGenreMentions(text, catalogVocabulary);
  return {
    text,
    required: parseIdentityTerms(required.join(',')),
    preferred: parseIdentityTerms(preferred.join(',')),
    avoided: parseIdentityTerms(avoided.join(',')),
    requestedGenres: [...orderedGenres],
    genreSequence: orderedGenres,
    drift,
    vibe,
    curve,
    opening,
    fallbackPolicy: [...DEFAULT_SET_FALLBACK_POLICY],
  };
}

export function intendedGenreForPosition(identity, index, count) {
  const sections = identity?.journey?.sections || [];
  if (sections.length) {
    const progress = ((Math.max(0, index) + 0.5) / Math.max(1, count)) * 100;
    let elapsed = 0;
    for (const section of sections) {
      elapsed += Math.max(0, Number(section.durationPercent || 0));
      if (progress <= elapsed) return (section.genres || [])[0] || '';
    }
    return sections.at(-1)?.genres?.[0] || '';
  }
  const sequence = [...new Set(identity?.genreSequence || [])].filter(Boolean);
  if (!sequence.length) return '';
  const progress = (Math.max(0, index) + 0.5) / Math.max(1, count);
  return sequence[Math.min(sequence.length - 1, Math.floor(progress * sequence.length))];
}

export function inferredTrackIdentity(track, manual = []) {
  const source =
    `${track.source_name || ''} ${track.title || ''} ${track.artist || ''} ${track._genre || track.genre || ''} ${track._detailedGenre || track.detailed_genre || ''}`.toLowerCase();
  const tags = [...manual.map((value) => String(value).toLowerCase())];
  const add = (term, pattern) => {
    if (pattern.test(source)) tags.push(term);
  };
  add('latin identity', /latin|reggaeton|dembow|cumbia|salsa|bachata|guaracha|merengue|perreo/);
  add('techno foundation', /techno/);
  add('house foundation', /house/);
  add('spanish vocals', /spanish|español|vocal latino|reggaeton|salsa|bachata/);
  add('dembow', /dembow|reggaeton|perreo/);
  add('latin percussion', /latin|salsa|cumbia|guaracha|tribal/);
  add('ecuadorian party', /ecuador|ecuadorian/);
  add('colombian', /colombia|colombian|cumbia/);
  add('caribbean', /caribbean|reggaeton|salsa|dembow/);
  add('andean', /andean/);
  add('recognizable material', /remix|edit|bootleg|mashup|classic|anthem/);
  add('dark', /dark/);
  add('industrial', /industrial/);
  add('melodic', /melodic/);
  add('hypnotic', /hypnotic/);
  add('euphoric', /euphoric|anthem/);
  add('r&b', /(?:r\s*&\s*b|rnb|rhythm and blues)/);
  add('hip hop', /hip[- ]?hop/);
  add('rap', /(?:^|\W)rap(?:\W|$)/);
  add('chill kickback', /chill|downtempo|lounge|warm-up|laid[- ]?back/);
  return [...new Set(tags)];
}
