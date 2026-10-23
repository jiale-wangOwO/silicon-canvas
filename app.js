import { Compiler } from './compiler.js';
import { complete, providerSettings } from './provider.js';
import { renderOptionPreview } from './option-previews.js';
import { setupArtworkCarousel } from './artwork-carousel.js?v=20261023-gallery';
import { setupArtworkViewer } from './artwork-viewer.js?v=20261023-gallery';

const $ = (id) => document.getElementById(id);
const GPU_INPUT = '我想画一张 GPU 架构图给同事介绍。主机接口接到命令处理器，任务分发到四个计算簇；每簇包含 warp 调度、SIMD、张量单元和片上存储。各簇共享 L2，并经内存控制器访问显存。主图突出任务分发与存储路径，计算簇看得出重复关系，内部控制信号不必全部展开。希望层级清楚，适合放进技术演示文稿。';
const FIELDS = { representation: 'representation', scene: 'scene', style: 'style', density: 'density', aspect: 'aspect', explanatoryMode: 'explanatory_mode', completionMode: 'completion_mode' };
const state = { result: null, figureId: null, input: null, busy: false, controller: null, guideStatus: 'none', revision: 0, provider: providerSettings('https://api.deepseek.com', 'deepseek-flash', '') };
const compiler = new Compiler((message) => { if (state.busy) progress(message); });
let toastTimer, copyTimer;

