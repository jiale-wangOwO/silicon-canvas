const base = './assets/aesthetic-20261022/';
const entries = [
  ['01-residual-rmsnorm', 'algorithm', 'Residual RMS Normalization', './assets/framework-20261023/'],
  ['03-command-controller', 'system', 'Command Controller', './assets/framework-20261023/'],
  ['05-compute-package', 'product', '黑曜计算封装'],
  ['01-gated-mlp', 'algorithm', 'SwiGLU：门控与融合'],
  ['06-chiplet-exploded', 'product', 'Chiplet 层间组装'],
  ['03-edge-vision', 'system', '端侧视觉：从像素到事件'],
  ['07-tiled-matmul', 'algorithm', '分块矩阵乘加'],
  ['04-chiplet-fabric', 'system', '异构芯粒互连'],
  ['02-ring-allreduce', 'algorithm', 'Ring All-Reduce 两阶段'],
  ['08-optical-io', 'product', '光电共封装'],
];
const gallery = document.querySelector('#gallery');
const viewer = document.querySelector('#viewer');
const asList = value => Array.isArray(value) ? value : typeof value === 'string' && value ? [value] : [];
const node = (tag, text, className) => {
  const element = document.createElement(tag);
  if (text) element.textContent = text;
  if (className) element.className = className;
  return element;
};
let filter = 'all';
let selectedId = '';
let lastTrigger;
const cases = await Promise.all(entries.map(async ([id, group, title, folder = base]) => {
  let data = {};
  try {
    const response = await fetch(`${folder}${id}-case.json`);
    if (response.ok) data = await response.json();
  } catch { /* Images remain available if supplementary text cannot load. */ }
  return {
    ...data, id, group, title: data.title || title,
    image: folder + (data.image_file || data.image || `${id}.png`),
    thumbnail: `./assets/showcase-thumbs/${folder.split('/').filter(Boolean).pop()}--${id}.webp`,
    prompt: folder + (data.prompt_file || data.prompt || `${id}-prompt.txt`),
    style: data.subtitle || data.palette || data.style || '',
    composition: asList(data.composition),
    evaluation: data.evaluation || (typeof data.review === 'string' ? data.review : asList(data.review?.strengths).join(' ')),
    limitations: asList(data.limitations || data.review?.limitations),
  };
}));

function filteredCases() { return cases.filter(item => filter === 'all' || item.group === filter); }
function addLink(parent, label, href) {
  const link = node('a', label);
  link.href = href;
  link.target = '_blank';
  link.rel = 'noopener';
  parent.append(link);
}
function render() {
  gallery.replaceChildren();
  for (const item of filteredCases()) {
    const article = node('article', '', 'case');
    article.id = item.id;
    const picture = node('button', '', 'case-picture');
    picture.type = 'button';
    picture.setAttribute('aria-label', `放大查看：${item.title}`);
    const image = node('img');
    image.src = item.thumbnail;
    image.alt = item.title;
    image.width = item.dimensions?.width || item.width || 1672;
    image.height = item.dimensions?.height || item.height || 941;
    image.loading = 'lazy';
    image.decoding = 'async';
    picture.append(image);
    picture.addEventListener('click', () => { lastTrigger = picture; openImage(item); });
    const meta = node('div', '', 'case-meta');
    meta.append(node('h2', item.title));
    if (item.style) meta.append(node('p', item.style, 'case-style'));
    meta.append(node('p', item.purpose || '', 'case-purpose'));
    const details = node('details');
    details.append(node('summary', '构图与使用'));
    if (item.composition.length) {
      const list = node('ul');
      item.composition.forEach(text => list.append(node('li', text)));
      details.append(list);
    }
    if (item.evaluation) details.append(node('p', item.evaluation));
    if (item.limitations.length) details.append(node('p', item.limitations.join(' ')));
    const links = node('div', '', 'prompt-links');
    addLink(links, item.prompt_kind === 'edit' ? '调整提示词 ↗' : '生成提示词 ↗', item.prompt);
    if (item.initial_prompt_file) addLink(links, '初始提示词 ↗', base + item.initial_prompt_file);
    if (item.edit_prompt_file) addLink(links, '调整提示词 ↗', base + item.edit_prompt_file);
    details.append(links);
    meta.append(details);
    article.append(picture, meta);
    gallery.append(article);
  }
  gallery.setAttribute('aria-busy', 'false');
  document.querySelector('#loadStatus').hidden = true;
}
function openImage(item) {
  selectedId = item.id;
  document.querySelector('#viewerTitle').textContent = item.title;
  document.querySelector('#viewerPurpose').textContent = item.purpose || '';
  const image = document.querySelector('#viewerImage');
  image.src = item.image;
  image.alt = item.title;
  document.querySelector('#originalImage').href = item.image;
  if (!viewer.open) viewer.showModal();
}
function stepImage(direction) {
  const visible = filteredCases();
  const index = visible.findIndex(item => item.id === selectedId);
  openImage(visible[(index + direction + visible.length) % visible.length]);
}
document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {
  filter = button.dataset.filter;
  document.querySelectorAll('[data-filter]').forEach(peer => peer.setAttribute('aria-pressed', String(peer === button)));
  render();
}));
document.querySelector('#closeViewer').addEventListener('click', () => viewer.close());
document.querySelector('#previousImage').addEventListener('click', () => stepImage(-1));
document.querySelector('#nextImage').addEventListener('click', () => stepImage(1));
viewer.addEventListener('close', () => lastTrigger?.focus({ preventScroll: true }));
viewer.addEventListener('keydown', event => {
  if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
    event.preventDefault();
    stepImage(event.key === 'ArrowLeft' ? -1 : 1);
  }
});
render();
