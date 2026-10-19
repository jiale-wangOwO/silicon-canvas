// Native scrolling through repeated pixels. Only stationary scroll positions
// are recentered; crossing the last artwork is an ordinary forward advance.
export function setupArtworkCarousel({ strip, previous, next, pause, interval = 2000 }) {
  if (!strip || !previous || !next) return () => {};
  const doc = strip.ownerDocument;
  const view = doc.defaultView;
  const motion = view.matchMedia('(prefers-reduced-motion: reduce)');
  const originals = [...strip.children].filter((node) => !node.hasAttribute('data-carousel-clone'));
  const removers = [], clones = [], hovered = new Set();
  const delay = Math.max(500, interval);
  let timer = null, settleTimer = null, disposed = false, userPaused = false;
  let dragging = false, pageInactive = false, animating = false, manualAnimation = false, queuedSteps = 0;
  let geometry = null, nextAt = 0, instantTarget = null;
  const bounds = strip.getBoundingClientRect();
  let onScreen = bounds.bottom > 0 && bounds.top < view.innerHeight && bounds.right > 0 && bounds.left < view.innerWidth;
  const now = () => view.performance.now();
  const mod = (value, divisor) => ((value % divisor) + divisor) % divisor;

  function listen(target, type, handler, options) {
    target?.addEventListener(type, handler, options);
    removers.push(() => target?.removeEventListener(type, handler, options));
  }
  function cancelTimer() { if (timer !== null) view.clearTimeout(timer); timer = null; }
  function cancelSettle() { if (settleTimer !== null) view.clearTimeout(settleTimer); settleTimer = null; }
  function focused() { return [strip, previous, next].some((node) => node.contains(doc.activeElement)); }
  function offset(node) { return node.getBoundingClientRect().left - strip.getBoundingClientRect().left + strip.scrollLeft; }
  function updateControls() {
    previous.disabled = next.disabled = !geometry;
    if (pause) {
      const paused = userPaused || motion.matches;
      pause.hidden = !geometry;
      pause.disabled = motion.matches;
      pause.textContent = paused ? '▶' : 'Ⅱ';
      pause.setAttribute('aria-pressed', String(paused));
      pause.setAttribute('aria-label', motion.matches ? '已根据系统设置暂停自动播放' : paused ? '播放图片轮播' : '暂停图片轮播');
      pause.title = pause.getAttribute('aria-label');
    }
  }
  function makeClone(original) {
    const clone = original.cloneNode(true);
    clone.classList.add('is-carousel-clone');
    clone.setAttribute('data-carousel-clone', '');
    clone.removeAttribute('data-original-artwork');
    clone.setAttribute('aria-hidden', 'true');
    for (const node of [clone, ...clone.querySelectorAll('*')]) node.removeAttribute('id');
    for (const node of clone.querySelectorAll('a,button,input,select,textarea,[tabindex],[contenteditable]')) {
      node.setAttribute('tabindex', '-1');
      if (node.hasAttribute('contenteditable')) node.setAttribute('contenteditable', 'false');
    }
    for (const image of clone.querySelectorAll('img')) image.loading = 'lazy';
    clones.push(clone);
    return clone;
  }
  function removeClones() {
    for (const clone of clones.splice(0)) clone.remove();
    strip.classList.remove('is-carousel-looping');
  }
  function placeInstant(left) {
    instantTarget = left;
    strip.scrollTo({ left, behavior: 'instant' });
  }
  function recenter() {
    if (!geometry) return;
    const relative = strip.scrollLeft - geometry.start;
    if (relative < -0.5 || relative >= geometry.width - 0.5) {
      // Keep fractional geometry: rounding every cycle gradually drifts.
      const turns = Math.floor((relative + 0.5) / geometry.width);
      placeInstant(strip.scrollLeft - turns * geometry.width);
    }
  }
  function refresh() {
    cancelTimer(); cancelSettle(); queuedSteps = 0; animating = false;
    let index = 0, fraction = 0;
    if (geometry) {
      const relative = mod(strip.scrollLeft - geometry.start, geometry.width);
      index = Math.max(0, geometry.offsets.findLastIndex((value) => value <= relative + 0.5));
      const end = geometry.offsets[index + 1] ?? geometry.width;
      fraction = (relative - geometry.offsets[index]) / (end - geometry.offsets[index]);
    }
    const span = originals.length ? originals.at(-1).getBoundingClientRect().right - originals[0].getBoundingClientRect().left : 0;
    if (originals.length < 2 || span <= strip.clientWidth + 1) {
      removeClones(); geometry = null;
      placeInstant(0);
    } else {
      if (!clones.length) {
        strip.classList.add('is-carousel-looping');
        for (const original of originals) strip.insertBefore(makeClone(original), originals[0]);
        for (const original of originals) strip.appendChild(makeClone(original));
      }
      const start = offset(originals[0]);
      const width = offset(clones[originals.length]) - start;
      const offsets = originals.map((node) => offset(node) - start);
      geometry = { start, width, offsets };
      const end = offsets[index + 1] ?? width;
      placeInstant(start + offsets[index] + fraction * (end - offsets[index]));
    }
    schedule();
  }
  function schedule(restart = true) {
    cancelTimer(); updateControls();
    if (restart || !nextAt) nextAt = now() + delay;
    if (disposed || pageInactive || userPaused || motion.matches || doc.hidden || !onScreen || hovered.size || focused() || dragging || animating || !geometry) return;
    timer = view.setTimeout(() => {
      timer = null; nextAt = now() + delay; advance(1, true);
    }, Math.max(0, nextAt - now()));
  }
  function armSettle() { cancelSettle(); settleTimer = view.setTimeout(settle, 160); }
  function settle() {
    cancelSettle();
    if (disposed || pageInactive || dragging) return;
    animating = false;
    recenter();
    if (manualAnimation) { nextAt = now() + delay; manualAnimation = false; }
    if (queuedSteps) {
      const direction = Math.sign(queuedSteps); queuedSteps -= direction; advance(direction);
    } else schedule(false);
  }
  function advance(direction, automatic = false) {
    if (!geometry) return;
    cancelTimer();
    if (animating) { if (!automatic) queuedSteps += direction; return; }
    recenter();
    const current = strip.scrollLeft;
    const positions = [...strip.children].map(offset);
    const target = direction > 0 ? positions.find((value) => value > current + 0.5)
      : positions.findLast((value) => value < current - 0.5);
    if (target === undefined) return;
    manualAnimation = !automatic; animating = !motion.matches;
    if (motion.matches) placeInstant(target);
    else strip.scrollTo({ left: target, behavior: 'smooth' });
    if (motion.matches) settle(); else armSettle();
  }
  function manual(direction) { nextAt = now() + delay; advance(direction); }

  listen(previous, 'click', () => manual(-1));
  listen(next, 'click', () => manual(1));
  listen(pause, 'click', () => { userPaused = !userPaused; schedule(); });
  listen(strip, 'scroll', () => {
    const ownPlacement = instantTarget !== null && Math.abs(strip.scrollLeft - instantTarget) < 1;
    instantTarget = null;
    if (ownPlacement || !geometry) return;
    cancelTimer(); animating = true; armSettle();
  }, { passive: true });
  // A quiet-scroll debounce also avoids an instant recenter's scrollend event
  // accidentally completing the next queued smooth advance.
  // Pointer links keep their browser behavior; hidden continuation links do
  // not receive focus or introduce duplicate keyboard/accessibility entries.
  listen(strip, 'mousedown', (event) => {
    if (event.button === 0 && event.target.closest('[data-carousel-clone]')) event.preventDefault();
  });
  listen(strip, 'keydown', (event) => {
    if (event.target !== strip || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key) || !geometry) return;
    event.preventDefault();
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') manual(event.key === 'ArrowLeft' ? -1 : 1);
    else {
      cancelTimer(); queuedSteps = 0; animating = !motion.matches; manualAnimation = true;
      const target = geometry.start + (event.key === 'Home' ? 0 : geometry.offsets.at(-1));
      if (motion.matches) placeInstant(target);
      else strip.scrollTo({ left: target, behavior: 'smooth' });
      if (motion.matches) settle(); else armSettle();
    }
  });
  for (const node of [strip, previous, next, pause].filter(Boolean)) {
    listen(node, 'mouseenter', () => { hovered.add(node); schedule(); });
    listen(node, 'mouseleave', () => { hovered.delete(node); schedule(); });
    listen(node, 'focusin', schedule);
    listen(node, 'focusout', () => view.queueMicrotask(schedule));
  }
  listen(strip, 'pointerdown', () => { dragging = true; manualAnimation = true; queuedSteps = 0; schedule(); });
  listen(view, 'pointerup', () => { if (dragging) { dragging = false; armSettle(); } });
  listen(view, 'pointercancel', () => { dragging = false; armSettle(); });
  listen(strip, 'wheel', () => { manualAnimation = true; queuedSteps = 0; schedule(); }, { passive: true });
  listen(doc, 'visibilitychange', schedule);
  listen(view, 'pagehide', () => { pageInactive = true; dragging = false; hovered.clear(); queuedSteps = 0; cancelTimer(); cancelSettle(); });
  listen(view, 'pageshow', () => { pageInactive = false; nextAt = now() + delay; settle(); });
  listen(view, 'resize', refresh);
  listen(motion, 'change', schedule);
  const observer = typeof view.IntersectionObserver === 'function'
    ? new view.IntersectionObserver((entries) => {
      const entry = entries.find((item) => item.target === strip);
      if (entry) { onScreen = entry.isIntersecting; schedule(); }
    }, { threshold: 0.1 }) : null;
  observer?.observe(strip);
  refresh();
  return () => {
    if (disposed) return;
    disposed = true; cancelTimer(); cancelSettle(); observer?.disconnect();
    for (const remove of removers) remove();
    removeClones();
  };
}
