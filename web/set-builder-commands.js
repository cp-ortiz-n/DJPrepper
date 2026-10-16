export function createSetEditCommands({ store, snapshot, restore, render, historyLimit = 60 }) {
  const updateAvailability = () => ({ canUndo: store.history.length > 0, canRedo: store.future.length > 0 });

  const checkpoint = () => {
    if (!store.plan.length) return updateAvailability();
    store.history.push(snapshot());
    if (store.history.length > historyLimit) store.history.shift();
    store.future = [];
    return updateAvailability();
  };

  const undo = () => {
    if (!store.history.length) return false;
    store.future.push(snapshot());
    restore(store.history.pop());
    render();
    return true;
  };

  const redo = () => {
    if (!store.future.length) return false;
    store.history.push(snapshot());
    restore(store.future.pop());
    render();
    return true;
  };

  const move = (from, to) => {
    if (from < 0 || from >= store.plan.length || to < 0 || to >= store.plan.length || from === to) return false;
    checkpoint();
    const [track] = store.plan.splice(from, 1);
    store.plan.splice(to, 0, track);
    render();
    return true;
  };

  return Object.freeze({ checkpoint, undo, redo, move, updateAvailability });
}
