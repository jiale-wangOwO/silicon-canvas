import assert from 'node:assert/strict';
import test from 'node:test';
import { setupArtworkCarousel } from '../artwork-carousel.js';

class Element extends EventTarget {
  attributes = new Map(); children = []; disabled = false; hidden = false; parent = null; baseWidth = 0;
  constructor(tag = 'article') { super(); this.tagName = tag; const classes = new Set(); this.classList = { add: (x) => classes.add(x), remove: (x) => classes.delete(x), contains: (x) => classes.has(x) }; }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.get(name) ?? null; }
  hasAttribute(name) { return this.attributes.has(name); }
  removeAttribute(name) { this.attributes.delete(name); }
  contains(node) { return node === this || this.children.some((child) => child.contains(node)); }
  appendChild(node) { node.parent = this; this.children.push(node); return node; }
  insertBefore(node, before) { node.parent = this; this.children.splice(this.children.indexOf(before), 0, node); }
  remove() { if (this.parent) this.parent.children.splice(this.parent.children.indexOf(this), 1); this.parent = null; }
  cloneNode(deep) { const n = new Element(this.tagName); n.baseWidth = this.baseWidth; n.attributes = new Map(this.attributes); if (deep) for (const c of this.children) n.appendChild(c.cloneNode(true)); return n; }
  querySelectorAll(selector) {
    const all = this.children.flatMap((n) => [n, ...n.querySelectorAll('*')]);
    return selector === '*' ? all : selector === 'img' ? all.filter((n) => n.tagName === 'img') : all.filter((n) => n.tagName === 'a' || n.hasAttribute('tabindex') || n.hasAttribute('contenteditable'));
  }
  closest() { return this.hasAttribute('data-carousel-clone') ? this : this.parent?.closest() ?? null; }
  getBoundingClientRect() {
    const rail = this.parent;
    if (!rail?.isStrip) return { left: 0, right: 0, top: 0, bottom: 0 };
    const index = rail.children.indexOf(this);
    const left = rail.children.slice(0, index).reduce((sum, n) => sum + n.baseWidth * rail.scale + rail.gap, 0) - rail.scrollLeft;
    return { left, right: left + this.baseWidth * rail.scale, top: 100, bottom: 300 };
  }
  emit(type) { this.dispatchEvent(new Event(type)); }
}

