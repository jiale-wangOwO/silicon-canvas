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
  closest(selector) { return this.hasAttribute('data-carousel-clone') ? this : this.parent?.closest(selector) ?? null; }
  getBoundingClientRect() {
    const rail = this.parent;
    if (!rail?.isStrip) return { left: 0, right: 0, top: 0, bottom: 0 };
    const index = rail.children.indexOf(this);
    const left = rail.children.slice(0, index).reduce((sum, n) => sum + n.baseWidth * rail.scale + rail.gap, 0) - rail.scrollLeft;
    return { left, right: left + this.baseWidth * rail.scale, top: 100, bottom: 300 };
  }
  emit(type) { this.dispatchEvent(new Event(type)); }
}

function browser({ viewport = 800, widths = Array(5).fill(280), gap = 20, reduced = false, roundScroll = false } = {}) {
  let time = 0, sequence = 0, observer;
  const jobs = new Map();
  const doc = new Element(); doc.hidden = false; doc.activeElement = null;
  const view = new Element(); doc.defaultView = view;
  const motion = new Element(); motion.matches = reduced;
  view.performance = { now: () => time }; view.matchMedia = () => motion;
  view.innerHeight = 1000; view.innerWidth = 1200; view.queueMicrotask = (fn) => fn();
  view.setTimeout = (callback, delay) => { const id = ++sequence; jobs.set(id, { callback, at: time + delay }); return id; };
  view.clearTimeout = (id) => jobs.delete(id);
  view.IntersectionObserver = class { constructor(callback) { this.callback = callback; observer = this; } observe() {} disconnect() { this.disconnected = true; } };
  const strip = new Element(); strip.ownerDocument = doc; strip.scrollLeft = 0; strip.isStrip = true; strip.scale = 1; strip.gap = gap; strip.clientWidth = viewport;
  Object.defineProperty(strip, 'scrollWidth', { get: () => strip.children.reduce((s, n) => s + n.baseWidth * strip.scale, 0) + Math.max(0, strip.children.length - 1) * gap });
  strip.getBoundingClientRect = () => ({ left: 0, right: strip.clientWidth, top: 100, bottom: 300 });
  strip.moves = [];
  const visible = () => strip.children.map((n) => ({ src: n.children[0].getAttribute('href'), ...n.getBoundingClientRect() })).filter((n) => n.right > 0 && n.left < strip.clientWidth);
  strip.scrollTo = ({ left, behavior }) => {
    const before = visible();
    strip.scrollLeft = Math.max(0, Math.min(Math.max(0, strip.scrollWidth - strip.clientWidth), roundScroll ? Math.round(left) : left));
    strip.moves.push({ left: strip.scrollLeft, behavior, before, after: visible() }); strip.emit('scroll');
  };
  const originals = widths.map((width, i) => {
    const node = new Element(); node.baseWidth = width; node.setAttribute('data-original-artwork', ''); node.setAttribute('id', 'card-' + i);
    const anchor = new Element('a'); anchor.setAttribute('href', i + '.png'); anchor.setAttribute('id', 'link-' + i); anchor.appendChild(new Element('img')); node.appendChild(anchor); strip.appendChild(node); return node;
  });
  const previous = new Element(), next = new Element(), pause = new Element();
  const cleanup = setupArtworkCarousel({ strip, previous, next, pause });
  function advance(duration) {
    const end = time + duration;
    for (;;) {
      const first = [...jobs].sort((a, b) => a[1].at - b[1].at)[0];
      if (!first || first[1].at > end) break;
      jobs.delete(first[0]); time = first[1].at; first[1].callback();
    }
    time = end;
  }
  advance(160); // Initial instant placement settles before interaction.
  return { strip, originals, previous, next, pause, doc, motion, view, cleanup, advance, jobs, visible,
    intersect(value) { observer.callback([{ target: strip, isIntersecting: value }]); },
    key(key) { const event = new Event('keydown', { cancelable: true }); Object.defineProperty(event, 'key', { value: key }); strip.dispatchEvent(event); return event; } };
}

