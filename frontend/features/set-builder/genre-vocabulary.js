/** Build and query genre vocabulary from the catalog instead of source-code aliases. */

export function normalizeGenre(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/[^a-z0-9&]+/g, ' ')
    .trim()
    .replace(/\s+/g, ' ');
}

export function normalizeGenreVocabulary(vocabulary = []) {
  const merged = new Map();
  for (const value of vocabulary || []) {
    const structured = value && typeof value === 'object' && !Array.isArray(value);
    const canonical = normalizeGenre(structured ? value.canonical : value);
    if (!canonical) continue;
    const current = merged.get(canonical) || { canonical, aliases: new Set(), count: 0 };
    current.aliases.add(canonical);
    if (structured) {
      for (const alias of value.aliases || []) {
        const normalized = normalizeGenre(alias);
        if (normalized) current.aliases.add(normalized);
      }
      current.count += Math.max(0, Number(value.count || 0));
    }
    merged.set(canonical, current);
  }
  return [...merged.values()]
    .sort((left, right) => right.count - left.count || left.canonical.localeCompare(right.canonical))
    .map((entry) => ({
      canonical: entry.canonical,
      aliases: [...entry.aliases].sort((left, right) => right.length - left.length || left.localeCompare(right)),
      count: entry.count,
    }));
}

/** Return displayable canonical names from either structured or legacy vocabulary. */
export function canonicalGenreNames(vocabulary = []) {
  return normalizeGenreVocabulary(vocabulary).map((entry) => entry.canonical);
}

function canonicalAliasAffinity(canonical, alias) {
  return phraseOccurrences(canonical, alias).length > 0 ? 1 : 0;
}

/** Derive canonical genres, aliases, and prevalence from catalog track relationships. */
export function createCatalogGenreVocabulary(tracks = []) {
  const entries = new Map();
  const add = (canonicalValue, aliases = []) => {
    const canonical = normalizeGenre(canonicalValue);
    if (!canonical || ['all', 'other', 'unknown', 'unclassified'].includes(canonical)) return;
    const current = entries.get(canonical) || { canonical, aliases: new Set(), count: 0 };
    current.aliases.add(canonical);
    aliases.map(normalizeGenre).filter(Boolean).forEach((alias) => current.aliases.add(alias));
    current.count += 1;
    entries.set(canonical, current);
  };
  for (const track of tracks || []) {
    const categoryParts = String(track?._genre || track?.genre || '')
      .split('/')
      .map((part) => part.trim())
      .filter(Boolean);
    const details = String(track?._detailedGenre || track?.detailed_genre || '')
      .split(',')
      .map((detail) => detail.trim())
      .filter(Boolean);
    const category = categoryParts.at(-1) || '';
    if (normalizeGenre(category) === 'other' && details.length) details.forEach((detail) => add(detail));
    else add(category, details);
  }
  return normalizeGenreVocabulary(
    [...entries.values()].map((entry) => ({
      canonical: entry.canonical,
      aliases: [...entry.aliases],
      count: entry.count,
    })),
  );
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

export function catalogGenreMentions(brief, vocabulary = [], excluded = new Set()) {
  const text = normalizeGenre(brief);
  const mentions = normalizeGenreVocabulary(vocabulary).flatMap((entry) =>
    excluded.has(entry.canonical)
      ? []
      : entry.aliases.flatMap((alias) =>
          phraseOccurrences(text, alias).map(([start, end]) => ({
            genre: entry.canonical,
            start,
            end,
            direct: alias === entry.canonical,
            affinity: canonicalAliasAffinity(entry.canonical, alias),
            count: entry.count,
          })),
        ),
  );
  const unambiguous = [
    ...mentions
      .reduce((bySpan, mention) => {
        const key = `${mention.start}:${mention.end}`;
        const current = bySpan.get(key);
        if (
          !current ||
          Number(mention.direct) > Number(current.direct) ||
          (mention.direct === current.direct && mention.affinity > current.affinity) ||
          (mention.direct === current.direct &&
            mention.affinity === current.affinity &&
            mention.count > current.count)
        )
          bySpan.set(key, mention);
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