function browser({ viewport = 800, widths = [Array(5).fill(280), [400, 540, 350, 280, 420]], gap = 20, reduced = false, roundScroll = false } = {}) {
  let time = 0, sequence = 0, observer;
  const jobs = new Map();
  const doc = new Element(); doc.hidden = false; doc.activeElement = null;
  const view = new Element(); doc.defaultView = view;
  const motion = new Element(); motion.matches = reduced;
  view.performance = { now: () => time }; view.matchMedia = () => motion;
  view.innerHeight = 1000; view.innerWidth = 1200; view.queueMicrotask = (fn) => fn();
  view.setTimeout = (callback, delay) => { const id = ++sequence; jobs.set(id, { callback, at: time + delay }); return id; };
  view.clearTimeout = (id) => jobs.delete(id);
  view.requestAnimationFrame = (callback) => view.setTimeout(() => callback(time), 16);
  view.cancelAnimationFrame = view.clearTimeout;
  view.IntersectionObserver = class { constructor(callback) { this.callback = callback; observer = this; } observe() {} disconnect() { this.disconnected = true; } };
  const visible = (strip) => strip.children.map((n) => ({ src: n.children[0].getAttribute('href'), ...n.getBoundingClientRect() })).filter((n) => n.right > 0 && n.left < strip.clientWidth);
  const rows = widths.map((rowWidths, r) => {
    const strip = new Element(); strip.ownerDocument = doc; strip.scrollLeft = 0; strip.isStrip = true; strip.scale = 1; strip.gap = gap; strip.clientWidth = viewport;
    Object.defineProperty(strip, 'scrollWidth', { get: () => strip.children.reduce((s, n) => s + n.baseWidth * strip.scale, 0) + Math.max(0, strip.children.length - 1) * gap });
    strip.getBoundingClientRect = () => ({ left: 0, right: strip.clientWidth, top: 100, bottom: 300 });
    strip.moves = [];
    strip.scrollTo = ({ left, behavior }) => {
      const before = visible(strip);
      strip.scrollLeft = Math.max(0, Math.min(Math.max(0, strip.scrollWidth - strip.clientWidth), roundScroll ? Math.round(left) : left));
      strip.moves.push({ left: strip.scrollLeft, at: time, behavior, before, after: visible(strip) }); strip.emit('scroll');
    };
    const originals = rowWidths.map((width, i) => {
      const node = new Element(); node.baseWidth = width; node.setAttribute('data-original-artwork', ''); node.setAttribute('id', 'card-' + r + '-' + i);
      const anchor = new Element('a'); anchor.setAttribute('href', r + '-' + i + '.png'); anchor.setAttribute('id', 'link-' + r + '-' + i); anchor.appendChild(new Element('img')); node.appendChild(anchor); strip.appendChild(node); return node;
    });
    return { strip, originals };
  });
  const previous = new Element(), next = new Element(), pause = new Element();
  const cleanup = setupArtworkCarousel({ strips: rows.map((r) => r.strip), previous, next, pause });
  function advance(duration) {
    const end = time + duration;
    for (;;) {
      const first = [...jobs].sort((a, b) => a[1].at - b[1].at)[0];
      if (!first || first[1].at > end) break;
      jobs.delete(first[0]); time = first[1].at; first[1].callback();
    }
    time = end;
  }
  return { rows, previous, next, pause, doc, motion, view, cleanup, advance, jobs, visible,
    intersect(value) { observer.callback(rows.map(({ strip }) => ({ target: strip, isIntersecting: value }))); },
    key(key, row = 0) { const event = new Event('keydown', { cancelable: true }); Object.defineProperty(event, 'key', { value: key }); rows[row].strip.dispatchEvent(event); return event; } };
}
function centered({ strip, originals }, index) {
  const rect = originals[index].getBoundingClientRect();
  assert.ok(Math.abs((rect.left + rect.right) / 2 - strip.clientWidth / 2) < 0.51, 'selected image is centered');
  assert.equal(strip.getAttribute('data-current-index'), String(index));
  assert.equal(originals[index].classList.contains('is-current'), true);
}
function samePixels(before, after) {
  assert.deepEqual(before.map((p) => p.src), after.map((p) => p.src));
  before.forEach((p, i) => {
    assert.ok(Math.abs(p.left - after[i].left) < 0.6);
    assert.ok(Math.abs(p.right - after[i].right) < 0.6);
  });
}

test('unequal-width rows center their first image and share every animation frame and two-second start', () => {
  const b = browser(); b.rows.forEach((r) => centered(r, 0));
  const starts = b.rows.map(({ strip }) => strip.scrollLeft);
  b.advance(1999); assert.deepEqual(b.rows.map(({ strip }) => strip.scrollLeft), starts);
  b.advance(257);
  const fractions = b.rows.map(({ strip, originals }, r) => {
    const distance = (originals[0].baseWidth + originals[1].baseWidth) / 2 + strip.gap;
    return (strip.scrollLeft - starts[r]) / distance;
  });
  assert.ok(fractions[0] > 0 && fractions[0] < 1);
  assert.ok(Math.abs(fractions[0] - fractions[1]) < 1e-10, 'same eased progress despite different widths');
  b.advance(272); b.rows.forEach((r) => centered(r, 1));
  assert.deepEqual(b.rows[0].strip.moves.map((m) => m.at), b.rows[1].strip.moves.map((m) => m.at));
  assert.equal(b.jobs.size, 1, 'one autoplay timer for both rows');
  b.advance(1472); assert.equal(b.rows[0].strip.moves.at(-1).at, 2528);
  b.advance(528); b.rows.forEach((r) => centered(r, 2)); b.cleanup();
});