test('two-second forward advances cross the seam smoothly, then recenter identical pixels without a backwards animation', () => {
  const b = browser();
  assert.equal(b.strip.scrollLeft, 1500);
  b.advance(1839); assert.equal(b.strip.scrollLeft, 1500);
  b.advance(1); assert.equal(b.strip.scrollLeft, 1800);
  b.advance(8000); assert.equal(b.strip.scrollLeft, 3000);
  b.advance(160); assert.equal(b.strip.scrollLeft, 1500);
  const movement = b.strip.moves.slice(1);
  assert.deepEqual(movement.filter((m) => m.behavior === 'smooth').map((m) => m.left), [1800, 2100, 2400, 2700, 3000]);
  const normalization = movement.at(-1);
  assert.equal(normalization.behavior, 'instant'); assert.deepEqual(normalization.before, normalization.after);
  assert.equal(b.previous.disabled, false); assert.equal(b.next.disabled, false);
  b.cleanup();
});

test('previous crosses the leading seam with the same stationary pixel equivalence', () => {
  const b = browser(); b.previous.emit('click'); assert.equal(b.strip.scrollLeft, 1200);
  b.advance(160); assert.equal(b.strip.scrollLeft, 2700);
  assert.deepEqual(b.strip.moves.at(-1).before, b.strip.moves.at(-1).after); b.cleanup();
});

test('unequal fractional card widths and thirteen originals retain exact repeated geometry over many cycles', () => {
  const b = browser({ viewport: 710, widths: Array.from({ length: 13 }, (_, i) => 190.125 + i * 7.25), gap: 13.5 });
  const start = b.strip.scrollLeft;
  for (let i = 0; i < 52; i++) { b.next.emit('click'); b.advance(160); }
  assert.equal(b.strip.scrollLeft, start);
  for (const move of b.strip.moves.filter((m) => m.behavior === 'instant').slice(1)) assert.deepEqual(move.before, move.after);
  b.cleanup();
});

test('rapid manual arrows queue whole steps and do not race the running animation or autoplay', () => {
  const b = browser(); b.next.emit('click'); b.next.emit('click'); b.next.emit('click');
  assert.equal(b.strip.scrollLeft, 1800);
  b.advance(480); assert.equal(b.strip.scrollLeft, 2400);
  b.advance(1999); assert.equal(b.strip.scrollLeft, 2400);
  b.advance(1); assert.equal(b.strip.scrollLeft, 2700); b.cleanup();
});

test('native integer scroll rounding just below a fractional cycle boundary still recenters the first artwork', () => {
  const b = browser({ viewport: 367, widths: [280.171875, 280, 280, 280, 280], gap: 13, roundScroll: true });
  const start = b.strip.scrollLeft;
  for (let i = 0; i < 5; i++) { b.next.emit('click'); b.advance(160); }
  assert.equal(b.strip.scrollLeft, start);
  assert.equal(b.visible()[0].src, '0.png');
  assert.ok(b.strip.moves.at(-1).before[0].left < 1);
  b.cleanup();
});

test('hover, reading focus, hidden and offscreen states pause autoplay and resume a fresh interval', () => {
  const b = browser(); const start = b.strip.scrollLeft;
  b.strip.emit('mouseenter'); b.advance(6000); assert.equal(b.strip.scrollLeft, start);
  b.strip.emit('mouseleave'); b.doc.activeElement = b.originals[0].children[0]; b.strip.emit('focusin');
  b.advance(6000); assert.equal(b.strip.scrollLeft, start);
  b.doc.activeElement = null; b.strip.emit('focusout'); b.doc.hidden = true; b.doc.emit('visibilitychange');
  b.advance(6000); assert.equal(b.strip.scrollLeft, start);
  b.doc.hidden = false; b.doc.emit('visibilitychange'); b.intersect(false); b.advance(6000); assert.equal(b.strip.scrollLeft, start);
  b.intersect(true); b.advance(1999); assert.equal(b.strip.scrollLeft, start); b.advance(1); assert.equal(b.strip.scrollLeft, start + 300); b.cleanup();
});

test('Play retains focus and resumes after hover exits; explicit pause survives lifecycle restoration', () => {
  const b = browser(); const start = b.strip.scrollLeft;
  b.doc.activeElement = b.pause; b.pause.emit('focusin'); b.pause.emit('mouseenter'); b.pause.emit('click');
  b.advance(6000); assert.equal(b.strip.scrollLeft, start);
  b.pause.emit('click'); b.pause.emit('mouseleave'); b.advance(2000); assert.equal(b.strip.scrollLeft, start + 300);
  b.advance(160); b.pause.emit('click'); b.view.emit('pagehide'); b.view.emit('pageshow'); b.view.emit('pageshow');
  b.advance(6000); assert.equal(b.strip.scrollLeft, start + 300); assert.equal(b.pause.getAttribute('aria-pressed'), 'true'); b.cleanup();
});

