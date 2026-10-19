let runtime;
let initializing;

function progress(message) { self.postMessage({ type: 'progress', message }); }

async function initialize() {
  if (runtime) return runtime;
  if (initializing) return initializing;
  initializing = (async () => {
    progress('正在加载浏览器编译核心，首次使用需要下载运行环境…');
    const response = await fetch(new URL('./runtime-lock.json', import.meta.url), { cache: 'no-cache' });
    if (!response.ok) throw new Error('无法读取运行环境配置，请重新加载网页。');
    const lock = await response.json();
    const { loadPyodide } = await import(`${lock.indexURL}pyodide.mjs`);
    const python = await loadPyodide({ indexURL: lock.indexURL, stdout: () => {}, stderr: () => {} });
    progress('正在加载字体测量与底稿渲染…');
    await python.loadPackage(lock.packages);
    const archive = await fetch(new URL(lock.compilerArchive, import.meta.url));
    if (!archive.ok) throw new Error('编译核心资源缺失，请重新部署网页资源。');
    const bytes = new Uint8Array(await archive.arrayBuffer());
    python.FS.mkdirTree('/app');
    python.unpackArchive(bytes, 'zip', { extractDir: '/app' });
    python.runPython(`import sys, json\nsys.path.insert(0, '/app')\nfrom silicon_canvas.browser_bridge import dispatch\n`);
    runtime = python;
    progress('编译核心已就绪。');
    return runtime;
  })();
  try { return await initializing; } catch (error) { initializing = undefined; throw error; }
}

// Commands are serialized. The Python core owns geometry, text measurement and ZIP generation.
let queue = Promise.resolve();
self.addEventListener('message', (event) => {
  const { id, action, payload } = event.data || {};
  if (!Number.isSafeInteger(id) || typeof action !== 'string') return;
  queue = queue.then(async () => {
    try {
      const python = await initialize();
      python.globals.set('_sc_action', action);
      python.globals.set('_sc_payload_json', JSON.stringify(payload ?? {}));
      let result;
      try {
        result = await python.runPythonAsync(`json.dumps(dispatch(_sc_action, json.loads(_sc_payload_json)), ensure_ascii=False)`);
      } finally {
        python.globals.delete('_sc_action');
        python.globals.delete('_sc_payload_json');
      }
      self.postMessage({ id, result: JSON.parse(result) });
    } catch (error) {
      // Only engine validation text is exposed; provider errors never travel through this worker.
      const message = String(error?.message || '编译失败。');
      const known = message.match(/(?:ValueError|TypeError|KeyError|ProvenanceError): ([^\n]+)/);
      self.postMessage({ id, error: known ? known[1].slice(0, 500) : '浏览器编译环境未能完成请求，请检查网络后重试。', code: known ? 'validation' : 'runtime' });
    }
  }).catch(() => {});
});
