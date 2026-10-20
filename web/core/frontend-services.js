function requireFunction(owner, name) {
  if (typeof owner?.[name] !== 'function') {
    throw new TypeError(`Frontend services require ${name}().`);
  }
}

export function createFrontendServices({ api, dom, feedback, descriptors }) {
  for (const method of ['raw', 'request', 'errorMessage']) requireFunction(api, method);
  for (const method of ['$', '$$']) requireFunction(dom, method);
  for (const method of ['notify', 'confirmAction', 'operationReceiptText']) requireFunction(feedback, method);
  for (const method of ['chipsMarkup', 'editorMarkup', 'openEditorDialog', 'saveEditor', 'inferEditor'])
    requireFunction(descriptors, method);

  return Object.freeze({
    api: Object.freeze(api),
    dom: Object.freeze(dom),
    feedback: Object.freeze(feedback),
    descriptors: Object.freeze(descriptors),
  });
}

export function useFrontendServices(services) {
  if (!Object.isFrozen(services)) {
    throw new TypeError('Feature factories require the shared frontend services contract.');
  }
  return {
    api: services.api,
    $: services.dom.$,
    $$: services.dom.$$,
    notify: services.feedback.notify,
    confirmAction: services.feedback.confirmAction,
    operationReceiptText: services.feedback.operationReceiptText,
    descriptorChipsMarkup: services.descriptors.chipsMarkup,
    descriptorEditorMarkup: services.descriptors.editorMarkup,
    openDescriptorEditorDialog: services.descriptors.openEditorDialog,
    saveDescriptorEditor: services.descriptors.saveEditor,
    inferDescriptorEditor: services.descriptors.inferEditor,
  };
}
