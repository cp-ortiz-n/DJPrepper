const NON_GENRE_TERMS = new Set([
  'ambient',
  'balanced',
  'closing',
  'dance party',
  'dark',
  'driving',
  'euphoric',
  'hypnotic',
  'industrial',
  'melodic',
  'peak time',
  'party ready',
  'warm up',
  'vocal safe',
]);

const GENRE_ALIASES = Object.freeze({
  'disco & funk': ['disco & funk', 'disco and funk', 'disco'],
  'r&b': ['r&b', 'rnb', 'rab', 'r and b', 'rhythm and blues'],
  'hip hop': ['hip hop', 'hiphop'],
});

function normalize(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/[^a-z0-9&]+/g, ' ')
    .trim()
    .replace(/\s+/g, ' ');
}

function unique(values) {
  return [...new Set((values || []).map(normalize).filter(Boolean))];
}

function phraseOccurrences(text, phrase) {
  const occurrences = [];
  let cursor = 0;
  while (cursor <= text.length - phrase.length) {
    const index = text.indexOf(phrase, cursor);
    if (index < 0) break;
    const before = index === 0 ? ' ' : text[index - 1];
    const after = index + phrase.length >= text.length ? ' ' : text[index + phrase.length];
    if (!/[a-z0-9&]/.test(before) && !/[a-z0-9&]/.test(after)) {
      occurrences.push([index, index + phrase.length]);
    }
    cursor = index + 1;
  }
  return occurrences;
}

/** Return explicit catalog genres while suppressing nested matches such as Techno inside Latin Techno. */
export function explicitGenreMentions(brief, vocabulary = []) {
  const text = normalize(brief);
  const candidates = unique([...Object.keys(GENRE_ALIASES), ...vocabulary]).filter(
    (genre) => !NON_GENRE_TERMS.has(genre),
  );
  const mentions = candidates.flatMap((genre) => {
    const aliases = GENRE_ALIASES[genre] || [genre];
    return aliases.flatMap((alias) =>
      phraseOccurrences(text, normalize(alias)).map(([start, end]) => ({
        genre,
        start,
        end,
        canonicalAlias: Object.hasOwn(GENRE_ALIASES, genre),
      })),
    );
  });
  const unambiguous = [
    ...mentions
      .reduce((bySpan, mention) => {
        const key = `${mention.start}:${mention.end}`,
          current = bySpan.get(key);
        if (!current || (mention.canonicalAlias && !current.canonicalAlias)) bySpan.set(key, mention);
        return bySpan;
      }, new Map())
      .values(),
  ];
  const unnested = unambiguous.filter(
    (mention) =>
      !unambiguous.some(
        (other) =>
          other.genre !== mention.genre &&
          other.start <= mention.start &&
          other.end >= mention.end &&
          other.end - other.start > mention.end - mention.start,
      ),
  );
  return [
    ...new Map(
      unnested
        .sort((left, right) => left.start - right.start || right.end - right.start - (left.end - left.start))
        .map((mention) => [mention.genre, mention.genre]),
    ).values(),
  ];
}

/** Treat the written brief—not model additions—as the authority for requested genres. */
export function reconcileInterpretedGenreAuthority(interpreted = {}, vocabulary = [], brief = '') {
  const source = String(brief || interpreted.text || '').trim();
  if (!source) return { ...interpreted };
  const candidates = unique([
    ...vocabulary,
    ...(interpreted.requestedGenres || []),
    ...(interpreted.optionalGenres || []),
    ...(interpreted.genreSequence || []),
  ]);
  const explicit = explicitGenreMentions(source, candidates);
  const requestedByModel = new Set(unique(interpreted.requestedGenres));
  const optionalByModel = new Set(unique(interpreted.optionalGenres));
  const optionalGenres = explicit.filter((genre) => optionalByModel.has(genre));
  const requestedGenres = explicit.filter((genre) => requestedByModel.has(genre) || !optionalByModel.has(genre));
  return {
    ...interpreted,
    requestedGenres,
    optionalGenres,
    genreSequence: [...explicit],
  };
}

