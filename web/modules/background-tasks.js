const tasks = new Map();

export function stopBackgroundTask(key) {
  const task = tasks.get(key);
  if (!task) return;
  task.cancelled = true;
  clearTimeout(task.timer);
  task.controller?.abort();
  tasks.delete(key);
}

export function runBackgroundTask({key, url, load = null, interval = 1000, active = state => state.status === 'processing', update = () => {}, complete = () => {}, fail = () => {}}) {
  stopBackgroundTask(key);
  const task = {cancelled:false, timer:null, controller:null};
  tasks.set(key, task);
  const tick = async () => {
    if (task.cancelled) return;
    task.controller = new AbortController();
    try {
      let state;
      if (load) state = await load(task.controller.signal);
      else {
        const response = await fetch(typeof url === 'function' ? url() : url, {cache:'no-store', signal:task.controller.signal});
        state = await response.json();
        if (!response.ok) throw new Error(state.detail || 'Background task status is unavailable.');
      }
      update(state);
      if (task.cancelled) return;
      if (active(state)) task.timer = setTimeout(tick, interval);
      else {
        tasks.delete(key);
        await complete(state);
      }
    } catch (error) {
      if (error.name === 'AbortError' || task.cancelled) return;
      tasks.delete(key);
      fail(error);
    }
  };
  tick();
  return () => stopBackgroundTask(key);
}