function toast(message) {
  clearTimeout(toastTimer); $('toast').textContent = message; $('toast').hidden = false;
  toastTimer = setTimeout(() => { $('toast').hidden = true; }, 4500);
}
function notice(message = '', error = false) { $('notice').textContent = message; $('notice').classList.toggle('error', error); $('notice').hidden = !message; }
function progress(message = '') { $('progress').textContent = message; }
// New requests use English artwork labels; refinements use their saved settings.
function settings() { return { ...Object.fromEntries(Object.entries(FIELDS).map(([id, key]) => [key, $(id).value])), language: 'en' }; }
function input() { return { category: 'auto', ...settings(), description: $('description').value.trim(), notes: '', labels: '' }; }
function customCount() {
  const count = Object.keys(FIELDS).filter((id) => $(id).value !== 'auto').length;
  $('customCount').textContent = count; $('customCount').hidden = !count;
  renderOptionPreview($('optionPreview'), settings());
}
function resetSettings() { for (const id of Object.keys(FIELDS)) $(id).value = 'auto'; customCount(); }
function setBusy(busy, message = '') {
  state.busy = busy;
  for (const control of document.querySelectorAll('.wb-workspace button, .wb-workspace select, #description, #feedback, #lockStructure')) control.disabled = busy;
  $('openSettings').disabled = busy;
  $('cancel').disabled = false; $('cancel').hidden = !busy;
  $('outputPanel').setAttribute('aria-busy', String(busy));
  $('generateLabel').textContent = busy ? '正在生成…' : '生成提示词';
  if (message) progress(message); else if (!busy) progress();
}
async function operation(work, message) {
  if (state.busy) return;
  notice(); $('downloadMenu').open = false;
  state.controller = new AbortController(); setBusy(true, message);
  try { await work(state.controller.signal); }
  catch (error) {
    if (error.name === 'AbortError') notice('已取消。已发送的请求可能仍由模型服务商处理。');
    else notice(error.message || '本次生成未完成，请重试。', true);
  } finally { state.controller = null; setBusy(false); }
}
function figures() { return state.result?.figures || []; }
function figure() { return figures().find((item) => item.id === state.figureId) || figures()[0]; }
function representation(selected = figure()) {
  return selected?.technical_annex ? 'diagram' : selected?.render_brief?.representation || state.result?.representation_profile?.id || state.result?.settings?.resolved_representation || 'diagram';
}
function handoffHint() {
  const selected = figure();
  if (selected?.requires_layout_guide) {
    $('generationHint').textContent = state.guideStatus === 'available'
      ? '将提示词与绘图包中的配套图片，一起交给图片生成工具。'
      : state.guideStatus === 'pending' ? '正在准备配套文件…' : '配套图片未能生成，暂不能按完整方案使用。请调整描述后重试。';
  } else if (representation(selected) === 'diagram' && !selected?.algorithm_flow_plan && !selected?.structure_layout) {
    $('generationHint').textContent = '本次仅有文字提示词，布局与连接需要在成图后核对。';
  } else $('generationHint').textContent = '把提示词交给 ChatGPT 等工具的图片生成功能。';
}
async function checkRequiredReference(signal) {
  const selected = figure(), revision = state.revision;
  state.guideStatus = selected?.requires_layout_guide ? 'pending' : 'none'; handoffHint();
  if (!selected?.requires_layout_guide) return;
  try {
    const file = await compiler.call('guide', { result: state.result, figure_id: selected.id }, { signal });
    if (state.revision === revision) state.guideStatus = file?.base64 ? 'available' : 'unavailable';
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    if (state.revision === revision) state.guideStatus = 'unavailable';
  }
  if (state.revision === revision) handoffHint();
}
function renderFigure() {
  const selected = figure(); if (!selected) return;
  state.figureId = selected.id; $('figureChoice').value = selected.id;
  $('resultTitle').textContent = selected.title || state.result.spec.title;
  // The complete, unmodified compiler prompt is the primary hand-off.
  $('promptOutput').value = selected.prompt || '';
  $('copyLabel').textContent = '复制提示词'; handoffHint();
}
function renderResult(result, savedInput) {
  if (!result?.spec || !Array.isArray(result.figures) || !result.figures.length) throw new Error('没有返回可用的绘图方案，请重试。');
  state.result = result; state.input = savedInput; state.revision++;
  state.figureId = figures().some((item) => item.id === state.figureId) ? state.figureId : result.selected_figure_id || figures().find((item) => item.primary)?.id || figures()[0].id;
  $('figureChoice').replaceChildren();
  for (const [index, item] of figures().entries()) {
    const option = document.createElement('option'); option.value = item.id;
    option.textContent = item.primary ? '主图' : item.technical_annex ? `细节图 ${index}` : `视图 ${index + 1}`;
    $('figureChoice').append(option);
  }
  $('figureChoiceLabel').hidden = figures().length < 2;
  $('outputPanel').hidden = false; renderFigure();
}
function requireKey() {
  if (state.provider.key) return true;
  $('settingsError').hidden = true; $('settingsDialog').showModal(); $('apiKey').focus();
  return false;
}
async function generate(request, signal) {
  const prepared = await compiler.call('prepare', request, { signal });
  progress('正在理解内容，安排画面…');
  const controller = new AbortController();
  const abort = () => controller.abort(signal.reason); signal.addEventListener('abort', abort, { once: true });
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, 120000);
  const connection = { ...state.provider }; // Freeze this request's destination and credential.
  try {
    let completion = await complete(prepared.messages, connection, controller.signal), result;
    progress('正在生成提示词…');
    try { result = await compiler.call('finish', { data: completion.data, context: prepared.context }, { signal }); }
    catch (error) {
      if (error.code !== 'validation') throw error;
      const repair = await compiler.call('repair', { messages: prepared.messages, data: completion.data, context: prepared.context, error: error.message }, { signal });
      progress('正在检查并调整内容…');
      const fixed = await complete(repair.messages, connection, controller.signal);
      const usage = { ...completion.usage };
      for (const [name, count] of Object.entries(fixed.usage)) usage[name] = (usage[name] || 0) + count;
      completion = { ...fixed, usage };
      result = await compiler.call('finish', { data: completion.data, context: prepared.context }, { signal });
      result.repaired = true;
    }
    result.model = connection.model; result.usage = completion.usage;
    const { previous, ...savedInput } = request;
    renderResult(result, savedInput); await checkRequiredReference(signal);
    $('feedback').value = '';
    if (matchMedia('(max-width:760px)').matches) $('outputPanel').scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion:reduce)').matches ? 'auto' : 'smooth', block: 'start' });
  } catch (error) {
    if (timedOut) throw new Error('模型请求超时。服务商可能仍在处理，请稍后检查后再试。');
    throw error;
  } finally { clearTimeout(timer); signal.removeEventListener('abort', abort); }
}
function decodeFile(file) {
  if (!file?.base64) throw new Error('文件暂不可用，请重试。');
  const data = atob(file.base64), bytes = new Uint8Array(data.length);
  for (let i = 0; i < data.length; i++) bytes[i] = data.charCodeAt(i);
  return new Blob([bytes], { type: file.mime || 'application/octet-stream' });
}
function filename(text, suffix) { return (String(text || 'silicon-canvas').replace(/[^\p{L}\p{N}_-]+/gu, '-').replace(/^-+|-+$/g, '').slice(0, 70) || 'silicon-canvas') + suffix; }
function download(blob, name) {
  const link = document.createElement('a'), url = URL.createObjectURL(blob);
  link.href = url; link.download = name; link.hidden = true; document.body.append(link); link.click(); link.remove();
  $('downloadMenu').open = false; setTimeout(() => URL.revokeObjectURL(url), 30000);
}
async function copyPrompt() {
  const text = $('promptOutput').value; if (!text) return;
  try {
    await navigator.clipboard.writeText(text); $('copyLabel').textContent = '已复制';
    clearTimeout(copyTimer); copyTimer = setTimeout(() => { $('copyLabel').textContent = '复制提示词'; }, 2200);
    if (figure()?.requires_layout_guide) toast('已复制。请同时使用绘图包中的配套图片。');
  } catch { $('promptOutput').focus(); $('promptOutput').select(); toast('已选中文字，请使用浏览器复制。'); }
}