export function journeyGenreAuthority(interpreted = {}) {
  const coreGenres = unique([...(interpreted.genreSequence || []), ...(interpreted.requestedGenres || [])]);
  const optionalGenres = unique(interpreted.optionalGenres).filter((genre) => !coreGenres.includes(genre));
  return { coreGenres, optionalGenres, allowedGenres: [...coreGenres, ...optionalGenres] };
}

/** Explain whether an editable journey remains inside its confirmed genre policy. */
export function reviewJourneyGenrePolicy(journey = {}, interpreted = {}) {
  const mode = journey.genrePolicy?.mode || (interpreted.drift === 'none' ? 'strict' : 'related');
  const authority = journeyGenreAuthority(interpreted);
  if (mode !== 'strict' || !authority.allowedGenres.length) {
    return { valid: true, mode, ...authority, violations: [], unapprovedGenres: [] };
  }
  const allowed = new Set(authority.allowedGenres);
  const violations = (journey.sections || [])
    .map((section, index) => ({
      id: section.id || `section-${index + 1}`,
      name: section.name || `Section ${index + 1}`,
      genres: unique(section.genres).filter((genre) => !allowed.has(genre)),
    }))
    .filter((violation) => violation.genres.length);
  return {
    valid: violations.length === 0,
    mode,
    ...authority,
    violations,
    unapprovedGenres: unique(violations.flatMap((violation) => violation.genres)),
  };
}

export function journeyConfirmationState({ sections = [], durationTotal = 0, mode = 'strict', interpreted = {} }) {
  const policyReview = reviewJourneyGenrePolicy({ genrePolicy: { mode }, sections }, interpreted);
  const emptySection = sections.find((section) => !unique(section.genres).length);
  const durationValid = Math.abs(Number(durationTotal) - 100) <= 0.01;
  const valid = durationValid && !emptySection && policyReview.valid;
  const reason = !durationValid
    ? 'Section durations must total 100%.'
    : emptySection
      ? `${emptySection.name} needs at least one genre.`
      : !policyReview.valid
        ? `Remove ${policyReview.unapprovedGenres.join(', ')} or enable Related genres.`
        : '';
  return { valid, reason, policyReview };
}

/** Repair an inbound AI/saved journey before it becomes an editable strict plan. */
export function repairJourneyGenrePolicy(journey = {}, interpreted = {}) {
  const source = typeof structuredClone === 'function' ? structuredClone(journey) : JSON.parse(JSON.stringify(journey));
  const review = reviewJourneyGenrePolicy(source, interpreted);
  source.genrePolicy = {
    ...(source.genrePolicy || {}),
    mode: review.mode,
    coreGenres: review.coreGenres,
    optionalGenres: review.optionalGenres,
    repairedSections: [],
  };
  if (review.mode !== 'strict' || !review.allowedGenres.length) return { journey: source, repairs: [] };
  const allowed = new Set(review.allowedGenres);
  const fallback = review.coreGenres.length ? review.coreGenres : review.optionalGenres;
  const sections = source.sections || [];
  sections.forEach((section, index) => {
    const proposed = unique(section.genres);
    const kept = proposed.filter((genre) => allowed.has(genre));
    const removed = proposed.filter((genre) => !allowed.has(genre));
    if (!kept.length && fallback.length) {
      const position = Math.min(
        fallback.length - 1,
        Math.floor((index * fallback.length) / Math.max(1, sections.length)),
      );
      kept.push(fallback[position]);
    }
    if (removed.length) {
      section.suggestedGenres = unique([...(section.suggestedGenres || []), ...removed]);
      source.genrePolicy.repairedSections.push(section.id || `section-${index + 1}`);
      section.purpose = `Develop the requested ${kept.join(', ')} direction at this energy level.`;
    }
    section.genres = kept;
  });
  return { journey: source, repairs: [...source.genrePolicy.repairedSections] };
}