test('both seams preserve surrounding pixels and fractional centers over repeated cycles', () => {
  const b = browser({ viewport: 710, widths: [[190.125, 350.25, 280.75, 400.5, 261.125], [210.75, 410.125, 250.25, 360.5, 300.125]], gap: 13.5 });
  const starts = b.rows.map(({ strip }) => strip.scrollLeft);
  b.previous.emit('click'); b.advance(528); b.rows.forEach((r) => centered(r, 4));
  for (const { strip } of b.rows) samePixels(strip.moves.at(-1).before, strip.moves.at(-1).after);
  for (let i = 0; i < 21; i++) { b.next.emit('click'); b.advance(528); }
  assert.deepEqual(b.rows.map(({ strip }) => strip.scrollLeft), starts);
  for (const { strip } of b.rows) {
    strip.moves.slice(1).forEach((move, i) => {
      if (Math.abs(move.left - strip.moves[i].left) > 700) samePixels(move.before, move.after);
    });
  }
  b.cleanup();
});

test('rapid arrows queue complete synchronized steps; each manual completion resets autoplay', () => {
  const b = browser(); b.next.emit('click'); b.next.emit('click'); b.next.emit('click');
  b.advance(3 * 528); b.rows.forEach((r) => centered(r, 3));
  const starts = b.rows.map(({ strip }) => strip.scrollLeft);
  b.advance(1999); assert.deepEqual(b.rows.map(({ strip }) => strip.scrollLeft), starts);
  b.advance(529); b.rows.forEach((r) => centered(r, 4)); b.cleanup();
});

test('dragging either row settles to its nearest center and synchronizes the other row', () => {
  const b = browser(); const row = b.rows[1];
  const target = row.originals[2].getBoundingClientRect();
  const targetLeft = row.strip.scrollLeft + (target.left + target.right) / 2 - row.strip.clientWidth / 2;
  row.strip.emit('pointerdown'); row.strip.scrollTo({ left: targetLeft + 45, behavior: 'instant' });
  b.advance(1000);
  const sourceGap = (row.originals[2].baseWidth + row.originals[3].baseWidth) / 2 + row.strip.gap;
  const mirrored = b.rows[0].originals[2].getBoundingClientRect();
  assert.ok(Math.abs((mirrored.left + mirrored.right) / 2 - b.rows[0].strip.clientWidth / 2 + 45 / sourceGap * 300) < 1e-8,
    'other row follows fractional card progress before drag release');
  b.view.emit('pointerup'); b.advance(160 + 528);
  b.rows.forEach((r) => centered(r, 2));
  b.cleanup();
});

test('reading either row pauses both; modal suspension freezes motion and resumes from a centered pair', () => {
  const b = browser(); const starts = b.rows.map(({ strip }) => strip.scrollLeft);
  b.rows[1].strip.emit('mouseenter'); b.advance(6000);
  assert.deepEqual(b.rows.map(({ strip }) => strip.scrollLeft), starts);
  b.rows[1].strip.emit('mouseleave'); b.advance(2300);
  b.cleanup.setSuspended(true); const frozen = b.rows.map(({ strip }) => strip.scrollLeft);
  b.advance(6000); assert.deepEqual(b.rows.map(({ strip }) => strip.scrollLeft), frozen);
  assert.equal(b.jobs.size, 0);
  b.cleanup.setSuspended(false); b.advance(528); b.rows.forEach((r) => centered(r, 1));
  b.advance(2528); b.rows.forEach((r) => centered(r, 2)); b.cleanup();
});

