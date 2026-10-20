export function createNavigationController({ documentRef = document, loadView, onError = console.error }) {
  const show = (id) => {
    const target = documentRef.getElementById(id);
    if (!target?.classList.contains('view')) return;
    documentRef.querySelectorAll('.view').forEach((view) => view.classList.toggle('active', view === target));
    documentRef.querySelectorAll('.nav-button').forEach((button) => {
      button.classList.toggle('active', button.dataset.view === id);
    });
    Promise.resolve()
      .then(() => loadView(id))
      .catch(onError);
  };
  documentRef.addEventListener('click', (event) => {
    const control = event.target.closest?.('[data-view]');
    if (!control || control.disabled) return;
    event.preventDefault();
    show(control.dataset.view);
  });
  return { show };
}
