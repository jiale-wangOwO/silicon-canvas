// Credentials stay in the caller's memory. This module never persists or logs them.
export function providerSettings(baseUrl, model, key) {
  const raw = String(baseUrl || '').trim();
  let url;
  try { url = new URL(raw); } catch { throw new Error('请输入有效的 HTTPS API 地址。'); }
  if (url.protocol !== 'https:' || !url.hostname || url.username || url.password || url.search || url.hash || /\s|\\/.test(raw)) {
    throw new Error('API 地址须为 HTTPS，不能包含用户名、密码、查询参数或片段。');
  }
  const selectedModel = String(model || '').trim();
  if (!selectedModel || selectedModel.length > 150 || /\s/.test(selectedModel)) throw new Error('请输入有效的模型名称。');
  const apiKey = String(key || '').trim();
  if (/\s/.test(apiKey)) throw new Error('API Key 不能包含空格或换行。');
  let path = url.pathname.replace(/\/+$/, '');
  if (!path.endsWith('/chat/completions')) path += '/chat/completions';
  url.pathname = path;
  return { endpoint: url.href, hostname: url.hostname, model: selectedModel, key: apiKey };
}

export function safeStatusError(status) {
  if (status === 401 || status === 403) return 'API Key 无效或没有访问权限，请检查接口设置。';
  if (status === 402) return '模型账户余额不足，请在服务商处检查余额。';
  if (status === 429) return '请求频率或配额受限，请稍后再试。';
  if (status === 404) return '接口路径或模型不存在，请检查接口设置。';
  if (status === 400 || status === 422) return '模型未接受结构化输出参数，请检查是否兼容 Chat Completions 和 JSON 输出。';
  if (status >= 500) return '模型服务暂时不可用，请稍后再试。';
  return `模型请求未成功（HTTP ${status}）。`;
}

async function readBounded(response, limit) {
  if (!response.body?.getReader) {
    const text = await response.text();
    if (new TextEncoder().encode(text).byteLength > limit) throw new Error('模型返回内容过大，请缩短输入或拆分设计。');
    return text;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let size = 0, result = '';
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > limit) throw new Error('模型返回内容过大，请缩短输入或拆分设计。');
      result += decoder.decode(value, { stream: true });
    }
    return result + decoder.decode();
  } finally {
    try { await reader.cancel(); } catch { /* Already closed. */ }
  }
}

export function parseCompletion(text, model) {
  let envelope, data;
  try {
    envelope = JSON.parse(text);
    const choice = envelope?.choices?.[0];
    if (choice?.finish_reason === 'length') throw new Error('length');
    if (![undefined, null, 'stop'].includes(choice?.finish_reason)) throw new Error('finish');
    if (typeof choice?.message?.content !== 'string') throw new Error('format');
    data = JSON.parse(choice.message.content);
    if (!data || typeof data !== 'object' || Array.isArray(data) || !Object.keys(data).length) throw new Error('format');
  } catch (error) {
    if (error.message === 'length') throw new Error('结构输出达到模型上限，请拆分设计或使用支持更长输出的模型。');
    throw new Error('模型未返回完整有效的结构 JSON，请重新生成或检查模型配置。');
  }
  const usage = {};
  for (const name of ['prompt_tokens', 'completion_tokens', 'total_tokens', 'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens']) {
    const value = envelope?.usage?.[name];
    if (Number.isSafeInteger(value) && value >= 0) usage[name] = value;
  }
  return { data, usage, model };
}

export async function complete(messages, settings, signal) {
  if (!settings.key) throw new Error('请先在右上角配置 API Key。');
  const body = { model: settings.model, messages, temperature: 0.2, max_tokens: 12000, response_format: { type: 'json_object' }, stream: false };
  if (new URL(settings.endpoint).hostname === 'api.deepseek.com') body.thinking = { type: 'disabled' };
  let response;
  try {
    response = await fetch(settings.endpoint, {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${settings.key}` },
      body: JSON.stringify(body), signal, redirect: 'error', credentials: 'omit', referrerPolicy: 'no-referrer', cache: 'no-store',
    });
  } catch (error) {
    if (signal?.aborted) throw new DOMException('请求已取消。', 'AbortError');
    throw new Error('无法连接模型接口。请检查网络及服务商的跨域支持；接口重定向也会被阻止。');
  }
  if (!response.ok) { try { await response.body?.cancel(); } catch { /* Ignore. */ } throw new Error(safeStatusError(response.status)); }
  const raw = await readBounded(response, 2 * 1024 * 1024);
  return parseCompletion(raw, settings.model);
}