$('createForm').addEventListener('submit', (event) => {
  event.preventDefault(); if (!requireKey()) return;
  const request = input(); state.figureId = null;
  operation((signal) => generate(request, signal), '正在准备…');
});
$('cancel').addEventListener('click', () => state.controller?.abort());
$('fillExample').addEventListener('click', () => { $('description').value = GPU_INPUT; resetSettings(); $('description').focus(); });
for (const id of Object.keys(FIELDS)) $(id).addEventListener('change', customCount);
$('resetSettings').addEventListener('click', resetSettings);
$('figureChoice').addEventListener('change', () => operation(async (signal) => {
  state.figureId = $('figureChoice').value; state.revision++; renderFigure(); await checkRequiredReference(signal);
}, '正在切换视图…'));
$('refine').addEventListener('click', () => {
  const feedback = $('feedback').value.trim();
  if (!feedback) { $('feedback').focus(); toast('写下希望调整的地方。'); return; }
  if (!state.result || !requireKey()) return;
  operation((signal) => generate({ ...state.result.settings, description: state.result.description || state.input.description, feedback, previous: state.result, lock_structure: $('lockStructure').checked, figure_id: state.figureId }, signal), '正在准备调整…');
});
$('copyPrompt').addEventListener('click', copyPrompt);
$('downloadPrompt').addEventListener('click', () => download(new Blob([$('promptOutput').value], { type: 'text/plain;charset=utf-8' }), filename(figure()?.title, '-prompt.txt')));
$('downloadBundle').addEventListener('click', () => operation(async (signal) => {
  const file = await compiler.call('bundle', { result: state.result }, { signal });
  download(decodeFile(file), file.filename || filename(state.result.spec.title, '-generation-pack.zip'));
}, '正在准备绘图包…'));
$('saveProject').addEventListener('click', () => {
  const project = { version: 1, tool: 'silicon-canvas', title: state.result.spec.title, input: state.input, result: state.result, active_figure_id: state.figureId, lock_structure: $('lockStructure').checked };
  download(new Blob([JSON.stringify(project, null, 2)], { type: 'application/json;charset=utf-8' }), filename(project.title, '-silicon-canvas.json'));
});
function keyStatus() { $('keyStatus').textContent = state.provider.key ? '模型已配置' : '连接模型'; $('keyDot').classList.toggle('ready', !!state.provider.key); }
function destination() {
  try { const provider = providerSettings($('baseUrl').value, $('model').value, ''); $('destination').textContent = `请求将从浏览器直接发送至 ${provider.hostname}。`; }
  catch { $('destination').textContent = '请填写有效的 HTTPS 接口地址。'; }
}
$('openSettings').addEventListener('click', () => { $('settingsError').hidden = true; $('settingsDialog').showModal(); });
$('closeSettings').addEventListener('click', () => $('settingsDialog').close());
$('settingsDialog').addEventListener('click', (event) => {
  if (event.target !== $('settingsDialog')) return;
  const rect = event.target.getBoundingClientRect();
  if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) $('settingsDialog').close();
});
$('baseUrl').addEventListener('input', destination); $('model').addEventListener('input', destination);
$('toggleKey').addEventListener('click', () => { const visible = $('apiKey').type === 'password'; $('apiKey').type = visible ? 'text' : 'password'; $('toggleKey').textContent = visible ? '隐藏' : '显示'; });
$('settingsForm').addEventListener('submit', (event) => {
  event.preventDefault();
  try { state.provider = providerSettings($('baseUrl').value, $('model').value, $('apiKey').value); keyStatus(); $('settingsDialog').close(); toast(state.provider.key ? '模型已配置。' : '设置已保存，尚未填写密钥。'); }
  catch (error) { $('settingsError').textContent = error.message; $('settingsError').hidden = false; }
});
$('clearKey').addEventListener('click', () => { state.provider = { ...state.provider, key: '' }; $('apiKey').value = ''; keyStatus(); toast('密钥已清除。'); });

const cleanupCarousel = setupArtworkCarousel({
  strips: [$('artworkStrip'), $('artworkStripSecondary')],
  previous: $('artworkPrevious'), next: $('artworkNext'), pause: $('artworkPause'),
});
const cleanupViewer = setupArtworkViewer({
  showcase: document.querySelector('.wb-showcase'), dialog: $('artworkViewer'), returnControl: $('artworkPause'),
  onOpen: () => cleanupCarousel.setSuspended(true), onClose: () => cleanupCarousel.setSuspended(false),
});
document.addEventListener('click', (event) => { if (!$('downloadMenu').contains(event.target)) $('downloadMenu').open = false; });
document.addEventListener('keydown', (event) => { if (event.key === 'Escape') $('downloadMenu').open = false; });
window.addEventListener('pagehide', (event) => { state.provider.key = ''; $('apiKey').value = ''; compiler.stop(); if (!event.persisted) { cleanupViewer(); cleanupCarousel(); } });
window.addEventListener('pageshow', keyStatus);
keyStatus(); customCount();
