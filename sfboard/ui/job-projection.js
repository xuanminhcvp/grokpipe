// Projection lifecycle → hàng đợi UI. Module thuần để test được không cần DOM.
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.GrokpipeJobProjection = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  function jobsTuLifecycle(lifecycle, fallback) {
    if (!lifecycle || lifecycle.source !== 'runtime') return fallback || {};
    const hidden = new Set(lifecycle.hidden_terminal_job_ids || []);
    const latest = new Map();
    for (const job of lifecycle.jobs || []) {
      const marker = job.batch_id || job.job_id;
      let group = latest.get(job.asset_id);
      if (!group || group.marker !== marker) {
        group = { marker, jobs: [] };
        latest.set(job.asset_id, group);
      }
      group.jobs.push(job);
    }
    const out = {};
    for (const [assetId, group] of latest) {
      // Chọn latest group TRƯỚC rồi mới lọc hidden. Nếu lọc trước, Clear một
      // rerun đã xong có thể làm sống lại NEEDS_ATTENTION cũ của cùng asset.
      const visibleJobs = group.jobs.filter(job => !hidden.has(job.job_id));
      if (!visibleJobs.length) continue;
      const states = visibleJobs.map(job => job.state);
      const canonical = states.every(state => state === 'completed') ? 'completed'
        : states.includes('running') ? 'running'
          : states.includes('retry_wait') ? 'retry_wait'
            : states.some(state => state === 'queued' || state === 'created') ? 'queued'
              : states.includes('needs_attention') ? 'needs_attention'
                : states.includes('failed') ? 'failed' : 'cancelled';
      const legacy = {
        created: ['queued', 'chờ lịch bền vững'],
        queued: ['queued', 'chờ lịch bền vững'],
        running: ['running', 'đang chạy'],
        retry_wait: ['queued', 'lỗi → chờ thử lại'],
        completed: ['done', 'xong'],
        failed: ['error', 'thất bại'],
        cancelled: ['error', 'đã dừng'],
        needs_attention: ['error', 'cần kiểm tra — không tự gửi lại'],
      }[canonical];
      out[assetId] = {
        state: legacy[0], msg: legacy[1], canonical_state: canonical,
        job_id: visibleJobs[0].job_id,
        job_ids: visibleJobs.map(job => job.job_id),
        batch_id: visibleJobs[0].batch_id,
      };
    }
    return out;
  }

  return { jobsTuLifecycle };
});
