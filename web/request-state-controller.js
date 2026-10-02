const memoryStorage = new Map();

function fallbackStorage() {
  return {
    getItem:key => memoryStorage.get(key) ?? null,
    setItem:(key,value) => memoryStorage.set(key,String(value)),
    removeItem:key => memoryStorage.delete(key),
  };
}

function browserStorage() {
  try { return globalThis.sessionStorage || fallbackStorage(); }
  catch (_) { return fallbackStorage(); }
}

function typedValue(value, fallback) {
  if (typeof fallback === 'number') {
    const parsed=Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }
  if (typeof fallback === 'boolean') return value === 'true';
  return String(value ?? fallback);
}

export function createRequestStateController({
  namespace,
  state,
  defaults={...state},
  debounceMs=240,
  fetchImpl=(...args)=>fetch(...args),
  storage=browserStorage(),
  location=globalThis.location,
  history=globalThis.history,
  onLoading=()=>{},
}={}) {
  if (!namespace || !state) throw new TypeError('namespace and state are required');
  const storageKey=`audioextender:${namespace}:request-state`;
  let sequence=0;
  let controller=null;
  let timer=null;

  const restore = () => {
    let saved={};
    try { saved=JSON.parse(storage.getItem(storageKey)||'{}'); } catch (_) { saved={}; }
    for (const [key,fallback] of Object.entries(defaults)) {
      if (Object.hasOwn(saved,key)) state[key]=typedValue(saved[key],fallback);
    }
    if (location?.href) {
      const url=new URL(location.href);
      for (const [key,fallback] of Object.entries(defaults)) {
        const value=url.searchParams.get(`${namespace}_${key}`);
        if (value!==null) state[key]=typedValue(value,fallback);
      }
    }
    return state;
  };

  const persist = () => {
    const snapshot=Object.fromEntries(Object.keys(defaults).map(key=>[key,state[key]]));
    storage.setItem(storageKey,JSON.stringify(snapshot));
    if (location?.href && history?.replaceState) {
      const url=new URL(location.href);
      for (const [key,fallback] of Object.entries(defaults)) {
        const parameter=`${namespace}_${key}`;
        const value=state[key];
        if (value===fallback || value==='' || value==null) url.searchParams.delete(parameter);
        else url.searchParams.set(parameter,String(value));
      }
      history.replaceState(history.state ?? null,'',`${url.pathname}${url.search}${url.hash}`);
    }
    return snapshot;
  };

  const update = (patch,{resetPage=true}={}) => {
    Object.assign(state,patch);
    if (resetPage && !Object.hasOwn(patch,'page')) state.page=1;
    persist();
    return state;
  };

  const setPage = page => update({page:Math.max(1,Number(page)||1)},{resetPage:false});

  const reset = () => {
    Object.assign(state,defaults,{page:1});
    persist();
    return state;
  };

  const debounce = callback => {
    clearTimeout(timer);
    timer=setTimeout(()=>{timer=null;callback();},debounceMs);
  };

  const cancel = () => {
    clearTimeout(timer);
    timer=null;
    controller?.abort();
    controller=null;
  };

  const request = async (url, options={}) => {
    persist();
    const requestSequence=++sequence;
    controller?.abort();
    controller=new AbortController();
    onLoading(true);
    try {
      const response=await fetchImpl(url,{cache:'no-store',...options,signal:controller.signal});
      if (!response.ok) throw new Error(options.errorMessage||'The catalog could not be loaded.');
      const payload=await response.json();
      if (requestSequence!==sequence) return {status:'stale',payload:null};
      return {status:'applied',payload};
    } catch (error) {
      if (error?.name==='AbortError'||requestSequence!==sequence) return {status:'aborted',payload:null};
      throw error;
    } finally {
      if (requestSequence===sequence) {
        controller=null;
        onLoading(false);
      }
    }
  };

  restore();
  return {state,defaults,restore,persist,update,setPage,reset,debounce,cancel,request};
}
