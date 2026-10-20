import { LIBRARY_ROLE_INFO, compatibility, formatLibraryKey, libraryRoles } from './model.js';

export function createDjLibraryIntelligence({ $, option, escapeHtml, revealTrack }) {
  function render(songs, latestByName) {
    const roleNames = ['warm-up', 'peak-time', 'closing', 'vocal-safe', 'melodic', 'ambient', 'live timing'];
    const groups = Object.fromEntries(roleNames.map((role) => [role, []]));
    songs.forEach((song) => libraryRoles(song).forEach((role) => groups[role].push(song)));
    $('#role-groups').innerHTML = roleNames
      .map((role) => {
        const [label, description] = LIBRARY_ROLE_INFO[role];
        return `<details class="role-card"><summary><strong>${groups[role].length}</strong><span>${label}</span><small>${escapeHtml(description)}</small></summary><div>${groups[role].length ? groups[role].map((song) => `<button type="button" data-job-id="${latestByName.get(song.source_name.toLowerCase())?.id || ''}" data-source-name="${escapeHtml(song.source_name)}">${escapeHtml(song.source_name.replace(/\.[^.]+$/, ''))}<span>${Number(song.bpm || 0).toFixed(1)} BPM · ${escapeHtml(formatLibraryKey(song.key))}</span></button>`).join('') : '<p>No matching tracks yet.</p>'}<button type="button" class="role-filter" data-role="${role}">Filter DJ Library to ${label}</button></div></details>`;
      })
      .join('');
    $('#role-groups')
      .querySelectorAll('[data-job-id]')
      .forEach((button) => (button.onclick = () => revealTrack(button.dataset.jobId, button.dataset.sourceName)));
    $('#role-groups')
      .querySelectorAll('.role-filter')
      .forEach((button) => {
        button.onclick = () => {
          $('#library-role').value = button.dataset.role;
          $('#library-role').dispatchEvent(new Event('change'));
          document.querySelector('.library-toolbar')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        };
      });

    const select = $('#compatibility-source');
    const previous = select.value;
    select.replaceChildren(
      option('', 'Choose a track'),
      ...songs
        .sort((a, b) => a.source_name.localeCompare(b.source_name))
        .map((song) => option(song.source_name, song.source_name.replace(/\.[^.]+$/, ''))),
    );
    if (songs.some((song) => song.source_name === previous)) select.value = previous;
    const show = () => {
      const source = songs.find((song) => song.source_name === select.value);
      if (!source) {
        $('#compatible-tracks').innerHTML = '<p>Select a track to see BPM and key-compatible suggestions.</p>';
        return;
      }
      const matches = songs
        .filter((song) => song !== source)
        .map((song) => ({ song, ...compatibility(source, song) }))
        .filter((match) => match.score >= 40)
        .sort((a, b) => b.score - a.score)
        .slice(0, 8);
      $('#compatible-tracks').innerHTML = matches.length
        ? `<div class="compatibility-title"><div><strong>Mix suggestions for ${escapeHtml(source.source_name)}</strong><span>${Number(source.bpm || 0).toFixed(1)} BPM · ${escapeHtml(formatLibraryKey(source.key))}</span></div><p><b>How the score works:</b> tempo 45% · harmonic key 35% · energy 10% · shared role 10%. Treat it as a shortlist, then listen before mixing.</p></div>${matches.map((match) => `<button type="button" data-job-id="${latestByName.get(match.song.source_name.toLowerCase())?.id || ''}" data-source-name="${escapeHtml(match.song.source_name)}"><strong>${escapeHtml(match.song.source_name.replace(/\.[^.]+$/, ''))}</strong><span>${match.score}% match · ${Number(match.song.bpm || 0).toFixed(1)} BPM · ${escapeHtml(formatLibraryKey(match.song.key))}</span><small>${match.difference <= 0.02 ? 'tempo locked' : `${(match.difference * 100).toFixed(1)}% tempo move`} · ${match.key}</small><em>Tempo ${match.components.tempo}/45 · Key ${match.components.key}/35 · Energy ${match.components.energy}/10 · Role ${match.components.role}/10</em></button>`).join('')}`
        : '<p>No strong matches are available yet. Try another source track or relax the Library filters.</p>';
      $('#compatible-tracks')
        .querySelectorAll('button')
        .forEach((button) => (button.onclick = () => revealTrack(button.dataset.jobId, button.dataset.sourceName)));
    };
    select.onchange = show;
    show();
  }

  return Object.freeze({ render });
}
