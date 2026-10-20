import { addLocalAudioFiles } from './import-workspace.js';
import { useFrontendServices } from '../../core/frontend-services.js';

function localImportFormData(files, playlistName) {
  const data = new FormData();
  files.forEach((file) => data.append('files', file, file.name));
  data.append('playlist_name', playlistName.trim() || 'Local Playlist');
  return data;
}

export function createLocalAudioImportFeature({
  services,
  importApi,
  runTask,
  stopTask,
  escapeHtml,
  showMusicFiles,
  clearWorkspaceFiles,
  loadMusicFiles,
}) {
  const { $ } = useFrontendServices(services);
  let files = [];

  function renderStagedFiles() {
    const root = $('#local-audio-staged');
    root.innerHTML = files.length
      ? `${files
          .slice(0, 20)
          .map(
            (file) =>
              `<div><strong>${escapeHtml(file.name)}</strong><span>${(file.size / 1024 / 1024).toFixed(1)} MB</span></div>`,
          )
          .join('')}${files.length > 20 ? `<span>+ ${files.length - 20} more tracks</span>` : ''}`
      : '<span>No files selected.</span>';
    $('#local-audio-import-submit').disabled = !files.length;
    $('#local-audio-import-message').textContent = files.length
      ? `${files.length} track${files.length === 1 ? '' : 's'} ready to convert.`
      : '';
  }

  function stage(incoming) {
    files = addLocalAudioFiles(files, incoming);
    renderStagedFiles();
  }

  function monitorLocalImport(batchId) {
    runTask({
      key: 'local-audio-import',
      load: () => importApi.localStatus(batchId),
      interval: 900,
      update: (state) => {
        const progress = $('#local-audio-import-progress');
        progress.hidden = false;
        progress.querySelector('span').style.width = `${Math.max(2, Number(state.progress || 0))}%`;
        progress.querySelector('small').textContent = `${state.stage} · ${Math.round(state.progress || 0)}%`;
      },
      complete: (state) => {
        const button = $('#local-audio-import-submit');
        const result = $('#local-audio-import-result');
        button.disabled = false;
        result.hidden = false;
        if (state.status !== 'complete') {
          result.innerHTML = `<strong>Import failed</strong><span>${escapeHtml(state.error || 'The local playlist could not be imported.')}</span>`;
          return;
        }
        const counts = state.counts || {};
        const genres = {};
        (state.results || [])
          .filter((item) => item.status === 'imported')
          .forEach((item) => {
            const genre = item.genre_category || 'Other';
            genres[genre] = (genres[genre] || 0) + 1;
          });
        result.innerHTML = `<strong>${escapeHtml(state.playlist_name)} imported</strong><span>${counts.imported || 0} converted · ${counts.duplicates || 0} duplicates skipped · ${counts.failed || 0} failed</span>${
          Object.keys(genres).length
            ? `<span>${escapeHtml(
                Object.entries(genres)
                  .map(([genre, count]) => `${genre} (${count})`)
                  .join(' · '),
              )}</span>`
            : ''
        }<button type="button" class="button secondary view-local-imports">Open Music Files</button>`;
        result.querySelector('.view-local-imports').onclick = showMusicFiles;
        files = [];
        renderStagedFiles();
        $('#local-audio-files').value = '';
        $('#local-audio-folder').value = '';
      },
      fail: (error) => {
        $('#local-audio-import-submit').disabled = false;
        $('#local-audio-import-message').textContent = error.message;
      },
    });
  }

  function monitorWorkspaceImport(batchId) {
    runTask({
      key: 'workspace-local-import',
      load: () => importApi.localStatus(batchId),
      interval: 900,
      update: (state) => {
        $('#upload-message').textContent = `${state.stage} · ${Math.round(state.progress || 0)}%`;
      },
      complete: async (state) => {
        const button = $('#workspace-import-submit');
        button.disabled = false;
        button.textContent = 'Convert and organize';
        if (state.status !== 'complete') {
          $('#upload-message').textContent = state.error || 'The local playlist import failed.';
          return;
        }
        const counts = state.counts || {};
        $('#upload-message').textContent =
          `${counts.imported || 0} WAV${counts.imported === 1 ? '' : 's'} imported · ${counts.duplicates || 0} duplicates skipped · ${counts.failed || 0} failed. Open Music Files to review them.`;
        clearWorkspaceFiles();
        await loadMusicFiles();
      },
      fail: (error) => {
        const button = $('#workspace-import-submit');
        button.disabled = false;
        button.textContent = 'Convert and organize';
        $('#upload-message').textContent = error.message;
      },
    });
  }

  async function start(filesToImport, playlistName, { workspace = false } = {}) {
    const button = $(workspace ? '#workspace-import-submit' : '#local-audio-import-submit');
    const message = $(workspace ? '#upload-message' : '#local-audio-import-message');
    const taskKey = workspace ? 'workspace-local-import' : 'local-audio-import';
    stopTask(taskKey);
    button.disabled = true;
    button.textContent = 'Uploading…';
    try {
      const payload = await importApi.startLocal(localImportFormData(filesToImport, playlistName));
      button.textContent = 'Convert and organize';
      message.textContent = `Converting ${payload.track_count} tracks from ${payload.playlist_name}…`;
      (workspace ? monitorWorkspaceImport : monitorLocalImport)(payload.batch_id);
    } catch (error) {
      button.disabled = false;
      button.textContent = 'Convert and organize';
      message.textContent = error.message;
    }
  }

  function bind() {
    $('#local-audio-files').addEventListener('change', (event) => stage(event.target.files));
    $('#local-audio-folder').addEventListener('change', (event) => {
      const incoming = [...event.target.files];
      const folder = incoming[0]?.webkitRelativePath?.split('/')[0];
      if (folder && $('#local-playlist-name').value === 'Local Playlist') $('#local-playlist-name').value = folder;
      stage(incoming);
    });
    $('#local-audio-import-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      if (files.length) await start(files, $('#local-playlist-name').value);
    });
  }

  return Object.freeze({
    bind,
    startWorkspace: (workspaceFiles, playlistName) => start(workspaceFiles, playlistName, { workspace: true }),
  });
}
