/** Shared, reversible presentation state for asynchronous Set Builder actions. */

export function beginButtonAction(button, label = 'Working…') {
  if (!button) return () => {};
  const getAttribute = (name) =>
    typeof button.getAttribute === 'function' ? button.getAttribute(name) : (button[name] ?? null);
  const setAttribute = (name, value) => {
    if (typeof button.setAttribute === 'function') button.setAttribute(name, value);
    else button[name] = String(value);
  };
  const restoreAttribute = (name, value) => {
    if (value == null) {
      if (typeof button.removeAttribute === 'function') button.removeAttribute(name);
      else delete button[name];
    } else setAttribute(name, value);
  };
  const snapshot = {
    disabled: button.disabled,
    text: button.textContent,
    ariaBusy: getAttribute('aria-busy'),
    ariaLabel: getAttribute('aria-label'),
  };
  button.disabled = true;
  button.textContent = label;
  setAttribute('aria-busy', 'true');
  setAttribute('aria-label', label);
  let restored = false;
  return () => {
    if (restored) return;
    restored = true;
    button.disabled = snapshot.disabled;
    button.textContent = snapshot.text;
    restoreAttribute('aria-busy', snapshot.ariaBusy);
    restoreAttribute('aria-label', snapshot.ariaLabel);
  };
}