test('reading focus, hidden pages and offscreen rows pause playback; Play focus permits resume', () => {
  const b = browser();
  b.doc.activeElement = b.rows[1].originals[0].children[0]; b.rows[1].strip.emit('focusin'); b.advance(6000);
  b.rows.forEach((r) => centered(r, 0));
  b.doc.activeElement = null; b.rows[1].strip.emit('focusout'); b.doc.hidden = true; b.doc.emit('visibilitychange');
  b.advance(6000); b.rows.forEach((r) => centered(r, 0));
  b.doc.hidden = false; b.doc.emit('visibilitychange'); b.intersect(false); b.advance(6000); b.rows.forEach((r) => centered(r, 0));
  b.intersect(true); b.doc.activeElement = b.pause; b.pause.emit('focusin'); b.pause.emit('click'); b.advance(6000);
  b.rows.forEach((r) => centered(r, 0)); b.pause.emit('click'); b.advance(2528); b.rows.forEach((r) => centered(r, 1));
  b.pause.emit('click'); b.view.emit('pagehide'); b.view.emit('pageshow'); b.view.emit('pageshow');
  b.advance(6000); b.rows.forEach((r) => centered(r, 1)); assert.equal(b.pause.getAttribute('aria-pressed'), 'true'); b.cleanup();
});

test('reduced motion supports instant centered keyboard navigation without autoplay', () => {
  const b = browser({ reduced: true }); b.advance(6000); b.rows.forEach((r) => centered(r, 0));
  assert.equal(b.pause.disabled, true); assert.equal(b.key('End', 1).defaultPrevented, true);
  b.rows.forEach((r) => centered(r, 4)); b.key('Home'); b.rows.forEach((r) => centered(r, 0));
  b.previous.emit('click'); b.rows.forEach((r) => centered(r, 4)); assert.equal(b.jobs.size, 0); b.cleanup();
});

test('resize preserves selected images and recenters for the new viewport', () => {
  const b = browser(); b.next.emit('click'); b.advance(528); b.next.emit('click'); b.advance(528);
  for (const { strip } of b.rows) { strip.scale = 1.27; strip.clientWidth = 390; }
  b.view.emit('resize'); b.rows.forEach((r) => centered(r, 2));
  for (const { strip } of b.rows) strip.clientWidth = 4000;
  b.view.emit('resize'); assert.equal(b.next.disabled, true); assert.equal(b.pause.hidden, true);
  assert.equal(b.jobs.size, 0); b.rows.forEach(({ strip }) => assert.equal(strip.children.length, 5)); b.cleanup();
});

test('clones keep pointer metadata but no duplicate IDs or keyboard stops; cleanup cancels all work', () => {
  const b = browser();
  for (const { strip } of b.rows) {
    const clones = strip.children.filter((n) => n.hasAttribute('data-carousel-clone')); assert.equal(clones.length, 10);
    for (const clone of clones) {
      assert.equal(clone.getAttribute('aria-hidden'), 'true'); assert.equal(clone.hasAttribute('data-original-artwork'), false);
      assert.equal([clone, ...clone.querySelectorAll('*')].some((n) => n.hasAttribute('id')), false);
      assert.equal(clone.children[0].getAttribute('tabindex'), '-1'); assert.match(clone.children[0].getAttribute('href'), /\.png$/);
      assert.equal(clone.children[0].children[0].loading, 'lazy');
    }
  }
  b.next.emit('click'); b.advance(64); b.cleanup(); b.cleanup();
  b.rows.forEach(({ strip }) => assert.equal(strip.children.length, 5)); assert.equal(b.jobs.size, 0);
  b.cleanup.setSuspended(false); b.next.emit('click'); b.view.emit('pageshow'); b.advance(6000); assert.equal(b.jobs.size, 0);
});

test('small inventories stay uncloned; missing markup still provides safe suspension API', () => {
  const b = browser({ widths: [[240, 240], [280]] }); b.advance(6000);
  assert.equal(b.rows[0].strip.children.length, 2); assert.equal(b.rows[1].strip.children.length, 1);
  assert.equal(b.jobs.size, 0); assert.equal(b.previous.disabled, true); b.cleanup();
  const cleanup = setupArtworkCarousel({}); cleanup.setSuspended(true); cleanup();
});
