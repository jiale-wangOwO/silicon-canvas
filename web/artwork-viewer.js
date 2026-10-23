// High-resolution assets are requested only while viewing a selected work.
export function setupArtworkViewer({ showcase, dialog, onOpen, onClose, returnControl }) {
  if (!showcase || !dialog) return () => {};
  const doc = dialog.ownerDocument;
  const view = doc.defaultView;
  const rows = [...showcase.querySelectorAll('.wb-artwork-strip')].map(row =>
    [...row.querySelectorAll('[data-original-artwork] .wb-artwork-picture')]);
  const entries = Array.from({ length: Math.max(0, ...rows.map(row => row.length)) }, (_, index) =>
    rows.map(row => row[index]).filter(Boolean)).flat();
  const element = id => dialog.querySelector(`#${id}`);
  const image = element('artworkViewerImage');
  const status = element('artworkViewerStatus');
  const stage = element('artworkViewerStage');
  const close = element('artworkViewerClose');
  let selected = 0, generation = 0, trigger = null, keyboard = false, pendingImage = null;
  const removers = [];
  function listen(target, name, handler) {
    target.addEventListener(name, handler);
    removers.push(() => target.removeEventListener(name, handler));
  }
  function cancelImage() {
    generation += 1;
    if (pendingImage) {
      pendingImage.onload = pendingImage.onerror = null;
      pendingImage.removeAttribute('src');
    }
    pendingImage = null;
  }
  function show(index) {
    cancelImage();
    selected = (index + entries.length) % entries.length;
    const entry = entries[selected];
    const preview = entry.querySelector('img');
    const token = generation;
    element('artworkViewerTitle').textContent = entry.dataset.title;
    element('artworkViewerCategory').textContent = entry.dataset.category || 'Silicon Canvas';
    element('artworkViewerDescription').textContent = entry.dataset.description || preview.alt;
    element('artworkViewerMeta').textContent = `${entry.dataset.origin === 'native' ? '结构预览' : 'Image Gen'} · ${entry.dataset.dimensions}`;
    element('artworkViewerOriginal').href = entry.href;
    image.alt = preview.alt;
    image.width = preview.width;
    image.height = preview.height;
    image.src = preview.currentSrc || preview.src;
    status.textContent = '正在加载高清图…';
    status.hidden = false;
    stage.setAttribute('aria-busy', 'true');
    const full = new view.Image();
    pendingImage = full;
    full.onload = () => {
      if (token !== generation || !dialog.open) return;
      image.src = full.src;
      stage.setAttribute('aria-busy', 'false');
      status.hidden = true;
      pendingImage = null;
    };
    full.onerror = () => {
      if (token !== generation || !dialog.open) return;
      stage.setAttribute('aria-busy', 'false');
      status.textContent = '高清图暂未加载，可通过下方入口打开原图。';
      pendingImage = null;
    };
    full.src = entry.href;
  }
  function open(event) {
    const anchor = event.target.closest('.wb-artwork-picture');
    if (!anchor || !showcase.contains(anchor) || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const index = entries.findIndex(entry => entry.getAttribute('href') === anchor.getAttribute('href'));
    if (index < 0) return;
    event.preventDefault();
    keyboard = event.detail === 0;
    trigger = anchor.closest('[data-carousel-clone]') ? entries[index] : anchor;
    onOpen?.();
    doc.body.classList.add('wb-viewer-open');
    dialog.showModal();
    show(index);
    close.focus({ preventScroll: true });
  }
  listen(showcase, 'click', open);
  listen(close, 'click', () => dialog.close());
  listen(element('artworkViewerPrevious'), 'click', () => show(selected - 1));
  listen(element('artworkViewerNext'), 'click', () => show(selected + 1));
  listen(dialog, 'keydown', event => {
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key) || event.altKey || event.ctrlKey || event.metaKey) return;
    event.preventDefault();
    show(selected + (event.key === 'ArrowRight' ? 1 : -1));
  });
  let backdropDown = false;
  const outside = event => {
    const rect = dialog.getBoundingClientRect();
    return event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom;
  };
  listen(dialog, 'pointerdown', event => { backdropDown = event.target === dialog && outside(event); });
  listen(dialog, 'click', event => {
    if (backdropDown && event.target === dialog && outside(event)) dialog.close();
    backdropDown = false;
  });
  listen(dialog, 'close', () => {
    cancelImage();
    image.removeAttribute('src');
    doc.body.classList.remove('wb-viewer-open');
    (keyboard ? trigger : returnControl)?.focus({ preventScroll: true });
    onClose?.();
  });
  return () => {
    cancelImage();
    if (dialog.open) dialog.close();
    doc.body.classList.remove('wb-viewer-open');
    for (const remove of removers) remove();
  };
}
