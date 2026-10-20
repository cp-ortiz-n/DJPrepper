import { useFrontendServices } from './frontend-services.js';

export function createDjLibrarySelection({
  services,
  loadLibrary,
  loadDownloadedLibrary,
  loadAnalysis,
  loadReports,
  loadJobs,
  showView,
  startKeyAnalysis,
  setLoadedAt,
  invalidateMusicFiles,
  documentRoot = globalThis.document,
  urlApi = globalThis.URL,
  alertUser = globalThis.alert,
  defer = globalThis.setTimeout,
}) {
  const {
    api,
    $,
    notify,
    confirmAction,
    operationReceiptText,
    openDescriptorEditorDialog,
    saveDescriptorEditor,
    inferDescriptorEditor,
  } = useFrontendServices(services);
  let visibleTracks = [];

  const setVisibleTracks = (tracks) => {
    visibleTracks = [...tracks];
  };

  const bindIdentityInference = (editor, trackIds, onApplied = async () => {}) => {
    editor.querySelector('.infer-descriptors').onclick = async (event) => {
      const action = event.currentTarget;
      const original = action.textContent;
      action.disabled = true;
      action.textContent = 'Inferring…';
      try {
        const result = await inferDescriptorEditor(editor, typeof trackIds === 'function' ? trackIds() : trackIds);
        if (result.applied) {
          notify(`Added inferred identity tags to ${result.applied} tracks. Manual tags were preserved.`, 'success');
          await onApplied(result);
        }
      } catch (error) {
        notify(error.message, 'danger');
      } finally {
        action.disabled = false;
        action.textContent = original;
      }
    };
  };

  const bindIdentityProtection = (editor, track) => {
    const input = editor.querySelector('.descriptor-inference-protection input');
    if (!input || !track) return;
    input.checked = Boolean(track.identity_inference_locked);
    input.onchange = async () => {
      const wanted = input.checked;
      input.disabled = true;
      try {
        const response = await api.raw(`/api/downloaded-library/tracks/${Number(track.id)}/inference-protection`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ protected: wanted }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(api.errorMessage(result, 'Inference protection could not be saved.'));
        track.identity_inference_locked = Boolean(result.protected_from_inference);
        input.checked = track.identity_inference_locked;
        notify(
          `${track.title || 'Track'}: ${input.checked ? 'protected from automatic inference' : 'eligible for re-inference'}. Survives restart: Yes.`,
          'success',
        );
      } catch (error) {
        input.checked = !wanted;
        notify(error.message, 'danger');
      } finally {
        input.disabled = false;
      }
    };
  };

  function bind() {
    const boxes = [...documentRoot.querySelectorAll('.library-track-select input:not(:disabled)')];
    const typeBoxes = [...documentRoot.querySelectorAll('.library-export-options input')];
    const all = $('#library-select-all');
    const button = $('#library-download-selected');
    const count = $('#library-selection-count');
    const genreInput = $('#library-genre-value');
    const genreButton = $('#library-change-genre');
    const identityButton = $('#library-edit-identity');
    const removeButton = $('#library-remove-selected');
    const reanalyzeButton = $('#library-reanalyze-selected');
    const keyAnalyzeButton = $('#library-key-analyze-selected');

    const selectedCards = () => boxes.filter((box) => box.checked).map((box) => box.closest('.library-card'));
    const selectedTrackIds = () =>
      selectedCards()
        .map((card) => Number(card.dataset.downloadedId))
        .filter(Boolean);
    const refresh = () => {
      const selected = boxes.filter((box) => box.checked).length;
      const fileTypes = typeBoxes.filter((box) => box.checked).length;
      const catalogSelected = boxes.filter(
        (box) => box.checked && box.closest('.library-card').dataset.downloadedId,
      ).length;
      count.textContent = `${selected} selected`;
      button.disabled = selected === 0 || fileTypes === 0;
      genreButton.disabled = selected === 0 || catalogSelected !== selected || !genreInput.value.trim();
      identityButton.disabled = selected === 0 || catalogSelected !== selected;
      removeButton.disabled = selected === 0;
      reanalyzeButton.disabled = selected === 0 || catalogSelected !== selected;
      keyAnalyzeButton.disabled = selected === 0 || catalogSelected !== selected;
      documentRoot.querySelector('.library-selection').classList.toggle('has-selection', selected > 0);
      boxes.forEach((box) => box.closest('.library-card').classList.toggle('is-selected', box.checked));
      all.checked = boxes.length > 0 && selected === boxes.length;
      all.indeterminate = selected > 0 && selected < boxes.length;
    };

    all.onchange = () => {
      boxes
        .filter((box) => !box.closest('.library-card').hidden)
        .forEach((box) => {
          box.checked = all.checked;
        });
      refresh();
    };
    boxes.forEach((box) => (box.onchange = refresh));
    typeBoxes.forEach((box) => (box.onchange = refresh));
    genreInput.oninput = refresh;

    genreButton.onclick = async () => {
      const cards = selectedCards();
      const trackIds = selectedTrackIds();
      const genre = genreInput.value.trim();
      if (!trackIds.length || trackIds.length !== cards.length || !genre) return;
      if (
        !(await confirmAction(
          `Move ${trackIds.length} selected track${trackIds.length === 1 ? '' : 's'} to the ${genre} genre folder?`,
          { title: 'Change track genre', acceptLabel: 'Move tracks' },
        ))
      )
        return;
      genreButton.disabled = true;
      genreButton.textContent = 'Moving…';
      try {
        const response = await api.raw('/api/downloaded-library/genre', {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ track_ids: trackIds, genre_category: genre }),
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(api.errorMessage(payload, 'Could not change genre.'));
        notify(operationReceiptText(payload.receipt), payload.receipt?.failures?.length ? 'danger' : 'success', {
          timeout: 9000,
        });
        genreInput.value = '';
        await Promise.all([loadLibrary(), loadDownloadedLibrary()]);
      } catch (error) {
        alertUser(error.message);
      } finally {
        genreButton.textContent = 'Change genre';
      }
    };

    identityButton.onclick = () => {
      const cards = selectedCards();
      const trackIds = selectedTrackIds();
      if (!trackIds.length || trackIds.length !== cards.length) return;
      const single = trackIds.length === 1;
      const currentTrack = single ? visibleTracks.find((track) => Number(track.id) === trackIds[0]) : null;
      const selectedBoxIndex = single ? boxes.findIndex((box) => box.checked) : -1;
      const previousBox = selectedBoxIndex > 0 ? boxes[selectedBoxIndex - 1] : null;
      const nextBox = selectedBoxIndex >= 0 ? boxes[selectedBoxIndex + 1] : null;
      const { editor, close } = openDescriptorEditorDialog({
        descriptors: currentTrack?.descriptors || [],
        bulk: !single,
        protectedFromInference: single ? Boolean(currentTrack?.identity_inference_locked) : null,
        title: single
          ? `Edit identity · ${currentTrack?.title || 'Selected track'}`
          : 'Edit identity for selected tracks',
        subtitle: single
          ? `Track ${selectedBoxIndex + 1} of ${boxes.length} in the current filtered list.`
          : `Apply descriptors to ${trackIds.length} selected tracks.`,
      });
      if (single) bindIdentityProtection(editor, currentTrack);
      editor.querySelector('.cancel-descriptors').onclick = close;
      editor.querySelector('.close-descriptor-editor').onclick = close;
      const saveButton = editor.querySelector('.save-descriptors');
      let previousButton = null;
      let nextButton = null;
      if (single) {
        previousButton = documentRoot.createElement('button');
        previousButton.type = 'button';
        previousButton.className = 'button secondary save-previous-descriptors';
        previousButton.textContent = '← Save & previous';
        previousButton.disabled = !previousBox;
        nextButton = documentRoot.createElement('button');
        nextButton.type = 'button';
        nextButton.className = 'save-next-descriptors';
        nextButton.textContent = 'Save & next →';
        nextButton.disabled = !nextBox;
        saveButton.after(previousButton, nextButton);
      }
      const save = async (destination, action) => {
        const original = action.textContent;
        const targetBox = destination < 0 ? previousBox : destination > 0 ? nextBox : null;
        action.disabled = true;
        saveButton.disabled = true;
        if (previousButton) previousButton.disabled = true;
        if (nextButton) nextButton.disabled = true;
        action.textContent = 'Saving…';
        try {
          const result = await saveDescriptorEditor(editor, trackIds);
          if (currentTrack) {
            currentTrack.descriptors = result.values || [];
            currentTrack.identity_inference_locked = Boolean(result.protected_from_inference);
          }
          notify(
            `Requested: update identity for ${result.requested} tracks. Changed: ${result.updated}. Written to: persistent track catalog. Failed: ${result.missing?.length || 0}. Survives restart: Yes.`,
            'success',
          );
          close();
          setLoadedAt(0);
          invalidateMusicFiles();
          if (targetBox) {
            boxes.forEach((box) => (box.checked = false));
            targetBox.checked = true;
            refresh();
            identityButton.onclick();
          } else {
            await loadLibrary();
          }
        } catch (error) {
          notify(error.message, 'danger');
          action.disabled = false;
          saveButton.disabled = false;
          if (previousButton) previousButton.disabled = !previousBox;
          if (nextButton) nextButton.disabled = !nextBox;
          action.textContent = original;
        }
      };
      saveButton.onclick = (event) => save(0, event.currentTarget);
      if (previousButton) previousButton.onclick = (event) => save(-1, event.currentTarget);
      if (nextButton) nextButton.onclick = (event) => save(1, event.currentTarget);
      bindIdentityInference(editor, trackIds, async () => {
        setLoadedAt(0);
        invalidateMusicFiles();
        await loadLibrary();
      });
    };

    removeButton.onclick = async () => {
      const cards = selectedCards();
      if (
        !cards.length ||
        !(await confirmAction(
          `Remove ${cards.length} selected track${cards.length === 1 ? '' : 's'} and all of their generations from the Library? Exported audio files will remain in the output folder.`,
          { title: 'Remove selected tracks', acceptLabel: 'Remove', danger: true },
        ))
      )
        return;
      removeButton.disabled = true;
      removeButton.textContent = 'Removing…';
      const removed = [];
      const failures = [];
      for (const card of cards) {
        try {
          const response = await api.raw(`/api/library/${encodeURIComponent(card.dataset.sourceName)}`, {
            method: 'DELETE',
          });
          if (!response.ok) throw new Error(api.errorMessage(await response.json(), 'Could not remove the track.'));
          removed.push(card.dataset.sourceName);
        } catch (error) {
          failures.push(`${card.dataset.sourceName}: ${error.message}`);
        }
      }
      await Promise.all([loadLibrary(), loadAnalysis(), loadReports()]);
      const summary = `Requested: remove ${cards.length} Library track${cards.length === 1 ? '' : 's'}. Changed: ${removed.length} removed. Written to: persistent Library catalog. Failed: ${failures.length}${failures.length ? ` (${failures.slice(0, 3).join('; ')}${failures.length > 3 ? '; …' : ''})` : ''}. Survives restart: Yes.`;
      notify(summary, failures.length ? 'danger' : 'success', { timeout: 10000 });
    };

    reanalyzeButton.onclick = async () => {
      const cards = selectedCards();
      const trackIds = selectedTrackIds();
      if (
        !trackIds.length ||
        trackIds.length !== cards.length ||
        !(await confirmAction(
          `Reanalyze ${trackIds.length} selected track${trackIds.length === 1 ? '' : 's'}? Audio files, metadata, artwork, and verified keys will be preserved.`,
          { title: 'Reanalyze selected tracks', acceptLabel: 'Reanalyze' },
        ))
      )
        return;
      reanalyzeButton.disabled = true;
      reanalyzeButton.textContent = 'Adding to queue…';
      try {
        const response = await api.raw('/api/downloaded-library/reanalyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ track_ids: trackIds }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(api.errorMessage(result, 'Could not queue reanalysis.'));
        showView('workspace-view');
        await loadJobs();
      } catch (error) {
        alertUser(error.message);
        reanalyzeButton.textContent = 'Reanalyze';
        refresh();
      }
    };

    keyAnalyzeButton.onclick = () => {
      startKeyAnalysis(selectedTrackIds(), keyAnalyzeButton, async () => {
        setLoadedAt(0);
        await Promise.all([loadLibrary(), loadReports()]);
      });
    };

    button.onclick = async () => {
      const jobIds = boxes.filter((box) => box.checked).map((box) => Number(box.value));
      const fileTypes = typeBoxes.filter((box) => box.checked).map((box) => box.value);
      button.disabled = true;
      button.textContent = 'Preparing download…';
      try {
        const response = await api.raw('/api/library/download', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ job_ids: jobIds, file_types: fileTypes }),
        });
        if (!response.ok) throw new Error(api.errorMessage(await response.json(), 'Could not prepare download.'));
        const url = urlApi.createObjectURL(await response.blob());
        const link = documentRoot.createElement('a');
        link.href = url;
        link.download = 'DJ Library Studio Selected Tracks.zip';
        link.click();
        defer(() => urlApi.revokeObjectURL(url), 1000);
      } catch (error) {
        alertUser(error.message);
      } finally {
        button.textContent = 'Download selected';
        refresh();
      }
    };

    refresh();
  }

  return Object.freeze({ bind, bindIdentityInference, bindIdentityProtection, setVisibleTracks });
}
