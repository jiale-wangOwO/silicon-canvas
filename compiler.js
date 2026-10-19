export class Compiler {
  constructor(onProgress = () => {}) { this.onProgress = onProgress; this.worker = null; this.pending = new Map(); this.sequence = 0; }
  start() {
    if (this.worker) return;
    if (location.protocol === 'file:') throw new Error('请通过 HTTPS 网页或本地静态服务器打开本工具。');
    this.worker = new Worker(new URL('./compiler-worker.js', import.meta.url), { type: 'module' });
    this.worker.onmessage = ({ data }) => {
      if (data.type === 'progress') { this.onProgress(data.message); return; }
      const pending = this.pending.get(data.id);
      if (!pending) return;
      this.pending.delete(data.id); clearTimeout(pending.timeout); pending.cleanup();
      if (data.error) { const error = new Error(data.error); error.code = data.code; pending.reject(error); }
      else pending.resolve(data.result);
    };
    this.worker.onerror = () => this.stop('浏览器编译进程意外停止，请重试。');
    this.worker.onmessageerror = () => this.stop('浏览器编译进程返回了无法读取的数据，请重试。');
  }
  call(action, payload = {}, { signal, timeout = 180000 } = {}) {
    if (signal?.aborted) return Promise.reject(new DOMException('请求已取消。', 'AbortError'));
    this.start();
    const id = ++this.sequence;
    return new Promise((resolve, reject) => {
      const abort = () => this.stop('请求已取消。', true);
      const timer = setTimeout(() => this.stop('浏览器编译超时，请检查网络后重试。'), timeout);
      const cleanup = () => signal?.removeEventListener('abort', abort);
      signal?.addEventListener('abort', abort, { once: true });
      this.pending.set(id, { resolve, reject, timeout: timer, cleanup });
      this.worker.postMessage({ id, action, payload });
    });
  }
  stop(message = '请求已取消。', aborted = false) {
    this.worker?.terminate(); this.worker = null;
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timeout); pending.cleanup();
      pending.reject(aborted ? new DOMException(message, 'AbortError') : new Error(message));
    }
    this.pending.clear();
  }
}
