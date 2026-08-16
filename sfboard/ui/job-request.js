// GỬI MỘT Ý ĐỊNH TẠO VIỆC — kèm khoá định danh của chính cú bấm đó.
//
// Trước đây mỗi cú bấm là một POST trần: bấm hai lần, mạng chậm rồi bấm lại,
// hay trình duyệt tự gửi lại — server đều thấy hai yêu cầu KHÁC NHAU và xếp
// hai lượt render cho cùng một thẻ. Với video, lượt thừa là một lần trừ credit.
//
// `Idempotency-Key` là định danh của Ý ĐỊNH: gửi lại cùng key thì server trả về
// đúng job cũ và KHÔNG xếp thêm. Key phải sinh MỘT LẦN trước request rồi giữ
// nguyên khi gửi lại — sinh mới mỗi lần gửi là quay về đúng bug cũ.
//
// File này chạy được cả trong trình duyệt lẫn Node (để test), nên không đụng
// tới DOM và không import gì.
function createJobRequestApi(root) {
  function newJobKey() {
    const c = root.crypto;
    if (c && typeof c.randomUUID === 'function') return c.randomUUID();
    // Trình duyệt cũ / ngữ cảnh không bảo mật: không có randomUUID.
    return 'k-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
  }

  async function postJob(path, key, fetchImpl) {
    const k = key || newJobKey();
    const f = fetchImpl || root.fetch;
    const response = await f(path, {
      method: 'POST',
      headers: { 'Idempotency-Key': k },
    });
    return { key: k, response, body: await response.json() };
  }

  return { newJobKey, postJob };
}

const GrokpipeJobRequest = createJobRequestApi(globalThis);
if (typeof module !== 'undefined' && module.exports) module.exports = GrokpipeJobRequest;
globalThis.GrokpipeJobRequest = GrokpipeJobRequest;
