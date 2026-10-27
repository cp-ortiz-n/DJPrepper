import { SET_BRIEF_MODES } from './workflow.js';
import { canonicalGenreNames } from './genre-vocabulary.js';
import {
  journeyConfirmationState, journeyGenreAuthority,
  repairJourneyGenrePolicy, reviewJourneyGenrePolicy,
} from './journey-policy.js';

/** Owns editable journey rendering, strict genre review, and confirmation state. */
export function createSetJourneyReview({
  $,
  $$,
  workflow,
  escapeHtml,
  option,
  parseIdentityTerms,
  intentionVocabulary,
  durationMinutes,
  journeyDurationStatus,
  journeyEnergyRange,
  journeyEvidenceLabel,
}) {
  function interpreted() {
    try {
      return JSON.parse($('#set-intention-interpretation')?.dataset.interpretation || '{}');
    } catch (_) {
      return {};
    }
  }
  const coreGenres = () => journeyGenreAuthority(interpreted()).coreGenres;
  function syncBuildAvailability() {
    const root = $('#set-journey-preview'),
      button = $('#set-generate');
    if (!root || !button) return;
    const needsConfirmation =
      workflow.briefMode() === SET_BRIEF_MODES.AI && !root.hidden && root.dataset.confirmed !== 'true';
    if (needsConfirmation) {
      button.disabled = true;
      button.textContent = 'Confirm journey first';
    } else if (button.textContent === 'Confirm journey first') {
      button.disabled = false;
      workflow.syncPlanningMode();
    }
  }
  function setConfirmed(confirmed, message = '') {
    const root = $('#set-journey-preview'),
      badge = $('#set-journey-confirmation');
    if (!root || !badge) return;
    root.dataset.confirmed = String(Boolean(confirmed));
    badge.className = confirmed ? 'confirmed' : 'needs-review';
    badge.textContent = message || (confirmed ? 'Confirmed' : 'Needs confirmation');
    syncBuildAvailability();
  }
  function syncSectionSummary(row) {
    const genres = parseIdentityTerms(row.querySelector('.journey-genres input').value),
      start = row.querySelector('.journey-energy-start').value,
      end = row.querySelector('.journey-energy-end').value;
    row.querySelector('.journey-summary-name').textContent =
      row.querySelector('.journey-name').value || 'Untitled section';
    row.querySelector('.journey-summary-purpose').textContent =
      row.querySelector('.journey-purpose input').value || 'No purpose added';
    row.querySelector('.journey-summary-duration').textContent =
      `${row.querySelector('.journey-duration').value || 0}%`;
    row.querySelector('.journey-summary-energy').textContent = `${start} → ${end}`;
    row.querySelector('.journey-summary-genres').innerHTML = genres.length
      ? genres.map((genre) => `<span>${escapeHtml(genre)}</span>`).join('')
      : '<span class="empty">Add a genre</span>';
  }
  function syncRelatedStatus() {
    const enabled = $('#set-allow-related-genres').checked;
    $('#set-journey-related-status').textContent = enabled
      ? 'On · suggested bridges allowed'
      : 'Off · exact genres only';
  }
  function current() {
    const root = $('#set-journey-preview');
    if (!root || root.hidden) return null;
    const sections = [...root.querySelectorAll('.set-journey-section')].map((row, index) => ({
      id: row.dataset.id || `section-${index + 1}`,
      name: row.querySelector('.journey-name').value.trim() || `Section ${index + 1}`,
      durationPercent: Number(row.querySelector('.journey-duration').value || 0),
      energyStart: Number(row.querySelector('.journey-energy-start').value || 5),
      energyEnd: Number(row.querySelector('.journey-energy-end').value || 5),
      genres: parseIdentityTerms(row.querySelector('.journey-genres input').value),
      characteristics: parseIdentityTerms(row.querySelector('.journey-characteristics').value),
      purpose: row.querySelector('.journey-purpose input').value.trim(),
    }));
    const duration = journeyDurationStatus(sections, durationMinutes());
    if (!duration.valid)
      throw new Error(`Journey section durations total ${duration.total}%. Adjust them to 100% before generating.`);
    const authority = journeyGenreAuthority(interpreted());
    return {
      version: 1,
      summary: $('#set-journey-summary').textContent,
      durationMinutes: durationMinutes(),
      confirmed: root.dataset.confirmed === 'true',
      genrePolicy: {
        mode: $('#set-allow-related-genres').checked ? 'related' : 'strict',
        coreGenres: authority.coreGenres,
        openingGenres: authority.openingGenres,
        optionalGenres: authority.optionalGenres,
      },
      sections,
    };
  }
  function render(journey, { confirmed = journey.confirmed === true } = {}) {
    const policyRepair = repairJourneyGenrePolicy(journey, interpreted()),
      viewJourney = policyRepair.journey;
    const root = $('#set-journey-preview'),
      container = $('#set-journey-sections');
    root.hidden = false;
    root.dataset.journey = JSON.stringify(viewJourney);
    root.dataset.originalJourney = JSON.stringify(viewJourney);
    $('#set-journey-summary').textContent = viewJourney.summary || 'Review the planned journey before generating.';
    $('#set-journey-evidence').textContent = journeyEvidenceLabel(viewJourney);
    const core = coreGenres();
    $('#set-journey-core-genres').innerHTML = core.length
      ? core.map((genre) => `<span>${escapeHtml(genre)}</span>`).join('')
      : '<span>Use section genres</span>';
    if (viewJourney.genrePolicy?.mode)
      $('#set-allow-related-genres').checked = viewJourney.genrePolicy.mode === 'related';
    $('#set-journey-genre-options').replaceChildren(
      ...canonicalGenreNames(intentionVocabulary())
        .slice()
        .sort((left, right) => left.localeCompare(right))
        .map((genre) => option(genre, genre)),
    );
    container.innerHTML = (viewJourney.sections || [])
      .map((section, index) => {
        const [energyStart, energyEnd] = journeyEnergyRange(section);
        const suggestions = (section.suggestedGenres || [])
          .map(
            (genre) =>
              `<button type="button" data-suggested-genre="${escapeHtml(genre)}">+ ${escapeHtml(genre)}</button>`,
          )
          .join('');
        return `<details class="set-journey-section" data-id="${escapeHtml(section.id || `section-${index + 1}`)}"${viewJourney.sections.length === 1 ? ' open' : ''}><summary class="journey-section-summary"><span class="journey-step" aria-hidden="true">${index + 1}</span><span class="journey-summary-title"><strong class="journey-summary-name">${escapeHtml(section.name || `Section ${index + 1}`)}</strong><small class="journey-summary-purpose">${escapeHtml(section.purpose || 'No purpose added')}</small></span><span class="journey-summary-stat"><small>Duration</small><strong class="journey-summary-duration">${Number(section.durationPercent || 0)}%</strong></span><span class="journey-summary-stat"><small>Energy</small><strong class="journey-summary-energy">${energyStart} → ${energyEnd}</strong></span><span class="journey-summary-genres">${(section.genres || []).map((genre) => `<span>${escapeHtml(genre)}</span>`).join('')}</span><span class="journey-summary-edit">Edit</span></summary><div class="journey-editor"><div class="journey-primary"><label>Section<input class="journey-name" value="${escapeHtml(section.name || `Section ${index + 1}`)}"></label><label class="journey-duration-label">Duration<input class="journey-duration" type="number" min="1" max="100" step="1" value="${Number(section.durationPercent || 0)}"><span>%</span></label><label class="journey-energy">Energy <span class="journey-energy-value">${energyStart} → ${energyEnd}</span><span class="journey-energy-inputs"><input class="journey-energy-start" aria-label="Starting energy" type="number" min="1" max="10" step=".5" value="${energyStart}"><i aria-hidden="true">→</i><input class="journey-energy-end" aria-label="Ending energy" type="number" min="1" max="10" step=".5" value="${energyEnd}"></span></label></div><div class="journey-details"><div class="journey-genres"><label>Genres<input list="set-journey-genre-options" value="${escapeHtml((section.genres || []).join(', '))}" placeholder="Catalog genres, separated by commas"></label>${suggestions ? `<div class="journey-genre-suggestions"><small>Suggested, not applied</small>${suggestions}</div>` : ''}</div><label>Character<input class="journey-characteristics" value="${escapeHtml((section.characteristics || []).join(', '))}" placeholder="melodic, warm-up"></label><label class="journey-purpose">Purpose<input value="${escapeHtml(section.purpose || '')}"></label></div></div></details>`;
      })
      .join('');
    const refresh = () => {
      const total = [...container.querySelectorAll('.journey-duration')].reduce(
          (sum, input) => sum + Number(input.value || 0),
          0,
        ),
        status = $('#set-journey-total'),
        sections = [...container.querySelectorAll('.set-journey-section')].map((row, index) => ({
          id: row.dataset.id || `section-${index + 1}`,
          name: row.querySelector('.journey-name').value.trim() || `Section ${index + 1}`,
          genres: parseIdentityTerms(row.querySelector('.journey-genres input').value),
        })),
        validation = journeyConfirmationState({
          sections,
          durationTotal: total,
          mode: $('#set-allow-related-genres').checked ? 'related' : 'strict',
          interpreted: interpreted(),
        });
      status.textContent = `${viewJourney.sections.length} sections · ${total}% of ${durationMinutes()} minutes · ${validation.reason || 'edits drive track placement'}`;
      status.classList.toggle('invalid', !validation.valid);
      $('#set-journey-confirm').disabled = !validation.valid;
      $('#set-journey-confirm').title = validation.reason;
      container.querySelectorAll('.set-journey-section').forEach((row) => {
        const startInput = row.querySelector('.journey-energy-start'),
          endInput = row.querySelector('.journey-energy-end'),
          values = journeyEnergyRange({ energyStart: startInput.value, energyEnd: endInput.value });
        if (!String(endInput.value).trim() || !Number.isFinite(Number(endInput.value))) endInput.value = values[1];
        row.querySelector('.journey-energy-value').textContent = `${values[0]} → ${values[1]}`;
        syncSectionSummary(row);
      });
      return validation;
    };
    container.querySelectorAll('input').forEach((input) =>
      input.addEventListener('input', () => {
        const validation = refresh();
        setConfirmed(false, validation.valid ? 'Unconfirmed changes' : 'Needs correction');
        if (!validation.valid) $('#set-builder-message').textContent = validation.reason;
      }),
    );
    container.querySelectorAll('[data-suggested-genre]').forEach((button) => {
      button.onclick = () => {
        const row = button.closest('.set-journey-section'),
          input = row.querySelector('.journey-genres input'),
          genres = parseIdentityTerms(input.value);
        $('#set-allow-related-genres').checked = true;
        $('#set-intention-drift').value = 'moderate';
        input.value = [...new Set([...genres, button.dataset.suggestedGenre])].join(', ');
        button.remove();
        input.dispatchEvent(new Event('input', { bubbles: true }));
      };
    });
    const validation = refresh();
    syncRelatedStatus();
    setConfirmed(confirmed && validation.valid, validation.valid ? '' : 'Needs correction');
    if (policyRepair.repairs.length) {
      setConfirmed(false, 'Adjusted · review');
      $('#set-builder-message').textContent =
        `${policyRepair.repairs.length} section${policyRepair.repairs.length === 1 ? ' was' : 's were'} returned to your requested genres. Unrequested AI ideas remain available as suggestions.`;
    }
  }
  function bind({ onRegenerate }) {
    $('#set-journey-confirm').onclick = () => {
      try {
        const journey = current(),
          container = $('#set-journey-sections');
        const emptyIndex = journey.sections.findIndex((section) => !section.genres.length);
        if (emptyIndex >= 0) {
          container.children[emptyIndex].open = true;
          throw new Error('Every journey section needs at least one genre.');
        }
        if (!$('#set-allow-related-genres').checked) {
          const policyReview = reviewJourneyGenrePolicy(journey, interpreted());
          if (!policyReview.valid) {
            const invalidIndex = journey.sections.findIndex((section) =>
              section.genres.some((genre) => policyReview.unapprovedGenres.includes(genre)),
            );
            if (invalidIndex >= 0) container.children[invalidIndex].open = true;
            throw new Error(
              `Remove ${policyReview.unapprovedGenres.join(', ')} or turn on Allow related genres before confirming.`,
            );
          }
        }
        setConfirmed(true);
        $('#set-builder-message').textContent =
          'Journey confirmed. Track planning will use these exact sections, genres, durations, and energy targets.';
      } catch (error) {
        setConfirmed(false, 'Needs correction');
        $('#set-builder-message').textContent = error?.message || String(error);
      }
    };
    $('#set-journey-apply-core').onclick = () => {
      const core = coreGenres();
      if (!core.length) {
        $('#set-builder-message').textContent = 'No core genre was found in the interpreted brief.';
        return;
      }
      $$('.journey-genres input').forEach((input) => {
        input.value = core.join(', ');
        input.dispatchEvent(new Event('input', { bubbles: true }));
      });
      $('#set-builder-message').textContent = `Applied ${core.join(', ')} to every journey section.`;
    };
    $('#set-journey-reset').onclick = () => {
      const root = $('#set-journey-preview');
      try {
        render(JSON.parse(root.dataset.originalJourney || root.dataset.journey || '{}'));
        $('#set-builder-message').textContent = 'Journey edits reset. Review and confirm the restored direction.';
      } catch (_) {
        $('#set-builder-message').textContent = 'The original journey could not be restored. Regenerate it instead.';
      }
    };
    $('#set-journey-regenerate').onclick = onRegenerate;
    $('#set-allow-related-genres').onchange = (event) => {
      $('#set-intention-drift').value = event.currentTarget.checked ? 'moderate' : 'none';
      if (!event.currentTarget.checked) {
        try {
          render(current(), { confirmed: false });
        } catch (_) {}
      }
      syncRelatedStatus();
      setConfirmed(false, 'Unconfirmed changes');
      $('#set-builder-message').textContent = event.currentTarget.checked
        ? 'Related genres may now be added deliberately. Suggested genres remain unselected.'
        : 'Genre expansion is off. Only requested and optional genres can be confirmed.';
    };
    $('#set-intention-drift').onchange = (event) => {
      $('#set-allow-related-genres').checked = event.currentTarget.value !== 'none';
      syncRelatedStatus();
      if (!$('#set-journey-preview').hidden) setConfirmed(false, 'Unconfirmed changes');
    };
    $('#set-intention').addEventListener('input', () => {
      if (!$('#set-journey-preview').hidden) setConfirmed(false, 'Prompt changed · review again');
    });
  }

  return Object.freeze({ bind, current, render, setConfirmed, syncBuildAvailability });
}
