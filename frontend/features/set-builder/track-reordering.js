/** Drag-and-drop and keyboard ownership for the Set Builder running order. */

export function dropDestinationIndex(from, target, placeAfter, length) {
  if (
    !Number.isInteger(from) ||
    !Number.isInteger(target) ||
    !Number.isInteger(length) ||
    length < 1 ||
    from < 0 ||
    target < 0 ||
    from >= length ||
    target >= length
  )
    return -1;
  let destination = target + (placeAfter ? 1 : 0);
  if (from < destination) destination -= 1;
  return Math.max(0, Math.min(length - 1, destination));
}

export function bindTrackReordering({
  cards,
  planLength,
  moveTrack,
  documentRef = document,
  schedule = requestAnimationFrame,
}) {
  let dragging = null;
  const clearDropTargets = () =>
    cards.forEach((card) => card.classList.remove('drag-before', 'drag-after', 'dragging'));

  cards.forEach((card) => {
    const index = Number(card.dataset.index);
    const dragHandle = card.querySelector('.set-drag-handle');
    dragHandle?.addEventListener('keydown', (event) => {
      if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return;
      event.preventDefault();
      const destination = index + (event.key === 'ArrowUp' ? -1 : 1);
      if (moveTrack(index, destination))
        schedule(() =>
          documentRef.querySelector(`.set-track-card[data-index="${destination}"] .set-drag-handle`)?.focus(),
        );
    });
    card.ondragstart = (event) => {
      if (!event.target.closest('.set-drag-handle')) {
        event.preventDefault();
        return;
      }
      dragging = index;
      if (event.dataTransfer) {
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', String(index));
      }
      card.classList.add('dragging');
    };
    card.ondragend = () => {
      dragging = null;
      clearDropTargets();
    };
    card.ondragover = (event) => {
      if (dragging == null || dragging === index) return;
      event.preventDefault();
      if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
      const bounds = card.getBoundingClientRect();
      card.classList.toggle('drag-before', event.clientY < bounds.top + bounds.height / 2);
      card.classList.toggle('drag-after', event.clientY >= bounds.top + bounds.height / 2);
    };
    card.ondragleave = (event) => {
      if (!card.contains(event.relatedTarget)) card.classList.remove('drag-before', 'drag-after');
    };
    card.ondrop = (event) => {
      event.preventDefault();
      if (dragging == null) return;
      const destination = dropDestinationIndex(dragging, index, card.classList.contains('drag-after'), planLength);
      clearDropTargets();
      if (destination >= 0) moveTrack(dragging, destination);
      dragging = null;
    };
  });
}
