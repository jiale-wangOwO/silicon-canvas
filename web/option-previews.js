// Small native UI illustrations. They preview presentation choices, not a
// generated result or the user's eventual source facts. No model/API work here.
const FORMS = { auto: '形式自动', diagram: '工程图', system_illustration: '系统示意', product_render: '商业渲染' };
const SCENES = { auto: '用途自动', concept: '整体概念', system: '系统组织', flow: '工作过程', detail: '实现细节' };
const STYLES = { auto: '配色自动', paper: '白皮书 · 明净', blueprint: '技术蓝', signal: '数据流强调色', monochrome: '黑白印刷' };
const DENSITIES = { auto: '详略自动', low: '概览', medium: '适中', high: '详细' };
const ASPECTS = { auto: '画幅自动', '16:9': '16:9', '4:3': '4:3', '1:1': '1:1', A4: 'A4 纵向' };
const MODES = { auto: '视角自动', hero: '产品主视觉', annotated_context: '产品与外围', functional_cutaway: '功能分区', assembly: '组成与层次' };
const PALETTES = {
  paper: { ink: '#17324D', compute: '#DCEAFF', memory: '#FFF0BE', muted: '#6E8BAB', line: '#BFCFE0' },
  blueprint: { ink: '#153759', compute: '#DBECFC', memory: '#E4E9F3', muted: '#8297ac', line: '#c4ced7' },
  signal: { ink: '#203833', compute: '#DCF0E9', memory: '#F8E8D4', muted: '#83948e', line: '#c2cec7' },
  monochrome: { ink: '#202020', compute: '#FFFFFF', memory: '#ECECEC', muted: '#818181', line: '#bdbdbd' },
};
const pick = (value, choices) => typeof value === 'string' && Object.hasOwn(choices, value) ? value : 'auto';
const escape = (text) => String(text).replace(/[&<>"']/g, (value) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[value]);

export function optionPreviewModel(settings = {}) {
  const source = settings && typeof settings === 'object' ? settings : {};
  const representation = pick(source.representation, FORMS);
  const scene = pick(source.scene, SCENES);
  const style = pick(source.style, STYLES);
  const density = pick(source.density, DENSITIES);
  const aspect = pick(source.aspect, ASPECTS);
  const mode = pick(source.explanatory_mode, MODES);
  const language = source.language === 'zh' ? 'zh' : source.language === 'en' ? 'en' : 'auto';
  const neutral = [representation, scene, style, density, aspect, mode].every((value) => value === 'auto');
  const form = representation === 'auto' ? mode !== 'auto' ? mode === 'hero' ? 'product_render' : 'system_illustration' : scene === 'concept' ? 'system_illustration' : 'diagram' : representation;
  const title = neutral ? '让内容决定画面的样子' : representation !== 'auto' ? FORMS[representation] : scene !== 'auto' ? SCENES[scene] : mode !== 'auto' ? '展示视角示意' : style !== 'auto' ? '配色示意' : aspect !== 'auto' ? '画幅示意' : density !== 'auto' ? '详略示意' : '文字示意';
  const descriptions = {
    diagram: '平面模块与连接，讲清资源、依赖和行为。',
    system_illustration: '用空间层次和功能分区解释整个系统。',
    product_render: '用产品主体、材质与环境建立画面的重点。',
  };
  const purpose = { concept: '突出完整方案，收起局部接线。', system: '展开真实归属和主要接口。', flow: '沿输入、分支、处理与返回组织阅读。', detail: '展开局部资源与精确连接。' };
  let description = neutral ? '形式、用途与详略都保持自动，按你的描述匹配。' : descriptions[form];
  if (scene !== 'auto') description = purpose[scene];
  if (mode !== 'auto' && form !== 'diagram') description = { hero: '让产品主体成为主角，留出安静的画面。', annotated_context: '把产品放回外围设备与系统关系中。', functional_cutaway: '透过外观，看清内部功能与主要关系。', assembly: '将组成层次分开，让各部分容易辨认。' }[mode];
  if (!neutral && representation === 'auto' && scene === 'auto') description += ' 表现形式仍按描述匹配。';
  const labels = [representation !== 'auto' ? FORMS[representation] : null, scene !== 'auto' ? SCENES[scene] : null, style !== 'auto' ? STYLES[style] : null, density !== 'auto' ? DENSITIES[density] : null, aspect !== 'auto' ? ASPECTS[aspect] : null, mode !== 'auto' ? MODES[mode] : null].filter(Boolean);
  return { representation, form, scene, style, density, aspect, mode, language, neutral, title, description, labels };
}

function definitions(p, prefix) {
  return `<defs><marker id="${prefix}-arrow" markerWidth="4" markerHeight="4" refX="3.5" refY="2" orient="auto"><path d="M0 0 4 2 0 4Z" fill="${p.ink}"/></marker><linearGradient id="${prefix}-metal" x1="0" y1="0" x2=".9" y2="1"><stop stop-color="#78847c"/><stop offset=".5" stop-color="#394b42"/><stop offset="1" stop-color="#263a31"/></linearGradient></defs>`;
}

function drawing(model, prefix) {
  const p = PALETTES[model.style === 'auto' ? 'paper' : model.style];
  const cn = model.language === 'zh';
  const word = (en, zh) => cn ? zh : en;
  const arrow = `url(#${prefix}-arrow)`;
  const line = (x1, y1, x2, y2, dashed = false) => `<path d="M${x1} ${y1}L${x2} ${y2}" fill="none" stroke="${p.ink}" stroke-width="1.35"${dashed ? ' stroke-dasharray="3 3"' : ''} marker-end="${arrow}"/>`;
  const path = (d, control = false) => `<path d="${d}" fill="none" stroke="${control ? p.muted : p.ink}" stroke-width="${control ? '.95' : '1.35'}"${control ? ' stroke-dasharray="3 3"' : ''} marker-end="${arrow}"/>`;
  const node = (x, y, w, h, label, role = 'compute', header = false) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="1" fill="${role === 'memory' ? p.memory : role === 'io' ? '#fff' : p.compute}" stroke="${p.ink}" stroke-width="1.05"/><text x="${x + w / 2}" y="${y + (header ? 10 : h / 2 + 2.7)}" text-anchor="middle">${escape(label)}</text>${model.style === 'blueprint' ? `<path d="M${x - 3} ${y + h / 2}h3m${w} 0h3" stroke="${p.ink}" stroke-width="1"/>` : ''}`;
  const group = (x, y, w, h, label) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="3" fill="none" stroke="${p.line}" stroke-width=".9"/><text x="${x + 7}" y="${y + 12}" fill="${p.muted}" font-size="7">${escape(label)}</text>`;
  const density = model.density === 'auto' ? 'medium' : model.density;
  const scene = model.scene === 'auto' ? 'system' : model.scene;
  let body = '';
  if (model.form === 'diagram') {
    if (scene === 'flow') {
      body = node(8, 66, 40, 25, word('Input', '输入'), 'io') + node(78, 35, 57, 25, word('Transform', '变换')) + node(78, 100, 57, 25, word('Reduce', '归约')) + node(166, 67, 48, 24, word('Combine', '合并')) + node(245, 67, 44, 24, word('Output', '输出'), 'io');
      body += path('M48 78H62V47H78') + path('M48 78H62V112H78') + path('M135 47H150V79H166') + path('M135 112H150V79H166') + line(214, 79, 245, 79);
      if (density === 'high') body += node(109, 5, 73, 14, word('Control', '控制'), 'io') + path('M145 19V28H107V35', true) + path('M267 91V146H28V91', true);
    } else if (scene === 'concept') {
      body = group(38, 25, 224, 112, word('System', '系统')) + node(57, 58, 56, 39, word('Compute', '计算')) + node(127, 58, 56, 39, word('Memory', '存储'), 'memory') + node(197, 58, 47, 39, word('I/O', '接口'), 'io');
      body += line(113, 77, 127, 77) + line(183, 77, 197, 77);
    } else if (scene === 'detail') {
      body = group(12, 13, 276, 135, word('Processing engine', '处理引擎')) + node(27, 52, 48, 19, word('Queue', '队列'), 'memory') + node(104, 43, 62, 42, word('Execute', '执行'), 'compute', density === 'high') + node(198, 52, 68, 19, word('Writeback', '写回'), 'memory');
      body += line(75, 61, 104, 61) + line(166, 61, 198, 61) + path('M233 71V126H51V71') + node(105, 100, 61, 16, word('Control', '控制'), 'io') + path('M135 100V85', true);
      if (density === 'high') body += node(108, 62, 24, 16, 'ALU') + node(138, 62, 24, 16, 'MUL') + path('M27 40H75', true);
    } else {
      body = group(57, 18, 192, 127, word('On chip', '芯片内部')) + node(74, 47, 62, 40, word('Compute', '计算'), 'compute', density !== 'low') + node(166, 47, 65, 33, word('Memory', '存储'), 'memory') + node(75, 111, 156, 17, word('System interconnect', '系统互联'), 'io') + node(4, 79, 34, 25, word('Host', '主机'), 'io') + path('M38 91H48V119H75') + path('M105 87V111') + path('M198 111V80');
      if (density !== 'low') body += node(80, 65, 23, 14, 'CPU') + node(108, 65, 23, 14, 'NPU');
      if (density === 'high') body += node(260, 58, 36, 22, 'DDR', 'memory') + path('M231 64H260') + node(165, 91, 66, 13, word('DMA / I/O', 'DMA / 接口'), 'io');
    }
  } else {
    const render = model.form === 'product_render';
    const mode = model.mode === 'auto' ? scene === 'concept' ? 'hero' : model.form === 'system_illustration' ? 'functional_cutaway' : 'annotated_context' : model.mode;
    const top = render ? `url(#${prefix}-metal)` : '#e0e8de';
    const packageShape = (dy, opacity = 1) => `<g opacity="${opacity}" transform="translate(0 ${dy})"><path d="m58 54 158-21 39 73-158 22Z" fill="${render ? '#263a31' : '#9faf9e'}"/><path d="m58 46 158-21 39 73-158 22Z" fill="${top}" stroke="${render ? '#5c7060' : p.ink}" stroke-width="1"/></g>`;
    if (mode === 'assembly') {
      body = `<ellipse cx="160" cy="141" rx="94" ry="9" fill="#293f31" opacity=".08"/>` + packageShape(22, .55) + packageShape(-2, .8) + packageShape(-26) + `<path d="M58 20V90m197-18v49" stroke="${p.muted}" stroke-dasharray="3 3" fill="none"/>`;
    } else {
      body = `<ellipse cx="157" cy="135" rx="99" ry="9" fill="#293f31" opacity="${render ? '.12' : '.05'}"/>` + packageShape(0);
      if (mode === 'hero') body += `<text x="154" y="83" text-anchor="middle" fill="${render ? '#f0f3eb' : p.ink}" font-size="18" font-weight="500" transform="rotate(-7 154 83)">${word('SoC', '芯片')}</text>`;
      else {
        body += `<g transform="matrix(1 -.13 .37 .71 79 51)"><rect width="73" height="58" rx="2" fill="${p.compute}" stroke="${p.ink}" stroke-width=".8"/><rect x="80" width="61" height="26" rx="2" fill="${p.memory}" stroke="${p.ink}" stroke-width=".8"/><rect x="80" y="32" width="61" height="26" rx="2" fill="#eef1eb" stroke="${p.ink}" stroke-width=".8"/><text x="36" y="32" text-anchor="middle">${word('Compute', '计算')}</text><text x="110" y="17" text-anchor="middle">${word('Memory', '存储')}</text><text x="110" y="49" text-anchor="middle">I/O</text></g>`;
        if (density === 'high') body += `<path d="m106 78 33-4m39-3 23-3" stroke="${p.ink}" stroke-width="1"/>`;
      }
      if (mode === 'annotated_context' || (model.scene === 'system' && model.mode === 'auto')) body += node(10, 61, 31, 34, word('Host', '主机'), 'io') + node(264, 76, 32, 24, 'DDR', 'memory') + `<path d="M41 78H72m177 12h15" fill="none" stroke="${p.ink}" stroke-width="1.2"/>`;
      if (model.scene === 'flow' && mode !== 'hero') body += path('M37 133H247') + `<text x="140" y="149" text-anchor="middle" fill="${p.muted}" font-size="7">${word('Input → Process → Output', '输入 → 处理 → 输出')}</text>`;
    }
  }
  return `${definitions(p, prefix)}<g fill="${p.ink}" font-family="Inter,Segoe UI,Microsoft YaHei,sans-serif" font-size="8">${body}</g>`;
}

function compactDrawing(model, prefix) {
  const p = PALETTES[model.style === 'auto' ? 'paper' : model.style];
  const cn = model.language === 'zh', word = (en, zh) => cn ? zh : en;
  const portrait = model.aspect === 'A4', width = portrait ? 100 : 160;
  let body = '';
  if (model.form === 'diagram') {
    const x = portrait ? 20 : 46, w = portrait ? 60 : 68;
    const labels = model.scene === 'flow' ? [word('Input', '输入'), word('Process', '处理'), word('Output', '输出')] : [word('Compute', '计算'), word('Memory', '存储'), word('I/O', '接口')];
    body = `<rect x="${x - 9}" y="12" width="${w + 18}" height="128" rx="3" fill="none" stroke="${p.line}" stroke-width=".8"/>`;
    labels.forEach((label, index) => {
      const y = 25 + 39 * index;
      body += `<rect x="${x}" y="${y}" width="${w}" height="24" rx="1" fill="${index === 1 ? p.memory : p.compute}" stroke="${p.ink}" stroke-width="1"/><text x="${width / 2}" y="${y + 15}" text-anchor="middle">${escape(label)}</text>`;
      if (index < 2) body += `<path d="M${width / 2} ${y + 24}v15" fill="none" stroke="${p.ink}" stroke-width="1.1" marker-end="url(#${prefix}-arrow)"/>`;
      if (model.style === 'blueprint') body += `<path d="M${x - 3} ${y + 12}h3m${w} 0h3" stroke="${p.ink}" stroke-width=".9"/>`;
    });
    if (model.density === 'high') body += `<path d="M${x + w} 115h7V37h-7" fill="none" stroke="${p.muted}" stroke-width=".9" stroke-dasharray="2 2"/>`;
  } else {
    const render = model.form === 'product_render';
    const mode = model.mode === 'auto' ? 'functional_cutaway' : model.mode;
    const center = width / 2;
    body = `<ellipse cx="${center + 3}" cy="129" rx="${portrait ? 39 : 55}" ry="6" fill="#294331" opacity=".09"/>`;
    const chip = (offset, opacity = 1) => `<g transform="translate(0 ${offset})" opacity="${opacity}"><path d="m${center - 38} 39 61-9 18 68-61 9Z" fill="${render ? `url(#${prefix}-metal)` : '#e0e8de'}" stroke="${p.ink}" stroke-width=".9"/><path d="m${center - 38} 39v6l18 68 61-9v-6" fill="#54745a"/></g>`;
    body += mode === 'assembly' ? chip(15, .5) + chip(-7, .8) + chip(-29) : chip(0);
    if (mode === 'hero') body += `<text x="${center + 1}" y="75" text-anchor="middle" fill="${render ? '#fff' : p.ink}" font-size="13">SoC</text>`;
    else if (mode !== 'assembly') body += `<g transform="translate(${center - 26} 49) rotate(-8)"><rect width="43" height="25" fill="${p.compute}" stroke="${p.ink}" stroke-width=".6"/><rect y="30" width="43" height="21" fill="${p.memory}" stroke="${p.ink}" stroke-width=".6"/><text x="21" y="16" text-anchor="middle" font-size="7">${word('Compute', '计算')}</text><text x="21" y="44" text-anchor="middle" font-size="7">${word('Memory', '存储')}</text></g>`;
    if (mode === 'annotated_context') body += `<rect x="${center - 19}" y="123" width="38" height="17" fill="#fff" stroke="${p.ink}" stroke-width=".8"/><text x="${center}" y="134" text-anchor="middle" font-size="7">${word('Host', '主机')}</text>`;
  }
  return `${definitions(p, prefix)}<g fill="${p.ink}" font-family="Inter,Segoe UI,Microsoft YaHei,sans-serif" font-size="8">${body}</g>`;
}

export function optionPreviewSvg(model, prefix = 'option-preview') {
  const key = String(prefix).replace(/[^a-zA-Z0-9_-]/g, '') || 'option-preview';
  if (model.neutral) return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 154" role="img" aria-label="自动模式示意：平面工程图、空间系统示意与产品主体"><g fill="none" stroke="#708773" stroke-width="1.5"><rect x="15" y="50" width="26" height="19" rx="2"/><rect x="65" y="34" width="27" height="19" rx="2"/><rect x="65" y="76" width="27" height="19" rx="2"/><path d="M41 59h12V44h12M53 59v26h12"/><path d="m115 57 48-10 18 39-48 10Z" fill="#e0e8de"/><path d="m126 63 17-3 7 19-17 3Zm24-5 17-3 7 19-17 3Z" stroke-width=".8"/><path d="m207 51 59-9 18 44-59 10Z" fill="#42634f"/><path d="m207 51v7l18 45 59-10v-7" fill="#304b3a"/></g><g fill="#7c837b" font-family="Segoe UI,Microsoft YaHei,sans-serif" font-size="8" text-anchor="middle"><text x="53" y="125">工程图</text><text x="148" y="125">系统示意</text><text x="246" y="125">商业渲染</text></g></svg>`;
  const dimensions = { auto: [272, 143], '16:9': [254, 143], '4:3': [190, 143], '1:1': [143, 143], A4: [101, 143] };
  const [width, height] = dimensions[model.aspect];
  const x = (300 - width) / 2, y = (154 - height) / 2;
  const compact = model.aspect === 'A4' || model.aspect === '1:1';
  const viewBox = compact ? model.aspect === 'A4' ? '0 0 100 150' : '0 0 160 150' : '0 0 300 160';
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 154" role="img" aria-label="${escape(model.title)}的视觉示意"><rect x="${x}" y="${y}" width="${width}" height="${height}" rx="3" fill="#ffffff" stroke="#e1e5dc" stroke-width=".8"/><svg x="${x + 5}" y="${y + 5}" width="${width - 10}" height="${height - 10}" viewBox="${viewBox}" preserveAspectRatio="xMidYMid meet">${compact ? compactDrawing(model, key) : drawing(model, key)}</svg></svg>`;
}

let sequence = 0;
const ids = new WeakMap();
export function renderOptionPreview(host, settings = {}) {
  const model = optionPreviewModel(settings);
  if (!host) return model;
  if (!ids.has(host)) ids.set(host, `option-look-${++sequence}`);
  const document = host.ownerDocument;
  const graphic = document.createElement('div'); graphic.className = 'op-graphic';
  graphic.innerHTML = optionPreviewSvg(model, ids.get(host));
  const copy = document.createElement('div'); copy.className = 'op-copy';
  const eyebrow = document.createElement('span'); eyebrow.className = 'op-eyebrow'; eyebrow.textContent = '表达预览';
  const title = document.createElement('strong'); title.className = 'op-title'; title.textContent = model.title;
  const description = document.createElement('p'); description.className = 'op-description'; description.textContent = model.description;
  copy.append(eyebrow, title, description);
  if (model.labels.length) {
    const tags = document.createElement('div'); tags.className = 'op-tags';
    for (const label of model.labels) { const tag = document.createElement('span'); tag.textContent = label; tags.append(tag); }
    copy.append(tags);
  }
  const note = document.createElement('p'); note.className = 'op-note'; note.textContent = '画法示意，实际内容按你的设计组织。'; copy.append(note);
  host.classList.add('option-preview'); host.dataset.previewForm = model.neutral ? 'auto' : model.form; host.replaceChildren(graphic, copy);
  return model;
}
