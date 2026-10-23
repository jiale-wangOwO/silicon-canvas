// Both rows share one clock and one logical step. Repeated pixels allow each
// center-aligned row to cross its seam without an animated jump backwards.
export function setupArtworkCarousel({ strips, strip, previous, next, pause, interval = 2000 }) {
  const elements = [...new Set((strips ?? [strip]).filter(Boolean))];
  if (!elements.length || !previous || !next) {
    const noop = () => {}; noop.setSuspended = () => {}; return noop;
  }
  const doc = elements[0].ownerDocument, view = doc.defaultView;
  const motion = view.matchMedia('(prefers-reduced-motion: reduce)');
  const removers = [], hovered = new Set();
  const delay = Math.max(500, interval), duration = 520;
  const mod = (value, divisor) => ((value % divisor) + divisor) % divisor;
  const now = () => view.performance.now();
  const rows = elements.map((element) => {
    const bounds = element.getBoundingClientRect();
    return { element, originals: [...element.children].filter((node) => !node.hasAttribute('data-carousel-clone')),
      clones: [], geometry: null, placed: null,
      visible: bounds.bottom > 0 && bounds.top < view.innerHeight && bounds.right > 0 && bounds.left < view.innerWidth };
  });
  let step = 0, timer = null, settleTimer = null, frame = null, animation = null;
  let disposed = false, userPaused = false, suspended = false, pageInactive = false;
  let dragging = false, nativeRow = null, queuedSteps = 0, nextAt = 0;
  const activeRows = () => rows.filter((row) => row.geometry);

  function listen(target, type, handler, options) {
    target?.addEventListener(type, handler, options);
    removers.push(() => target?.removeEventListener(type, handler, options));
  }
  function cancelTimer() { if (timer !== null) view.clearTimeout(timer); timer = null; }
  function cancelSettle() { if (settleTimer !== null) view.clearTimeout(settleTimer); settleTimer = null; }
  function cancelAnimation() {
    if (frame !== null) view.cancelAnimationFrame(frame);
    frame = null; animation = null;
  }
  // Focus on Play does not itself prevent playback. Artwork/arrow focus does.
  function focused() { return [...elements, previous, next].some((node) => node.contains(doc.activeElement)); }
  function center(row, node) {
    const bounds = node.getBoundingClientRect();
    return (bounds.left + bounds.right) / 2 - row.element.getBoundingClientRect().left + row.element.scrollLeft - row.element.clientWidth / 2;
  }
  function place(row, left) {
    row.placed = left;
    row.element.scrollTo({ left, behavior: 'instant' });
    row.placed = row.element.scrollLeft;
  }
  function canonical(row, value = step) { return row.geometry.centers[mod(value, row.originals.length)]; }
  function markCurrent() {
    for (const row of rows) {
      const index = mod(step, row.originals.length || 1);
      row.element.setAttribute('data-current-index', String(index));
      [...row.element.children].forEach((node, position) => {
        if (position % row.originals.length === index) node.classList.add('is-current');
        else node.classList.remove('is-current');
      });
    }
  }
  function updateControls() {
    const enabled = activeRows().length > 0;
    previous.disabled = next.disabled = !enabled;
    if (!pause) return;
    const paused = userPaused || motion.matches;
    pause.hidden = !enabled; pause.disabled = motion.matches;
    pause.textContent = paused ? '▶' : 'Ⅱ';
    pause.setAttribute('aria-pressed', String(paused));
    pause.setAttribute('aria-label', motion.matches ? '已根据系统设置暂停自动播放' : paused ? '播放图片轮播' : '暂停图片轮播');
    pause.title = pause.getAttribute('aria-label');
  }
  function makeClone(row, original) {
    const clone = original.cloneNode(true);
    clone.classList.add('is-carousel-clone');
    clone.setAttribute('data-carousel-clone', ''); clone.removeAttribute('data-original-artwork');
    clone.setAttribute('aria-hidden', 'true');
    for (const node of [clone, ...clone.querySelectorAll('*')]) node.removeAttribute('id');
    for (const node of clone.querySelectorAll('a,button,input,select,textarea,[tabindex],[contenteditable]')) {
      node.setAttribute('tabindex', '-1');
      if (node.hasAttribute('contenteditable')) node.setAttribute('contenteditable', 'false');
    }
    for (const image of clone.querySelectorAll('img')) image.loading = 'lazy';
    row.clones.push(clone);
    return clone;
  }
  function removeClones(row) {
    for (const clone of row.clones.splice(0)) clone.remove();
    row.element.classList.remove('is-carousel-looping');
  }
  function refresh() {
    cancelTimer(); cancelSettle(); cancelAnimation(); queuedSteps = 0; nativeRow = null;
    for (const row of rows) {
      const { element, originals } = row;
      const span = originals.length ? originals.at(-1).getBoundingClientRect().right - originals[0].getBoundingClientRect().left : 0;
      if (originals.length < 2 || span <= element.clientWidth + 1) {
        removeClones(row); row.geometry = null; place(row, 0); continue;
      }
      if (!row.clones.length) {
        element.classList.add('is-carousel-looping');
        for (const original of originals) element.insertBefore(makeClone(row, original), originals[0]);
        for (const original of originals) element.appendChild(makeClone(row, original));
      }
      const centers = originals.map((node) => center(row, node));
      row.geometry = { centers, width: center(row, row.clones[originals.length]) - centers[0] };
      place(row, canonical(row));
    }
    markCurrent(); schedule();
  }
  function schedule(restart = true) {
    cancelTimer(); updateControls();
    if (restart || !nextAt) nextAt = now() + delay;
    if (disposed || suspended || pageInactive || userPaused || motion.matches || doc.hidden ||
      !rows.some((row) => row.visible) || hovered.size || focused() || dragging || animation || nativeRow || !activeRows().length) return;
    timer = view.setTimeout(() => { timer = null; advance(1, true); }, Math.max(0, nextAt - now()));
  }
  function finish() {
    const completed = animation;
    if (!completed) return;
    cancelAnimation(); step = completed.step;
    // Canonical and continuation cards have identical surrounding pixels.
    for (const row of activeRows()) {
      const left = canonical(row);
      if (Math.abs(row.element.scrollLeft - left) > 0.01) place(row, left);
    }
    markCurrent();
    if (!completed.automatic) nextAt = now() + delay;
    if (queuedSteps && !suspended && !pageInactive) {
      const direction = Math.sign(queuedSteps); queuedSteps -= direction; advance(direction);
    } else schedule(false);
  }
  function animateTo(targetStep, automatic = false, direction = 0) {
    cancelTimer(); cancelSettle(); cancelAnimation(); nativeRow = null;
    const positions = activeRows().map((row) => {
      const from = row.element.scrollLeft, base = canonical(row, targetStep);
      let to = base + Math.round((from - base) / row.geometry.width) * row.geometry.width;
      // A two-card row has equidistant copies; retain the requested direction.
      if (direction > 0 && to < from - 0.5) to += row.geometry.width;
      if (direction < 0 && to > from + 0.5) to -= row.geometry.width;
      return { row, from, to };
    });
    animation = { step: targetStep, automatic, started: now(), positions };
    nextAt = now() + delay;
    if (motion.matches || positions.every(({ from, to }) => Math.abs(from - to) < 0.5)) {
      for (const { row, to } of positions) place(row, to);
      finish(); return;
    }
    function tick(timestamp) {
      frame = null;
      if (!animation || disposed) return;
      const progress = Math.min(1, Math.max(0, (timestamp - animation.started) / duration));
      const eased = progress < 0.5 ? 4 * progress ** 3 : 1 - (-2 * progress + 2) ** 3 / 2;
      // One timestamp/easing value makes different-width cards move together.
      for (const { row, from, to } of animation.positions) place(row, from + (to - from) * eased);
      if (progress === 1) finish(); else frame = view.requestAnimationFrame(tick);
    }
    frame = view.requestAnimationFrame(tick);
  }
  function advance(direction, automatic = false) {
    if (disposed || suspended || !activeRows().length) return;
    cancelTimer();
    if (animation) { if (!automatic) queuedSteps += direction; return; }
    animateTo(step + direction, automatic, direction);
  }
  function nearestStep(row) {
    if (!row?.geometry) return step;
    const positions = [...row.element.children].map((node) => center(row, node));
    let nearest = 0;
    positions.forEach((position, index) => {
      if (Math.abs(position - row.element.scrollLeft) < Math.abs(positions[nearest] - row.element.scrollLeft)) nearest = index;
    });
    return step + nearest - row.originals.length - mod(step, row.originals.length);
  }
  function mirrorNative(source) {
    const positions = [...source.element.children].map((node) => center(source, node));
    const before = Math.max(0, Math.min(positions.length - 2,
      positions.findLastIndex((position) => position <= source.element.scrollLeft)));
    const fraction = (source.element.scrollLeft - positions[before]) / (positions[before + 1] - positions[before]);
    const logical = step - mod(step, source.originals.length) + before - source.originals.length + fraction;
    const lower = Math.floor(logical), progress = logical - lower;
    for (const row of activeRows()) {
      if (row === source) continue;
      const start = canonical(row, lower);
      const end = canonical(row, lower + 1) + (mod(lower + 1, row.originals.length) === 0 ? row.geometry.width : 0);
      const base = start + (end - start) * progress;
      // Match fractional card progress, rather than pixel distances, so rows
      // with different artwork widths follow the same finger/trackpad motion.
      place(row, base + Math.round((row.element.scrollLeft - base) / row.geometry.width) * row.geometry.width);
    }
  }
  function settleNative() {
    cancelSettle();
    if (disposed || suspended || pageInactive || dragging) return;
    const row = nativeRow;
    if (row) animateTo(nearestStep(row)); else schedule();
  }
  function armSettle() { cancelSettle(); settleTimer = view.setTimeout(settleNative, 160); }
  function beginNative(row) {
    cancelTimer(); cancelAnimation(); queuedSteps = 0; nativeRow = row;
  }

  listen(previous, 'click', () => advance(-1));
  listen(next, 'click', () => advance(1));
  listen(pause, 'click', () => { userPaused = !userPaused; schedule(); });
  for (const row of rows) {
    const element = row.element;
    listen(element, 'scroll', () => {
      if (!row.geometry || suspended || disposed || (row.placed !== null && Math.abs(element.scrollLeft - row.placed) < 1)) return;
      beginNative(row); mirrorNative(row); armSettle();
    }, { passive: true });
    listen(element, 'pointerdown', () => { dragging = true; beginNative(row); });
    listen(element, 'wheel', (event) => {
      // Ordinary vertical page scrolling should not stop a running transition.
      if (Math.abs(event.deltaX) > 0 || event.shiftKey) { beginNative(row); armSettle(); }
    }, { passive: true });
    listen(element, 'mousedown', (event) => {
      if (event.button === 0 && event.target.closest('[data-carousel-clone]')) event.preventDefault();
    });
    listen(element, 'keydown', (event) => {
      if (event.target !== element || !row.geometry || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') advance(event.key === 'ArrowLeft' ? -1 : 1);
      else { queuedSteps = 0; animateTo(step - mod(step, row.originals.length) + (event.key === 'End' ? row.originals.length - 1 : 0)); }
    });
  }
  for (const node of [...elements, previous, next, pause].filter(Boolean)) {
    listen(node, 'mouseenter', () => { hovered.add(node); schedule(); });
    listen(node, 'mouseleave', () => { hovered.delete(node); schedule(); });
    listen(node, 'focusin', () => schedule());
    listen(node, 'focusout', () => view.queueMicrotask(() => schedule()));
  }
  listen(view, 'pointerup', () => { if (dragging) { dragging = false; armSettle(); } });
  listen(view, 'pointercancel', () => { dragging = false; armSettle(); });
  listen(doc, 'visibilitychange', () => { if (doc.hidden) { queuedSteps = 0; if (animation) finish(); } schedule(); });
  listen(view, 'pagehide', () => {
    pageInactive = true; dragging = false; hovered.clear(); queuedSteps = 0;
    if (animation) finish();
    cancelTimer(); cancelSettle(); nativeRow = null;
  });
  listen(view, 'pageshow', () => { pageInactive = false; refresh(); });
  listen(view, 'resize', refresh);
  listen(motion, 'change', () => { if (motion.matches && animation) finish(); schedule(); });
  const observer = typeof view.IntersectionObserver === 'function'
    ? new view.IntersectionObserver((entries) => {
      for (const entry of entries) { const row = rows.find((item) => item.element === entry.target); if (row) row.visible = entry.isIntersecting; }
      schedule();
    }, { threshold: 0.1 }) : null;
  for (const element of elements) observer?.observe(element);
  refresh();
  const cleanup = () => {
    if (disposed) return;
    disposed = true; cancelTimer(); cancelSettle(); cancelAnimation(); observer?.disconnect();
    for (const remove of removers) remove();
    for (const row of rows) removeClones(row);
  };
  cleanup.setSuspended = (value) => {
    if (disposed || suspended === Boolean(value)) return;
    suspended = Boolean(value); queuedSteps = 0; cancelTimer(); cancelSettle();
    if (suspended) { cancelAnimation(); nativeRow = null; dragging = false; }
    else { const row = activeRows()[0]; if (row) animateTo(nearestStep(row)); else schedule(); }
  };
  return cleanup;
}
