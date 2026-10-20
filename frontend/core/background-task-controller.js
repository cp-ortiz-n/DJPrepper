export function createBackgroundTaskController({ loadJson, schedule = setTimeout, cancelSchedule = clearTimeout }) {
  const tasks = new Map();

  function stop(key) {
    const task = tasks.get(key);
    if (!task) return false;
    task.cancelled = true;
    cancelSchedule(task.timer);
    task.controller?.abort();
    tasks.delete(key);
    return true;
  }

  function run({
    key,
    url,
    load = null,
    interval = 1000,
    active = (state) => state.status === 'processing',
    update = () => {},
    complete = () => {},
    fail = () => {},
  }) {
    stop(key);
    const task = { cancelled: false, timer: null, controller: null };
    tasks.set(key, task);

    const tick = async () => {
      if (task.cancelled) return;
      task.controller = new AbortController();
      try {
        const state = load
          ? await load(task.controller.signal)
          : await loadJson(typeof url === 'function' ? url() : url, task.controller.signal);
        update(state);
        if (task.cancelled) return;
        if (active(state)) task.timer = schedule(tick, interval);
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

    void tick();
    return () => stop(key);
  }

  return Object.freeze({ run, stop, isRunning: (key) => tasks.has(key) });
}