test('pagehide cancels pending work and repeated pageshow leaves one autoplay timer', () => {
  const b = browser(); const start = b.strip.scrollLeft;
  b.view.emit('pagehide'); assert.equal(b.jobs.size, 0); b.advance(6000); assert.equal(b.strip.scrollLeft, start);
  b.view.emit('pageshow'); b.view.emit('pageshow'); assert.equal(b.jobs.size, 1);
  b.advance(2000); assert.equal(b.strip.scrollLeft, start + 300); b.cleanup();
});

test('reduced motion retains cyclic instant manual navigation without autoplay', () => {
  const b = browser({ reduced: true }); const start = b.strip.scrollLeft;
  b.advance(6000); assert.equal(b.strip.scrollLeft, start); assert.equal(b.pause.disabled, true);
  b.previous.emit('click'); b.advance(160); assert.equal(b.strip.scrollLeft, start + 1200);
  assert.equal(b.strip.moves.some((m) => m.behavior === 'smooth'), false); b.cleanup();
});

test('keyboard Home and End refer to originals; drag release normalizes a long native scroll', () => {
  const b = browser({ viewport: 367, widths: Array(9).fill(268.25), gap: 13 });
  const start = b.strip.scrollLeft;
  assert.equal(b.key('End').defaultPrevented, true); b.advance(160); assert.equal(b.strip.scrollLeft, start + 8 * 281.25);
  b.key('Home'); b.advance(160); assert.equal(b.strip.scrollLeft, start);
  b.strip.emit('pointerdown'); b.strip.scrollTo({ left: b.strip.scrollWidth - b.strip.clientWidth, behavior: 'instant' });
  b.advance(2000); const edge = b.visible(); b.view.emit('pointerup'); b.advance(160);
  assert.deepEqual(edge, b.visible()); b.cleanup();
});

test('resize preserves the logical artwork and recomputes variable measured offsets', () => {
  const b = browser({ widths: [200.5, 350.25, 280.75, 400.5] });
  b.next.emit('click'); b.advance(160); b.next.emit('click'); b.advance(160);
  assert.equal(b.visible()[0].src, '2.png');
  b.strip.scale = 1.27; b.strip.clientWidth = 390; b.view.emit('resize'); b.advance(160);
  assert.equal(b.visible()[0].src, '2.png');
  b.strip.clientWidth = 2000; b.view.emit('resize'); b.advance(160);
  assert.equal(b.strip.children.length, 4); assert.equal(b.next.disabled, true); assert.equal(b.pause.hidden, true); b.cleanup();
});

test('clones keep pointer hrefs but have no duplicate IDs, original markers or keyboard stops; cleanup removes them', () => {
  const b = browser();
  const clones = b.strip.children.filter((n) => n.hasAttribute('data-carousel-clone'));
  assert.equal(clones.length, 10);
  for (const clone of clones) {
    assert.equal(clone.getAttribute('aria-hidden'), 'true'); assert.equal(clone.hasAttribute('data-original-artwork'), false);
    assert.equal([clone, ...clone.querySelectorAll('*')].some((n) => n.hasAttribute('id')), false);
    assert.equal(clone.children[0].getAttribute('tabindex'), '-1'); assert.match(clone.children[0].getAttribute('href'), /\.png$/);
    assert.equal(clone.children[0].children[0].loading, 'lazy');
  }
  b.cleanup(); b.cleanup(); assert.equal(b.strip.children.length, 5); assert.equal(b.jobs.size, 0);
  b.next.emit('click'); b.view.emit('pageshow'); b.advance(6000); assert.equal(b.jobs.size, 0);
});

test('small nonoverflowing inventories remain uncloned and have no automatic work', () => {
  const b = browser({ widths: [240, 240] }); b.advance(6000);
  assert.equal(b.strip.children.length, 2); assert.equal(b.jobs.size, 0); assert.equal(b.previous.disabled, true); assert.equal(b.next.disabled, true); assert.equal(b.pause.hidden, true); b.cleanup();
});
