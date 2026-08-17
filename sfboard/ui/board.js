// Giao diện SF Board — phần JavaScript.
// Tách khỏi board.html 2026-08-12. Board phục vụ file này ở /ui/board.js.
// SỬA GIAO DIỆN THÌ SỬA ĐÂY, đừng dán ngược vào board.html.
// VIEW nhớ qua các lần tải lại: đang làm dở tab nào thì F5 vẫn ở tab đó. Lưu chung
// cho mọi phim như cờ sáng/tối — đây là chỗ đang làm việc, không phải thuộc tính phim.
// KHOÁ Ý ĐỊNH cho mọi nút TẠO. `job-request.js` nạp trước file này (xem
// board.html). Sinh key MỘT LẦN trước request rồi giữ nguyên khi gửi lại —
// sinh mới mỗi lần gửi là quay về đúng bug "bấm hai lần render hai lượt".
const { newJobKey, postJob } = globalThis.GrokpipeJobRequest;
const { jobsTuLifecycle } = globalThis.GrokpipeJobProjection;
const VIEW_OK = ['script', 'sf'];
let DATA = { scenes: [] }, JOBS = {}, SUBMITTING = {}, AUTO = {}, T = null, DIRTY = false, MTIME = 0;
let VIEW = VIEW_OK.includes(localStorage.getItem('sfboard-view'))
  ? localStorage.getItem('sfboard-view') : 'script';
// THẺ ĐỊA ĐIỂM — chỗ dừng khi leo refs.bg, và là nơi giữ luatchung + chat.
// Dấu hiệu chuẩn là CÓ luatchung. Tiền tố 'SF-M-' là quy ước CŨ (bỏ 2026-08-07),
// vẫn nhận để dự án cũ hiển thị đúng.
const isDiaDiem = f => !!((f.luatchung || '').trim()) || /^SF-M-/.test(f.id || '');
const $ = s => document.querySelector(s);
const esc = s => (s || '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
/* giây → m:ss. Dùng chung cho chip tổng trên header và huy hiệu từng scene,
   để hai chỗ không lệch cách hiển thị. */
const mmss = s => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`;
const ST = { proposed: ['pend', 'Chờ duyệt'], approved: ['ok', 'ĐÃ DUYỆT'], revise: ['warn', 'Cần sửa'], rejected: ['bad', 'Loại'] };

/* Lifecycle mới là nguồn trạng thái. `SUBMITTING` chỉ là trạng thái nút cục bộ
   trong lúc request chưa được server nhận; nó không giả mạo JOBS=running. */
const viecHienTai = id => SUBMITTING[id] || JOBS[id] || {};
const jobQuery = id => {
  const job = viecHienTai(id);
  return job.job_id
    ? 'job_id=' + encodeURIComponent(job.job_id)
    : 'sf=' + encodeURIComponent(id);
};
/* BADGE TRẠNG THÁI cạnh mã SF và mã video — xanh DUYỆT, đỏ LÀM LẠI (user chốt
   2026-08-15). Trước đó thử báo bằng viền thẻ: viền đủ đậm để nhìn ra thì cả
   lưới thành vòng màu bão hoà, chói mắt; badge gọn hơn vì chỉ chiếm một điểm.
   Thẻ chưa duyệt KHÔNG có badge — không dán nhãn cho trạng thái mặc định, bảng
   sẽ đầy nhãn vô nghĩa.
   Không dùng lại nhãn của `ST` ở trên: ST phục vụ chip thống kê ở header với
   cách gọi khác ("ĐÃ DUYỆT" · "Loại"), đổi nó là đổi luôn chỗ đó. */
const STAG = { approved: ['ok', 'DUYỆT'], revise: ['warn', 'SỬA'], rejected: ['bad', 'LÀM LẠI'] };
const stag = s => STAG[s] ? `<span class="kindtag st ${STAG[s][0]}">${STAG[s][1]}</span>` : '';

/* ══ HỘP HỎI / BÁO ══ thay await hoi() và bao() của trình duyệt.
   Hộp gốc dán nguyên "localhost:8780 says", nền trắng bất kể theme, không xuống
   dòng được và nút thì theo hệ điều hành. Hộp này dùng <dialog> nên vẫn KHOÁ thao
   tác như bản gốc (Esc = huỷ), nhưng theo màu board và tự xuống dòng.
   ⚠ hoi() là BẤT ĐỒNG BỘ — phải `await hoi(...)`, quên await thì Promise luôn
   truthy và hành động nguy hiểm chạy ngay cả khi user bấm Huỷ. */
function _hopThoai({ tieude, msg, ic, nut }) {
  return new Promise(res => {
    const d = $('#hoibox');
    $('#hb-ic').textContent = ic || '';
    $('#hb-t').textContent = tieude || '';
    $('#hb-m').textContent = msg || '';
    const ft = $('#hb-ft'); ft.innerHTML = '';
    let xong = false;
    const dong = v => { if (xong) return; xong = true; d.close(); res(v) };
    nut.forEach(n => {
      const b = document.createElement('button');
      b.textContent = n.nhan;
      if (n.chinh) b.className = 'go' + (n.bad ? ' bad' : '');
      b.onclick = () => dong(n.tra);
      ft.appendChild(b);
    });
    d.oncancel = e => { e.preventDefault(); dong(false) };   // Esc = huỷ
    d.showModal();
    // Nút chính nhận focus để Enter là xong; với việc XOÁ thì focus nút Huỷ cho an toàn.
    const uu = ft.querySelector(nut.some(n => n.bad) ? 'button' : '.go') || ft.lastChild;
    setTimeout(() => uu.focus(), 20);
  });
}
function hoi(msg, { tieude, dong = 'Đồng ý', bad = false } = {}) {
  return _hopThoai({
    tieude: tieude || (bad ? 'Xác nhận — không hoàn tác được' : 'Xác nhận'),
    ic: bad ? '⚠️' : '❓', msg,
    nut: [{ nhan: 'Huỷ', tra: false }, { nhan: dong, tra: true, chinh: true, bad }]
  });
}
function bao(msg, { tieude } = {}) {
  return _hopThoai({
    tieude: tieude || 'Thông báo', ic: 'ℹ️', msg,
    nut: [{ nhan: 'Đóng', tra: true, chinh: true }]
  });
}
/* chonMuc(): danh sách bấm được, thay kiểu prompt() "gõ lại mã cho đúng".
   items = [{tra, nhan, phu}] · trả về `tra` của mục được bấm, null nếu huỷ. */
function chonMuc(msg, items, { tieude } = {}) {
  return new Promise(res => {
    const d = $('#hoibox');
    $('#hb-ic').textContent = '📋';
    $('#hb-t').textContent = tieude || 'Chọn';
    const bd = $('#hb-m'); bd.textContent = msg || '';
    const ds = document.createElement('div');
    ds.style.cssText = 'display:flex;flex-direction:column;gap:4px;margin-top:12px';
    let xong = false;
    const kt = v => { if (xong) return; xong = true; d.close(); res(v) };
    items.forEach(it => {
      const b = document.createElement('button');
      b.style.cssText = 'text-align:left;padding:8px 11px;font-weight:600';
      b.innerHTML = esc(it.nhan) + (it.phu ? ` <span style="font-weight:400;color:var(--tx2)">— ${esc(it.phu)}</span>` : '');
      b.onclick = () => kt(it.tra);
      ds.appendChild(b);
    });
    bd.appendChild(ds);
    const ft = $('#hb-ft'); ft.innerHTML = '';
    const huy = document.createElement('button'); huy.textContent = 'Huỷ'; huy.onclick = () => kt(null);
    ft.appendChild(huy);
    d.oncancel = e => { e.preventDefault(); kt(null) };
    d.showModal();
    setTimeout(() => ds.firstChild && ds.firstChild.focus(), 20);
  });
}
/* nhap() thay prompt(): trả về chuỗi đã trim, hoặc null nếu huỷ / để trống —
   ĐÚNG hợp đồng của prompt() cũ nên chỗ gọi không phải đổi cách kiểm. */
function nhap(msg, { tieude, macdinh = '', dong = 'Đồng ý', placeholder = '' } = {}) {
  return new Promise(res => {
    const d = $('#hoibox');
    $('#hb-ic').textContent = '✏️';
    $('#hb-t').textContent = tieude || 'Nhập';
    $('#hb-m').textContent = msg || '';
    const o = document.createElement('input');
    o.type = 'text'; o.value = macdinh; o.placeholder = placeholder;
    o.style.cssText = 'width:100%;margin-top:12px;font-family:ui-monospace,monospace';
    $('#hb-m').appendChild(o);
    const ft = $('#hb-ft'); ft.innerHTML = '';
    let xong = false;
    const kt = v => { if (xong) return; xong = true; d.close(); res(v) };
    const lay = () => { const v = o.value.trim(); kt(v || null) };
    const huy = document.createElement('button'); huy.textContent = 'Huỷ'; huy.onclick = () => kt(null);
    const ok = document.createElement('button'); ok.textContent = dong; ok.className = 'go'; ok.onclick = lay;
    ft.append(huy, ok);
    o.onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); lay() } };
    d.oncancel = e => { e.preventDefault(); kt(null) };
    d.showModal();
    setTimeout(() => { o.focus(); o.select() }, 20);
  });
}

async function loadProjects() {
  let d; try { d = await (await fetch('/api/projects')).json(); } catch (e) { return; }
  // Nhãn PHIM/HOOK trên header đã bỏ 2026-08-09; vẫn giữ ở TIÊU ĐỀ TAB để phân biệt
  // khi mở nhiều board cùng lúc.
  document.title = (d.kind === 'hook' ? '[HOOK] ' : '[PHIM] ') + 'SF Board :' + d.port;
  $('#film').title = 'Cổng ' + d.port + ' · Chrome: ' + (d.cdp || []).join(', ');
}

async function load() {
  DATA = await (await fetch('/api/board')).json();
  MTIME = DATA.mtime || 0; DIRTY = false;
  $('#film').textContent = '· ' + (DATA.film || ''); render();
}
/* Khối LƯỢT CHỜ PHÂN LOẠI (dải ảnh chờ, gắn tay, kéo–thả sang thẻ) đã BỎ
   2026-08-09 theo yêu cầu user. TẠO ẢNH THEO LÔ vẫn nguyên: server vẫn tải ảnh
   về thư mục lượt và tự ghép vào SF; chỉ bỏ phần SẮP XẾP TAY khi ghép hụt.
   Đổi lại: lượt nào ghép hụt thì chạy lại SF đó, không vớt ảnh thủ công nữa. */
const PLDIR = 'cho-phan-loai';   // vẫn dùng trong tooltip 'ảnh này ra từ lượt nào'
let SPMODE = 'shot';             // chế độ của hộp #sfpick: 'shot' | 'ref'
/* CÔNG TẮC DÁN MÃ. Nút phải nói rõ trạng thái bằng CHỮ, không chỉ bằng màu:
   đây là thứ âm thầm đi vào từng tấm ảnh, nhìn nhầm là render cả loạt có nhãn
   rồi mới phát hiện lúc dựng video. */
let MAON = true;
function veMa() {
  const b = $('#mabtn'); if (!b) return;
  b.textContent = MAON ? '🔖 Mã SF: BẬT' : '🔖 Mã SF: tắt';
  b.classList.toggle('on', MAON);
  b.style.color = MAON ? 'var(--warn)' : '';
}
async function toggleMa() {
  const moi = !MAON;
  if (moi && !await hoi('Bật in mã SF vào ảnh?\n\nMã sẽ nằm ở GÓC DƯỚI BÊN TRÁI của mọi ảnh render từ giờ '
    + '— rất tiện khi một lượt trả về lệch số ảnh, nhìn là biết ảnh nào của thẻ nào.\n\n'
    + '⚠ Nhãn nằm TRONG ảnh, nên nó sẽ theo start frame vào video. Nhớ TẮT trước khi render bản cuối.')) return;
  const r = await (await fetch('/api/dan-ma?on=' + (moi ? 1 : 0), { method: 'POST' })).json();
  if (!r.ok) { bao('Không đổi được'); return }
  MAON = !!r.on; veMa();
  $('#runstatus').textContent = MAON
    ? 'đã BẬT in mã SF vào góc ảnh — nhớ tắt trước khi render bản cuối'
    : 'đã tắt in mã SF — ảnh render từ giờ sẽ sạch nhãn';
  setTimeout(() => $('#runstatus').textContent = '', 9000);
}
/* CHẠY HẾT ẢNH GỐC ĐỊA ĐIỂM — nếp cũ: xong toàn bộ ảnh gốc rồi mới tới khung con.
   Hỏi rõ trước khi chạy, vì thẻ đã có ảnh mà chưa duyệt thì chạy lại là ĐÈ. */
async function chayMaster() {
  const d = await (await fetch('/api/master', { method: 'POST' })).json();
  if (!d.ok) { bao('Không đọc được danh sách thẻ địa điểm'); return }
  if (!d.chua_anh.length && !d.chua_duyet.length) {
    bao(`Cả ${d.tong} thẻ địa điểm đều đã có ảnh và ĐÃ DUYỆT.\n\nKhông còn gì phải chạy.`);
    return
  }
  let lai = false;
  if (d.chua_anh.length) {
    if (!await hoi(`Chạy ảnh gốc cho ${d.chua_anh.length} thẻ địa điểm chưa có ảnh?\n\n`
      + d.chua_anh.join(' · ')
      + (d.chua_duyet.length ? `\n\n(${d.chua_duyet.length} thẻ khác đã có ảnh nhưng CHƯA DUYỆT — `
        + `bấm OK ở hộp kế tiếp nếu muốn chạy lại cả chúng.)` : ''))) return;
    if (d.chua_duyet.length)
      lai = await hoi(`Chạy lại luôn ${d.chua_duyet.length} thẻ đã có ảnh nhưng chưa duyệt?\n\n`
        + d.chua_duyet.join(' · ')
        + `\n\nBản cũ KHÔNG mất — nó vào dãy bản, bấm chọn lại được.\nBỏ qua thì bấm Cancel.`);
  } else {
    lai = await hoi(`Mọi thẻ địa điểm đều đã có ảnh, nhưng ${d.chua_duyet.length} thẻ CHƯA DUYỆT.\n\n`
      + d.chua_duyet.join(' · ') + `\n\nChạy lại chúng?\nBản cũ vào dãy bản, không mất.`);
    if (!lai) return;
  }
  const r = (await postJob('/api/master?chay=1' + (lai ? '&lai=1' : ''), newJobKey())).body;
  if (!r.ok) { bao(r.err || 'Không xếp được'); return }
  $('#runstatus').textContent = `đã xếp ${r.so} ảnh gốc địa điểm — có ảnh rồi mới chạy được khung con`;
  setTimeout(() => $('#runstatus').textContent = '', 10000);
}
/* ---- NGĂN KÉO HÀNG ĐỢI -------------------------------------------------
   Xếp việc theo ĐOẠN CHAT chứ không phải một danh sách id phẳng — vì đơn vị
   thật của việc tạo ảnh là đoạn chat, nhìn theo đó mới biết "đang vẽ ai, còn
   nợ nhóm nào". Nút dừng để ngay trong này để lúc nào cũng với tới được.  */
let QOPEN = false, QSEEN = {};   // QSEEN: id -> mốc thời gian thấy 'running' lần đầu
function toggleQueue(v) {
  QOPEN = (v === undefined) ? !QOPEN : !!v;
  $('#qdrawer').classList.toggle('on', QOPEN);
  $('#qbtn').classList.toggle('on', QOPEN);
  $('#qfab').classList.toggle('on', QOPEN);
  veHangDoi();
}
/* Esc và bấm ra ngoài đều đóng ngăn kéo — không phải rê lên tận nút ✕.
   Có dialog đang mở (lightbox) thì nhường Esc cho nó đóng trước. */
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape' || !QOPEN) return;
  if (document.querySelector('dialog[open]')) return;
  e.preventDefault(); toggleQueue(false);
});
document.addEventListener('mousedown', e => {
  if (!QOPEN) return;
  if (e.target.closest('#qdrawer,#qfab,#qbtn')) return;
  toggleQueue(false);
});
function veHangDoi() {
  const nay = Date.now();
  const dang = [], cho = [], loi = [], xong = [];
  for (const [id, j] of Object.entries(JOBS || {})) {
    if (id.startsWith('LO:')) continue;              // ident lô — đã rải cho từng SF
    if (j.state === 'running') { if (!QSEEN[id]) QSEEN[id] = nay; dang.push([id, j]) }
    else {
      delete QSEEN[id];
      if (j.state === 'queued') cho.push([id, j]);
      else if (j.state === 'error') loi.push([id, j]);
      else if (j.state === 'done') xong.push([id, j]);
    }
  }
  const n = dang.length + cho.length;
  const b = $('#qbtn');
  if (b) b.textContent = n ? `▤ Hàng đợi (${n})` : '▤ Hàng đợi';
  const fab = $('#qfab'), fabn = $('#qfabn');
  if (fab) { fab.classList.toggle('has', !!n); if (fabn) fabn.textContent = n > 99 ? '99+' : n }
  const tom = $('#qtom');
  if (tom) tom.textContent = n || loi.length || xong.length
    ? `${dang.length} đang chạy · ${cho.length} chờ`
      + (xong.length ? ` · ${xong.length} xong` : '')
      + (loi.length ? ` · ${loi.length} lỗi` : '')
    : 'không có việc nào';
  const don = $('#qdon');
  if (don) don.style.display = loi.length ? '' : 'none';
  const con = new Set([...dang, ...cho, ...loi, ...xong].map(x => x[0]));   // bỏ chọn id đã biến mất
  [...QTICK].forEach(i => { if (!con.has(i)) QTICK.delete(i) });
  qCapNhatChon();
  const _nl = $('#qn-live'), _nd = $('#qn-done'), _cl = $('#qclear');
  if (_nl) _nl.textContent = (dang.length + cho.length) || '';
  if (_nd) _nd.textContent = xong.length || '';
  if (_cl) _cl.style.display = (QVIEW === 'done' && xong.length) ? '' : 'none';
  if (!QOPEN) return;
  const MAU = { running: '#16a34a', queued: '#9ca3af', error: '#dc2626' };
  // XẾP THEO THỨ TỰ SẼ CHẠY, không gom theo địa điểm nữa (user chốt 2026-08-12).
  // Gom theo nhóm thì đọc được "còn nợ chỗ nào", nhưng KHÔNG trả lời được câu
  // hay phải hỏi hơn: "tới lượt tôi chưa?". Thứ tự lấy từ chính hàng đợi của
  // board, nên nó là thứ tự THẬT chứ không phải thứ tự bấm.
  cho.sort((a, b) => (qViTri(a[0]) + 1 || 9e9) - (qViTri(b[0]) + 1 || 9e9));
  const box = $('#qbody');
  if (!dang.length && !cho.length && !loi.length && !xong.length) {
    box.innerHTML = '<div class="hint" style="padding:10px 0">Hàng đợi trống — không có việc nào đang chạy hay đang chờ.</div>';
    return;
  }
  let h = '';
  // ---- ĐANG CHỜ: một TASK = một tin nhắn gửi đi, xong task 1 mới tới task 2.
  // Đơn vị này mới là thứ board thật sự chạy; liệt kê từng SF rời làm người đọc
  // tưởng chúng chạy lần lượt, trong khi cả nhóm đi chung MỘT lượt.
  if (QVIEW === 'live' && cho.length) {
    const theoTask = new Map();      // ident lô → [SF con đang chờ]
    const moCoi = [], choVid = [];
    // VIDEO KHÔNG CÓ TASK. Grok nhận một ảnh + một prompt mỗi lượt, nên mỗi
    // video là một việc rời — vẽ chúng theo khuôn task thì "Chạy hết video" của
    // cả phim đẻ ra 300 khối "Task N · 1 ảnh", vừa sai chữ vừa không đọc nổi.
    // Gom hết vào MỘT khối, liệt kê bằng chip như thành viên của một task.
    const dsVid = new Set(QHANG.video || []);
    for (const [id, j] of cho) {
      if (dsVid.has(id)) { choVid.push([id, j]); continue }
      const k = qViTri(id);
      if (k < 0) { moCoi.push([id, j]); continue }
      const key = [...(QHANG.anh || []), ...(QHANG.video || [])][k];
      if (!theoTask.has(key)) theoTask.set(key, []);
      theoTask.get(key).push([id, j]);
    }
    const dsTask = [...theoTask.entries()]
      .sort((a, b) => qViTri(a[1][0][0]) - qViTri(b[1][0][0]));
    h += `<div class="qg"><b>⏳ Đang chờ</b> <span class="hint">${dsTask.length} task`
      + `${choVid.length ? ' + ' + choVid.length + ' video' : ''}`
      + `${moCoi.length ? ' + ' + moCoi.length + ' mồ côi' : ''}</span>`
      + `<div class="hint" style="font-size:11px;margin:2px 0 6px">${esc(qViSao())}</div>`;
    dsTask.forEach(([key, ds], idx) => {
      const g = (QNHOM || {})[ds[0][0]] || {};
      const ghi = ds.map(([, j]) => j.msg).find(m => m && /gửi lại|chặn|thiếu/i.test(m));
      h += `<div class="qtask">
        <div class="qth"><span class="qstt">${idx + 1}</span>
          <b>Task ${idx + 1}</b>
          <span class="hint">${ds.length} ảnh${g.nhan ? ' · ' + esc(g.bieu_tuong || '') + ' ' + esc(g.nhan) : ''}</span>
          <span style="flex:1"></span>
          <span class="t">${idx === 0 ? 'kế tiếp' : 'sau ' + idx + ' task'}</span>
        </div>
        <div class="qtb">${ds.map(([id]) => `<span class="qsf" title="Huỷ ${esc(id)} khỏi task này"
             onclick="huyMotViec('${esc(id)}')">${esc(id)} ✕</span>`).join('')}</div>
        ${ghi ? `<div class="hint" style="font-size:11px;margin-top:3px">${esc(ghi.slice(0, 120))}</div>` : ''}
      </div>`;
    });
    if (choVid.length) {
      const thu = id => (QHANG.video || []).indexOf(id);
      choVid.sort((a, b) => (thu(a[0]) + 1 || 9e9) - (thu(b[0]) + 1 || 9e9));
      h += `<div class="qtask">
        <div class="qth"><span class="qstt">🎬</span>
          <b>Video</b>
          <span class="hint">${choVid.length} lượt Grok · chạy lần lượt, mỗi lượt TỐN CREDIT</span>
          <span style="flex:1"></span>
          <span class="t">${dsTask.length ? 'song song với ảnh' : 'kế tiếp'}</span>
        </div>
        <div class="qtb">${choVid.map(([id]) => `<span class="qsf" title="Huỷ ${esc(id)} khỏi hàng đợi"
             onclick="huyMotViec('${esc(id)}')">${esc(id)} ✕</span>`).join('')}</div>
      </div>`;
    }
    for (const [id, j] of moCoi)
      h += `<div class="qi" title="${esc(j.msg || '')}"><span class="d" style="background:#dc2626"></span>
        <span class="n">${esc(id)}</span><span class="t">mồ côi ⟳</span></div>`;
    h += '</div>';
  }
  // ---- TAB "✓ ĐÃ XONG": gom theo LƯỢT, để đọc được "task nào xong, về mấy ảnh".
  // Từng SF một thì 10 dòng cho một tin nhắn, và không thấy được lượt đó có trả
  // đủ hay không — mà đó mới là thứ cần theo dõi.
  if (QVIEW === 'done') {
    if (!xong.length) {
      box.innerHTML = '<div class="hint" style="padding:10px 0">Chưa có việc nào xong trong phiên này.'
        + '<br>Sổ này nằm trong bộ nhớ board — khởi động lại board là sạch.</div>';
      return;
    }
    const theoLuot = new Map();
    for (const [id, j] of xong) {
      const m = /lượt (\d+)/.exec(j.msg || '');
      const k = m ? +m[1] : 0;
      if (!theoLuot.has(k)) theoLuot.set(k, []);
      theoLuot.get(k).push([id, j]);
    }
    const ds = [...theoLuot.entries()].sort((a, b) => b[0] - a[0]);   // mới nhất lên đầu
    h += `<div class="qg"><b>✓ Đã xong</b> <span class="hint">${ds.length} lượt · ${xong.length} ảnh</span>`;
    for (const [luot, xs] of ds) {
      const g = (QNHOM || {})[xs[0][0]] || {};
      // "đã duyệt nên giữ bản cũ" = ảnh về nhưng KHÔNG thay ảnh chính. Đếm riêng,
      // nếu không con số "10 ảnh" nói dối là thẻ đã đổi ảnh.
      const giu = xs.filter(([, j]) => /đã duyệt/.test(j.msg || '')).length;
      h += `<div class="qi">
        <span class="d" style="background:#16a34a"></span>
        <span class="n">${luot ? `Lượt ${luot}` : 'Gắn tay'}
          <span class="hint">${g.nhan ? esc(g.bieu_tuong || '') + ' ' + esc(g.nhan) : ''}</span></span>
        <span class="t">${xs.length} ảnh${giu ? ` · ${giu} giữ bản cũ` : ''}</span></div>
        <div class="qtb">${xs.map(([id]) => `<span class="qsf" style="cursor:default">${esc(id)}</span>`).join('')}</div>`;
    }
    h += '</div>';
    box.innerHTML = h;
    return;
  }
  for (const [ten, ds, tt] of [['⏵ Đang chạy', dang, 'running'],
                               ['⚠ Lỗi', loi, 'error']]) {
    if (!ds.length) continue;
    h += `<div class="qg"><b>${esc(ten)}</b> <span class="hint">${ds.length} việc</span>`;
    let stt = 0;
    for (const [id, j] of ds) {
      stt++;
      const giay = QSEEN[id] ? Math.round((nay - QSEEN[id]) / 1000) : 0;
      // Việc ĐANG CHẠY không cắt được: thợ đang nằm trong lượt chờ ChatGPT vẽ,
      // chỉ "Dừng tất cả" (đóng Chrome) mới cắt nổi. Nên nút ✕ chỉ mở cho việc CHỜ.
      const nut = tt === 'queued'
        ? `<button class="sm" style="padding:0 6px;line-height:1.5"
         title="Huỷ riêng việc này — lô sẽ được xếp lại với các việc còn lại"
         onclick="huyMotViec('${esc(id)}')">✕</button>`
        : (tt === 'running'
          ? `<button class="sm" style="padding:0 6px;line-height:1.5"
             title="Dừng riêng việc này — bấm stop trên ChatGPT rồi bỏ chờ, KHÔNG đóng Chrome nên các việc khác vẫn chạy. Cả lô chứa nó sẽ dừng theo, vì một lô là một tin nhắn."
             onclick="dungMotViec('${esc(id)}')">■</button>`
          : `<button class="sm" style="padding:0 6px;line-height:1.5"
             title="Dọn dòng lỗi này khỏi danh sách — không đụng ảnh hay prompt"
             onclick="xoaLoi('${esc(id)}')">✕</button>`);
      const g = (QNHOM || {})[id] || {};
      // TÁCH NHÃN TÀI KHOẢN RA THÀNH CHIP RIÊNG. Board dán "[gpt-4 :9225]" vào
      // đầu mọi thông báo lỗi, nhưng nằm lẫn trong câu dài thì phải đọc mới thấy
      // — mà câu hỏi đầu tiên khi nhìn danh sách lỗi luôn là "cửa sổ nào".
      const _mtk = /^\[([^\]]+)\]\s*/.exec(j.msg || '');
      const _tk = _mtk ? _mtk[1] : '';
      const _msg = _mtk ? (j.msg || '').slice(_mtk[0].length) : (j.msg || '');
      h += `<div class="qi" title="${esc(j.msg || '')}">`
        + `<input type="checkbox" data-qt="${esc(id)}" ${QTICK.has(id) ? 'checked' : ''}
        onclick="qTick('${esc(id)}',this.checked)" style="flex:none;margin:0">`
        + `<span class="d" style="background:${MAU[tt]}"></span>`
        + `<span class="n">${esc(id)}${g.bieu_tuong ? ` <span class="hint">${esc(g.bieu_tuong)} ${esc(g.nhan || '')}</span>` : ''}</span>`
        + (tt === 'error' && _tk ? `<span class="qtk" title="Cửa sổ Chrome đã chạy việc này">${esc(_tk)}</span>` : '')
        + `<span class="t">${tt === 'running' ? (giay ? giay + 's' : '…') : 'lỗi'}</span>`
        + nut + `</div>`;
      if (tt === 'error' && _msg)
        h += `<div class="hint" style="font-size:11px;margin:-2px 0 4px 14px;color:#b45309">${esc(_msg.slice(0, 150))}</div>`;
    }
    h += '</div>';
  }
  box.innerHTML = h;
}

// ---- VÌ SAO ĐANG CHỜ ------------------------------------------------------
// Câu hỏi hay gặp nhất mà board cũ không trả lời được: "Chrome đang rảnh, sao
// việc vẫn nằm im?". Ba nguyên nhân thật, ba câu khác nhau — đoán mò một câu
// chung là vô dụng.
function qViSao() {
  const t = QTHO.img || { song: 0, ban: 0 };
  const v = QTHO.vid || { song: 0, ban: 0 };
  const ranh = Math.max(0, t.song - t.ban) + Math.max(0, v.song - v.ban);
  if (!t.song && !v.song) return 'KHÔNG có tab nào sống — bật tài khoản ở ⚙ Tài khoản.';
  const mo = [`ảnh ${t.ban}/${t.song} tab đang chạy`];
  if (v.song) mo.push(`video ${v.ban}/${v.song} tab`);
  return ranh
    ? `${mo.join(' · ')} — còn ${ranh} tab rảnh, việc đầu hàng sẽ được nhấc trong vài giây.`
    : `${mo.join(' · ')} — mọi tab đều bận, việc chờ tới lượt.`;
}

// Vị trí TASK chứa SF này trong hàng đợi thật, -1 nếu không có (= việc mồ côi:
// nhãn 'chờ' còn mà không ai nhặt nữa — người gác cứu trong 30 giây). Đây đúng
// là ca 'Chrome đang rảnh mà việc đứng im'.
// PHẢI DÒ CẢ IDENT LÔ: hàng đợi giữ "LO:sf1,sf2,…" (một lô là một tin nhắn),
// còn danh sách này hiện TỪNG SF. So thẳng tên SF với hàng là trượt hết, và
// mọi việc đang chờ bị gán nhầm là "mồ côi".
function qViTri(id) {
  const thuTu = [...(QHANG.anh || []), ...(QHANG.video || [])];
  const k = thuTu.indexOf(id);
  if (k >= 0) return k;
  return thuTu.findIndex(x => x.startsWith('LO:') && x.slice(3).split(',').includes(id));
}

/* CHỌN NHIỀU rồi xử một lượt — khúc giữa còn thiếu giữa "một cái" và "tất cả".
   Mỗi trạng thái cần một cách xử khác nhau nên gom vào đây, thay vì bắt user tự
   nhớ: đang chạy → dừng · đang chờ → huỷ · lỗi → dọn. */
// Ngăn kéo có hai tab: 'live' (đang chạy & chờ) · 'done' (sổ việc đã xong).
let QVIEW = 'live';

function qTab(v) {
  QVIEW = v;
  $('#qtab-live').classList.toggle('on', v === 'live');
  $('#qtab-done').classList.toggle('on', v === 'done');
  veHangDoi();
}

async function xoaXong() {
  const r = await (await fetch('/api/xoa-xong', { method: 'POST' })).json();
  await poll();
  $('#runstatus').textContent = `đã dọn ${r.bo || 0} dòng đã xong`;
  setTimeout(() => $('#runstatus').textContent = '', 4000);
}

let QTICK = new Set();
function qTick(id, on) { on ? QTICK.add(id) : QTICK.delete(id); qCapNhatChon() }
function qBoChon() { QTICK.clear(); const a = $('#qall'); if (a) a.checked = false; veHangDoi() }
function qChonHet(on) {
  QTICK.clear();
  if (on) document.querySelectorAll('#qbody input[data-qt]').forEach(e => QTICK.add(e.dataset.qt));
  veHangDoi();
}
function qCapNhatChon() {
  const n = QTICK.size, bar = $('#qbulk');
  if (bar) { bar.style.display = n ? 'flex' : 'none'; $('#qseln').textContent = `${n} việc đã chọn` }
}
async function xuLyDaChon() {
  if (!QTICK.size) return;
  const ds = [...QTICK], dem = { chay: 0, cho: 0, loi: 0 };
  ds.forEach(i => {
    const st = (JOBS[i] || {}).state;
    if (st === 'running') dem.chay++; else if (st === 'queued') dem.cho++; else dem.loi++
  });
  if (!await hoi(`Xử ${ds.length} việc đã chọn?\n\n`
    + `· ${dem.chay} đang chạy → DỪNG (bấm stop trên ChatGPT; cả lô chứa nó dừng theo)\n`
    + `· ${dem.cho} đang chờ → HUỶ (lô còn lại tự xếp lại)\n`
    + `· ${dem.loi} dòng lỗi → DỌN khỏi danh sách\n\n`
    + `Chrome KHÔNG bị đóng, các việc khác vẫn chạy.`)) return;
  let ok = 0; const hong = [];
  for (const id of ds) {
    const st = (JOBS[id] || {}).state;
    const u = st === 'running' ? '/api/dung-viec?' + jobQuery(id)
      : st === 'queued' ? '/api/huy-viec?' + jobQuery(id)
        : '/api/xoa-loi?sf=' + encodeURIComponent(id);
    try {
      const r = await (await fetch(u, { method: 'POST' })).json();
      r.ok ? ok++ : hong.push(id + ': ' + (r.err || '?'))
    }
    catch (e) { hong.push(id + ': ' + e) }
  }
  QTICK.clear(); const a = $('#qall'); if (a) a.checked = false;
  $('#runstatus').textContent = `đã xử ${ok}/${ds.length} việc`
    + (hong.length ? ` · ${hong.length} không xử được` : '');
  setTimeout(() => $('#runstatus').textContent = '', 9000);
  if (hong.length) bao('Không xử được:\n\n' + hong.slice(0, 6).join('\n'));
  veHangDoi();
}
async function xoaLoi(id) {
  const u = id ? '/api/xoa-loi?sf=' + encodeURIComponent(id) : '/api/xoa-loi?het=1';
  const r = await (await fetch(u, { method: 'POST' })).json();
  if (!r.ok) { bao(r.err || 'Không dọn được'); return }
  if (!id) {
    $('#runstatus').textContent = `đã dọn ${r.bo} dòng lỗi`;
    setTimeout(() => $('#runstatus').textContent = '', 5000)
  }
  await poll();
}
async function dungMotViec(id) {
  if (!await hoi(`Dừng riêng "${id}"?\n\nCả lô chứa nó sẽ dừng theo — một lô là MỘT tin nhắn nên không cắt đôi được.\nChrome KHÔNG bị đóng, các việc khác vẫn chạy bình thường.`)) return;
  const r = await (await fetch('/api/dung-viec?' + jobQuery(id), { method: 'POST' })).json();
  if (!r.ok) { bao(r.err || 'Không dừng được'); return }
  $('#runstatus').textContent = `đang dừng ${id}…`;
  setTimeout(() => $('#runstatus').textContent = '', 7000);
}
async function huyMotViec(id) {
  const r = await (await fetch('/api/huy-viec?' + jobQuery(id),
    { method: 'POST' })).json();
  if (!r.ok) { bao(r.err || 'Không huỷ được'); return }
  $('#runstatus').textContent = `đã huỷ ${id}` + (r.con_lai ? ` · xếp lại lô ${r.con_lai} ảnh còn lại` : '');
  setTimeout(() => $('#runstatus').textContent = '', 7000);
  veHangDoi();
}
let QNHOM = {}, QHANG = {}, QTHO = {};
// Dấu vết từng việc: ident -> [{luc,state,msg,tk,lan,giay}, …]. JOBS chỉ giữ
// trạng thái HIỆN TẠI, nên không có cái này thì không soi lại được một việc
// đã đi qua những đâu và hỏng ở bước nào.
let VET = {}, VET_MO = '';
async function poll() {
  const r = await (await fetch('/api/jobs')).json();
  const j = jobsTuLifecycle(r.lifecycle, r.jobs || {});
  for (const [id, pending] of Object.entries(SUBMITTING)) {
    if (pending.job_id && (j[id] || {}).job_ids?.includes(pending.job_id)) {
      delete SUBMITTING[id];
    }
  }
  QNHOM = r.nhom || {}; QHANG = r.hang || {}; QTHO = r.tho || {}; VET = r.vet || {};
  const a = r.auto || {};
  const changed = JSON.stringify(j) !== JSON.stringify(JOBS) || JSON.stringify(a) !== JSON.stringify(AUTO);
  AUTO = a;
  veChayHetPhim();
  const wasRunning = Object.values(JOBS).some(x => x.state === 'running');
  JOBS = j;
  veHangDoi();          // cập nhật số trên nút + nội dung ngăn kéo mỗi vòng poll
  if (r.dan_ma !== undefined && !!r.dan_ma !== MAON) { MAON = !!r.dan_ma; veMa() }
  if (r.auto_vid !== undefined && !!r.auto_vid !== AVON) { AVON = !!r.auto_vid; veAutoVid() }
  // Sổ lỗi: chỉ kéo phần mới khi tổng bên server đã nhích lên.
  if ((r.loi || 0) > LOI_N) { await napLoi(); veLoi() }
  HTAC = { ht: (r.pl || {}).ht || 0, ht_cuoi: (r.pl || {}).ht_cuoi || '' };
  if (changed) {
    const nowRunning = Object.values(j).some(x => x.state === 'running');
    if (wasRunning && !nowRunning) { await load(); return } else { render() }
  }
  // file bị sửa từ bên ngoài (AI cập nhật prompt/kịch bản) → nạp lại
  if (r.mtime && r.mtime !== MTIME && !DIRTY) {
    await load();
    $('#save').textContent = 'đã đồng bộ ↻'; $('#save').className = 'save on';
    setTimeout(() => $('#save').textContent = '', 2200);
  }
}
setInterval(poll, 1500);

// ---------------------------------------------------------------- hộp lỗi
// Mọi WARNING/ERROR của board và của executor đổ vào đây. Lý do có hộp này:
// những lỗi cần nhìn nhất (selector chết, ERR_QUIC, tab kẹt trang post) chỉ nằm
// trong Terminal, mà thẻ trên board chỉ hiện đúng một dòng tóm tắt cụt — không
// đủ để sửa, và mất sạch khi đóng cửa sổ chạy board.
let LOI = [], LOI_N = 0, LOI_OPEN = false;

// LỖI JS CỦA CHÍNH GIAO DIỆN cũng vào hộp. Không có hai dòng này thì mọi lỗi
// script chỉ nằm trong Console của trình duyệt — user không mở, nên "board đứng
// im, bấm không ăn" biến thành triệu chứng không dấu vết.
addEventListener('error', e => {
  LOI.push({
    n: 0, luc: new Date().toTimeString().slice(0, 8), muc: 'UI', nguon: 'board.js',
    text: `${e.message} @ ${(e.filename || '').split('/').pop()}:${e.lineno}`
  });
  veLoi();
});
addEventListener('unhandledrejection', e => {
  const raw = String((e.reason && (e.reason.stack || e.reason.message)) || e.reason);
  // "Failed to fetch" = board vừa tắt/khởi động lại, vòng poll sau tự nối lại.
  // Không phải bug, mà mỗi lần restart nó đẻ ra cả chục dòng kèm stack trỏ vào
  // chrome-extension:// — thứ chẳng liên quan gì tới board, đọc chỉ tổ rối.
  if (/failed to fetch|networkerror|load failed/i.test(raw)) return;
  LOI.push({
    n: 0, luc: new Date().toTimeString().slice(0, 8), muc: 'UI', nguon: 'promise',
    // Chỉ giữ DÒNG ĐẦU: stack nhiều tầng đẩy mọi lỗi khác ra khỏi hộp, mà dòng
    // đầu đã đủ để biết hỏng ở đâu.
    text: raw.split('\n')[0].slice(0, 200)
  });
  veLoi();
});

async function napLoi() {
  try {
    const r = await (await fetch('/api/loi?tu=' + LOI_N)).json();
    for (const m of (r.loi || [])) { LOI.push(m); LOI_N = Math.max(LOI_N, m.n) }
    if (LOI.length > 800) LOI = LOI.slice(-800);
  } catch (e) { /* board tắt giữa chừng — vòng poll sau thử lại */ }
}

function toggleLoi() {
  LOI_OPEN = !LOI_OPEN;
  $('#loipanel').style.display = LOI_OPEN ? 'block' : 'none';
  $('#loibtn').classList.toggle('on', LOI_OPEN);
  if (LOI_OPEN) veLoi();
}

// BA NGUỒN, gộp làm một danh sách — hộp này phải là chỗ DUY NHẤT cần nhìn:
//   · log server  (WARNING/ERROR của board và executor, có giờ)
//   · job đang lỗi (thứ user thấy trên thẻ; nhiều chỗ đặt trạng thái lỗi mà
//     không kèm log, nên chỉ đọc log server là hụt đúng phần hay hỏng nhất)
//   · lỗi JS của chính giao diện (xem LOI_UI bên dưới)
function loiTatCa() {
  const ra = LOI.slice();
  // `typeof` chứ không đọc thẳng: hộp lỗi phải chạy được cả khi lỗi JS nổ ra
  // TRƯỚC lúc board kịp khởi tạo xong — đó đúng là lúc cần nó nhất.
  for (const [id, j] of Object.entries(typeof JOBS === 'undefined' ? {} : (JOBS || {}))) {
    if (j.state !== 'error') continue;
    const phu = [j.tk ? `tk ${j.tk}` : '', (j.lan || 0) > 1 ? `lần ${j.lan}` : '',
                 j.giay ? `${j.giay}s` : ''].filter(Boolean).join(' · ');
    ra.push({
      n: 0, luc: j.luc || '', muc: 'JOB', nguon: id,
      text: `${id}: ${j.msg || ''}${phu ? '   [' + phu + ']' : ''}`,
    });
  }
  return ra;
}

function loiLoc() {
  const t = (($('#loitim') || {}).value || '').toLowerCase().trim();
  const nang = (($('#loinang') || {}).checked) || false;
  return loiTatCa().filter(m => (!nang || m.muc === 'ERROR' || m.muc === 'CRITICAL' || m.muc === 'UI')
    && (!t || (m.text + ' ' + m.nguon).toLowerCase().includes(t)));
}

function veLoi() {
  const tong = loiTatCa().length;
  const badge = $('#loin');
  if (badge) { badge.textContent = tong || ''; badge.className = tong ? 'qn on' : 'qn' }
  if (!LOI_OPEN || !$('#loibody')) return;
  const ds = loiLoc();
  $('#loimeta').textContent = `${ds.length}/${tong} dòng`
    + (LOI.length >= 800 ? ' · chỉ giữ 800 dòng log gần nhất' : '');
  // Mới nhất LÊN ĐẦU: lỗi vừa xảy ra là lỗi đang cần đọc, đừng bắt cuộn xuống đáy.
  $('#loibody').innerHTML = ds.length
    ? ds.slice().reverse().map(m => veLoiDong(m)).join('')
    : '<div class="hint" style="padding:10px">Chưa có lỗi nào. Sạch.</div>';
}

// Một dòng trong hộp 🐞. Dòng JOB bấm được: mở ra SỔ DẤU VẾT của việc đó —
// nó đã xếp hàng lúc nào, chạy trên tài khoản nào, hỏng ở lần thử thứ mấy, mỗi
// chặng mất bao lâu. Dòng WARNING là nhật ký một thời điểm, không có gì để mở.
function veLoiDong(m) {
  const nang = m.muc === 'ERROR' || m.muc === 'CRITICAL';
  const co_vet = m.muc === 'JOB' && (VET[m.nguon] || []).length;
  const mo = VET_MO === m.nguon;
  const dau = co_vet ? `<span class="loivet">${mo ? '▾' : '▸'}</span>` : '';
  let ra = `<div class="loirow ${nang ? 'nang' : ''} ${co_vet ? 'bam' : ''}"`
    + (co_vet ? ` onclick="moVet('${esc(m.nguon)}')"` : '') + `>
      <span class="loiluc">${esc(m.luc)}</span>
      <span class="loimuc">${esc(m.muc)}</span>
      <span class="loitext">${dau}${esc(m.text)}</span></div>`;
  if (mo && co_vet) ra += veVet(m.nguon);
  return ra;
}

function veVet(id) {
  const d = VET[id] || [];
  const NHAN = { queued: 'xếp hàng', running: 'đang chạy', done: 'xong', error: 'LỖI' };
  return `<div class="vetbox">` + d.map((v, i) => {
    const truoc = d[i - 1];
    // Khoảng cách tới chặng trước — chỗ này mới cho biết việc NẰM CHỜ bao lâu,
    // thứ mà tổng thời gian chạy không nói ra.
    const cach = truoc ? khoangGio(truoc.luc, v.luc) : '';
    return `<div class="vetrow ${v.state === 'error' ? 'nang' : ''}">
      <span class="vetluc">${esc(v.luc)}</span>
      <span class="vetst st-${esc(v.state || '')}">${esc(NHAN[v.state] || v.state || '')}</span>
      <span class="vetphu">${v.lan > 1 ? 'lần ' + v.lan + ' · ' : ''}${v.giay ? v.giay + 's · ' : ''}${cach ? '+' + cach + ' · ' : ''}${esc(v.tk || '')}</span>
      <span class="vetmsg">${esc(v.msg || '')}</span></div>`;
  }).join('') + `</div>`;
}

// '15:01:54' - '14:58:52' → '3m02s'. Chỉ có giờ-phút-giây nên qua nửa đêm sẽ
// âm; kẹp về 0 thay vì in số vô nghĩa — không ai soi log qua mốc nửa đêm.
function khoangGio(a, b) {
  const g = t => { const p = (t || '').split(':').map(Number); return p.length === 3 ? p[0] * 3600 + p[1] * 60 + p[2] : NaN };
  const d = g(b) - g(a);
  if (!isFinite(d) || d <= 0) return '';
  return d < 60 ? d + 's' : Math.floor(d / 60) + 'm' + String(d % 60).padStart(2, '0') + 's';
}

function moVet(id) { VET_MO = (VET_MO === id ? '' : id); veLoi() }

async function loiCopy() {
  const ds = loiLoc();
  // Chép KÈM dấu vết của việc lỗi — dán vào chat để nhờ soi thì thiếu đúng
  // phần lịch sử là người đọc lại phải hỏi ngược "nó thử mấy lần, tài khoản nào".
  const txt = ds.map(m => {
    let t = `${m.luc || '--:--:--'} ${m.muc} [${m.nguon}] ${m.text}`;
    for (const v of (m.muc === 'JOB' ? (VET[m.nguon] || []) : [])) {
      t += `\n      ${v.luc} ${v.state}${v.lan > 1 ? ' lần ' + v.lan : ''}`
        + `${v.giay ? ' ' + v.giay + 's' : ''}${v.tk ? ' [' + v.tk + ']' : ''} ${v.msg || ''}`;
    }
    return t;
  }).join('\n');
  try {
    await navigator.clipboard.writeText(txt);
    const b = $('#loicopy'); const cu = b.textContent;
    b.textContent = `✓ đã chép ${ds.length} dòng`;
    setTimeout(() => b.textContent = cu, 1800);
  } catch (e) { bao('Không chép được vào clipboard:\n' + e) }
}

async function loiXoa() {
  if (!await hoi('Dọn sổ lỗi trên board?\n\nChỉ xoá danh sách đang xem — log trong Terminal vẫn còn.')) return;
  await fetch('/api/loi-xoa', { method: 'POST' });
  LOI = []; veLoi();
}

// ---------------------------------------------------------------- accounts
let ACCT_OPEN = false, ACCT_TIMER = null, ACCT_TAB = 'img';
function acctTab(k) {
  ACCT_TAB = k;
  $('#atab-img').classList.toggle('on', k === 'img');
  $('#atab-vid').classList.toggle('on', k === 'vid');
  // Trần "tối đa N" chỉ đếm tài khoản ẢNH (_so_tk_doc bên board), nên chỉ hiện
  // ở tab ChatGPT — để nó nằm cạnh danh sách Grok là nói dối người đọc.
  $('#sotkwrap').style.display = k === 'img' ? 'flex' : 'none';
  $('#acctadd').textContent = k === 'img' ? '+ ChatGPT' : '+ Grok';
  pollAccts();
}
function toggleAccts() {
  ACCT_OPEN = !ACCT_OPEN;
  $('#acctpanel').style.display = ACCT_OPEN ? 'block' : 'none';
  $('#acctbtn').classList.toggle('on', ACCT_OPEN);
  if (ACCT_OPEN) { pollAccts(); ACCT_TIMER = setInterval(pollAccts, 4000) }
  else if (ACCT_TIMER) { clearInterval(ACCT_TIMER); ACCT_TIMER = null }
}
async function datSoTK(n) {
  const r = await (await fetch('/api/so-tk?n=' + encodeURIComponent(n), { method: 'POST' })).json();
  const o = $('#sotk'); if (o) o.value = r.so;
  $('#runstatus').textContent = `trần ${r.so} tài khoản ChatGPT chạy cùng lúc`;
  setTimeout(() => $('#runstatus').textContent = '', 5000);
  pollAccts();
}

async function pollAccts() {
  try {
    const r = await (await fetch('/api/accounts')).json();
    // Ô "chạy cùng lúc" chỉ nạp giá trị khi user KHÔNG đang gõ vào nó — nếu
    // không, mỗi vòng poll 4 giây lại giật con số về giá trị cũ.
    const _o = $('#sotk');
    if (_o && document.activeElement !== _o) {
      fetch('/api/so-tk').then(x => x.json()).then(d => { if (document.activeElement !== _o) _o.value = d.so });
    }
    // Đếm trên TOÀN BỘ danh sách rồi mới lọc — số trên tab phải là số thật của
    // loại đó, không phải số của cái đang hiện.
    const tat = r.accounts || [];
    const dem = k => tat.filter(a => a.kind === k).length;
    const dem_on = k => tat.filter(a => a.kind === k && a.enabled).length;
    $('#atab-img').innerHTML = `ChatGPT <span class="an">${dem_on('img')}/${dem('img')}</span>`;
    $('#atab-vid').innerHTML = `Grok <span class="an">${dem_on('vid')}/${dem('vid')}</span>`;
    const rows = tat.filter(a => a.kind === ACCT_TAB).map(a => {
      const dot = !a.enabled ? '⚫' : a.dead ? '🌙' : a.chrome ? '🟢' : '🟡';
      const kind = a.kind === 'img' ? 'ChatGPT · ảnh' : 'Grok · video';
      // NGHỈ TỚI MẤY GIỜ — ChatGPT có nói giờ mở lại trong thông báo chặn, board
      // đã bắt và lưu; trước đây chỉ nằm trong log nên nhìn giao diện chỉ thấy
      // "hết lượt" mà không biết chờ bao lâu, và ai cũng bấm "Thử lại" vô ích.
      let _nghi = '';
      if (a.nghi_den) {
        const con = Math.max(0, Math.round((a.nghi_den * 1000 - Date.now()) / 60000));
        const gio = new Date(a.nghi_den * 1000).toTimeString().slice(0, 5);
        _nghi = ` <b style="color:var(--warn)">· nghỉ đến ${gio}`
          + (con ? ` (còn ${con >= 60 ? Math.floor(con / 60) + 'h' + (con % 60 ? (con % 60) + 'p' : '') : con + ' phút'})` : ' — sắp mở lại')
          + '</b>';
      }
      // MỘT DÒNG TRẠNG THÁI, MỘT NÚT. Trước đây có cả "Bật/Tắt" lẫn "Mở Chrome"
      // và không ai phân biệt nổi: Tắt vốn đã đóng Chrome, Bật vốn đã mở Chrome.
      // Nút "Mở Chrome" chỉ MỞ THÊM chứ không kill cái đang treo, nên đúng lúc
      // cổng treo thì nó vô dụng — đường chữa thật xưa nay vẫn là Tắt rồi Bật.
      // Board tự mở lại Chrome khi tài khoản đang bật mà cửa sổ chết, nên không
      // còn việc gì cho nút đó nữa.
      const st = !a.enabled
        ? (a.auto_off
          ? '<span style="color:var(--tx2)">⚫ tắt — chờ tới lượt trong vòng xoay</span>'
          : '<span style="color:var(--tx2)">⚫ tắt</span>')
        : a.dead ? `<span style="color:var(--bad)">${esc(a.dead)}</span>${_nghi}`
          : !a.chrome ? '<span style="color:var(--warn)">🟡 đang mở Chrome…</span>'
            : a.worker ? '<span style="color:var(--ok)">🟢 đang chạy</span>'
              : '<span style="color:var(--tx2)">🟡 chờ thợ…</span>';
      return `<div class="acctrow">
    <span>${dot}</span>
    ${/* TÊN GỌI RIÊNG do user đặt (email, gói, ghi chú…). Bỏ trống thì ô hiện
         chính `id` làm gợi ý. `id` KHÔNG đổi theo: nó nằm trong log và trong
         tên thư mục profile, đổi là đứt hết dấu vết cũ — nên nó vẫn được in ra
         ở cột kế bên để đối chiếu với log. */''}
    <input class="aten" value="${esc(a.ten || '')}" placeholder="${esc(a.id)}" maxlength="40"
           title="Tên gọi riêng để bạn dễ nhận ra tài khoản — ví dụ email hoặc gói đang dùng.&#10;Bỏ trống để quay về tên mặc định.&#10;Mã ${esc(a.id)} không đổi: log và thư mục profile vẫn dùng nó."
           onchange="acctTen(${a.port},this.value)">
    <span class="ak" title="${kind} — mã dùng trong log">${esc(a.id)}</span>
    <span class="ap">:${a.port}</span>
    <span class="as">${st}</span>
    <span class="ad" title="Số bản tài khoản này làm XONG hôm nay, và kỷ lục cao nhất từng đạt${a.ky_luc_ngay ? ' (ngày ' + esc(a.ky_luc_ngay) + ')' : ''}.&#10;ChatGPT/Grok không công bố trần mỗi ngày — cứ chạy tới lúc bị chặn thì con số 'cao nhất' chính là trần thật.">hôm nay <b style="color:var(--acc)">${a.hom_nay || 0}</b>${a.ky_luc ? ` · cao nhất <b style="color:var(--tx)">${a.ky_luc}</b>` : ''}</span>
    <label title="Số tab chạy ĐỒNG THỜI trên cùng cửa sổ Chrome này.&#10;1 = chạy tuần tự từng việc (mặc định).&#10;Tăng lên để tạo nhiều video/ảnh song song trên CÙNG một tài khoản.&#10;Càng nhiều tab càng tốn RAM — tăng dần và xem máy có chịu nổi không."
           class="at">tab
      <input type="number" min="1" max="6" value="${a.tabs || 1}" style="width:44px"
             onchange="acctTabs(${a.port},this.value)">

    </label>
    <span class="anut">
      ${a.dead ? `<button onclick="acctOp('revive',${a.port})" title="Bỏ dấu chặn và mở lại Chrome ngay, không đợi hết giờ nghỉ">Thử lại</button>` : ''}
      ${/* CÔNG TẮC, KHÔNG PHẢI NÚT CHỮ. Nút chữ ghi HÀNH ĐỘNG ("Tắt") nằm cạnh
           cột ghi TRẠNG THÁI ("đang chạy") đọc lướt như hai thứ mâu thuẫn nhau.
           Công tắc thì bản thân nó vừa là trạng thái vừa là chỗ bấm. */''}
      <label class="sw" title="${a.enabled ? 'Đang bật — gạt để TẮT: đóng cửa sổ Chrome và ngừng nhận việc.' : 'Đang tắt — gạt để BẬT: mở cửa sổ Chrome và đưa vào vòng chạy.'}&#10;Cửa sổ Chrome đi theo công tắc này, không còn nút mở riêng.&#10;Chrome treo hay chết giữa chừng thì board tự mở lại; gạt tắt rồi bật là cách dọn dứt điểm.">
        <input type="checkbox" ${a.enabled ? 'checked' : ''} onchange="acctOp('toggle',${a.port})"><i></i></label>
      <button class="bad-b" title="Xóa hẳn tài khoản này khỏi danh sách (dữ liệu đăng nhập trong profile Chrome vẫn giữ)" onclick="acctDel('${esc(a.id)}',${a.port},${a.enabled})">🗑</button>
    </span>
  </div>`});
    // ĐANG GÕ THÌ ĐỪNG VẼ LẠI. Vòng poll 4 giây thay sạch innerHTML, nên nó
    // nuốt luôn chữ user đang gõ dở trong ô tên (và cả ô số tab). Chỉ hoãn một
    // nhịp, vòng sau vẽ bình thường.
    // Ô trần ref đọc từ CÙNG một lần gọi, khỏi thêm nhịp mạng. Không ghi đè
    // khi user đang gõ dở — cùng lý do với ô tên và ô số tab bên dưới.
    const _tr = $('#tranref');
    if (_tr && r.tran_ref && document.activeElement !== _tr) _tr.value = r.tran_ref;
    if ($('#acctrows').contains(document.activeElement)) return;
    $('#acctrows').innerHTML = rows.join('')
      || `<span class="hint">chưa có tài khoản ${ACCT_TAB === 'img' ? 'ChatGPT' : 'Grok'} nào</span>`;
  } catch (e) { }
}
async function acctTen(port, v) {
  await fetch(`/api/acct?op=ten&port=${port}&v=${encodeURIComponent(v)}`, { method: 'POST' });
  setTimeout(pollAccts, 400);
}
async function datTranRef(n) {
  await fetch(`/api/acct?op=tran-ref&n=${n}`, { method: 'POST' });
  setTimeout(pollAccts, 400);
}
async function acctTabs(port, n) {
  await fetch(`/api/acct?op=tabs&port=${port}&n=${n}`, { method: 'POST' });
  setTimeout(pollAccts, 400);
}
async function acctOp(op, port) {
  await fetch(`/api/acct?op=${op}&port=${port}`, { method: 'POST' });
  setTimeout(pollAccts, 400);
}
async function acctDel(id, port, enabled) {
  const busy = enabled ? `\n\n⚠ Tài khoản này ĐANG BẬT và có thể đang chạy việc dở.` : '';
  if (!await hoi(
    `XÓA HẲN tài khoản ${id}?` + busy +
    `\n\nSẽ xóa LUÔN thư mục profile Chrome:` +
    `\n· mất phiên đăng nhập, lần sau phải đăng nhập lại` +
    `\n· KHÔNG hoàn tác được`
  )) return;
  const r = await (await fetch(`/api/acct?op=del&port=${port}`, { method: 'POST' })).json();
  if (r.err) bao('Đã xóa tài khoản, nhưng không xóa được profile:\n' + r.err);
  else if (r.freed) $('#runstatus').textContent = `đã xóa ${id} · giải phóng ${r.freed}`;
  setTimeout(pollAccts, 400);
  setTimeout(() => $('#runstatus').textContent = '', 5000);
}
async function acctAdd(kind) {
  await fetch(`/api/acct?op=add&kind=${kind}`, { method: 'POST' });
  setTimeout(pollAccts, 600);
}

function save() {
  DIRTY = true; clearTimeout(T); $('#save').textContent = 'đang lưu…'; $('#save').className = 'save';
  T = setTimeout(async () => {
    const r = await (await fetch('/api/board', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(DATA)
    })).json();
    if (r.mtime) MTIME = r.mtime;
    DIRTY = false;
    $('#save').textContent = 'đã lưu ✓'; $('#save').className = 'save on';
    setTimeout(() => $('#save').textContent = '', 1600);
  }, 450);
}
const allSF = () => DATA.scenes.flatMap(s => s.sfs.map(f => ({ sc: s, f })));
const find = id => allSF().find(x => x.f.id === id);

function allShots() { return DATA.scenes.flatMap(s => (s.shots || []).map(x => ({ sc: s, sh: x }))) }

function stats() {
  if (VIEW === 'sf') {
    const a = allSF().map(x => x.f), c = k => a.filter(f => f.status === k).length;
    $('#stats').innerHTML = aiChip() + `<span class="chip ok">Duyệt ${c('approved')}</span>
 <span class="chip warn">Sửa ${c('revise')}</span><span class="chip pend">Chờ ${c('proposed')}</span>
 <span class="chip bad">Loại ${c('rejected')}</span><span class="chip">Tổng ${a.length}</span>`;
  } else {
    const sh = allShots().map(x => x.sh);
    const has = sh.filter(s => s.video).length;
    const ok = sh.filter(s => s.vstatus === 'approved').length;
    // THỜI LƯỢNG: đã có video / tổng kịch bản. Trước đây chỉ đếm phần ĐÃ DUYỆT
    // nên con số đứng im suốt lúc dựng, không nói được tiến độ.
    const gy = x => x.reduce((a, s) => a + (s.dur || 10), 0);
    const secs = gy(sh.filter(s => s.video)), secsAll = gy(sh);
    const st = sh.filter(stale).length;
    $('#stats').innerHTML = aiChip() + `<span class="chip ok">Video duyệt ${ok}</span>
 <span class="chip pend">Có video ${has}</span><span class="chip">Tổng shot ${sh.length}</span>
 <span class="chip" title="Thời lượng đã có video / tổng thời lượng kịch bản">${mmss(secs)} / ${mmss(secsAll)} phim</span>
 ${st ? `<span class="chip" style="background:#fef3c7;border-color:#fcd34d;color:#b45309;font-weight:600"
   title="Có ${st} video mà lời thoại đã sửa sau khi prompt được viết — bảo AI viết lại prompt cho khớp">⚠ ${st} prompt lệch thoại</span>` : ''}`;
  }
}

function aiReqs() {
  const out = [];
  allSF().forEach(x => { if (x.f.ai_request) out.push({ kind: 'SF', id: x.f.id, note: x.f.notes || '' }) });
  allShots().forEach(x => { if (x.sh.ai_request) out.push({ kind: 'VIDEO', id: x.sh.id, note: x.sh.notes || '' }) });
  return out;
}
function aiChip() {
  const n = aiReqs().length;
  return n ? `<span class="chip ai" onclick="showAI()" title="Bấm để copy danh sách gửi AI">🤖 ${n} yêu cầu cho AI</span>`
    + `<span class="chip" onclick="clearAI()" style="cursor:pointer"
  title="Đã xử lý xong đợt này — bỏ cờ 🤖 của tất cả, giữ nguyên ghi chú">✕ dọn yêu cầu</span>`: '';
}
function showAI() {
  const r = aiReqs();
  const txt = r.map(x => `${x.kind} ${x.id}: ${x.note || '(chưa ghi chú)'}`).join('\n');
  navigator.clipboard.writeText(txt);
  bao('Đã copy ' + r.length + ' yêu cầu:\n\n' + txt +
    '\n\nDán vào chat, hoặc nhắn AI \"xử lý yêu cầu trên bảng\".' +
    '\n\nXong việc thì bấm nút \"✕ dọn yêu cầu\" cạnh chip để bỏ cờ 🤖 hàng loạt.');
}
// Dọn cờ 🤖 hàng loạt — làm xong một đợt thì bỏ hết cờ cũ để đánh dấu đợt mới,
// không phải bấm tay từng thẻ. KHÔNG đụng tới ô ghi chú.
async function clearAI() {
  const r = aiReqs();
  if (!r.length) return;
  if (!await hoi('Bỏ cờ 🤖 của ' + r.length + ' mục đã đánh dấu?\n\n' +
    'Ô ghi chú GIỮ NGUYÊN, chỉ bỏ dấu "cần AI xử lý".')) return;
  allSF().forEach(x => { if (x.f.ai_request) { delete x.f.ai_request; delete x.f.ai_done } });
  allShots().forEach(x => { if (x.sh.ai_request) { delete x.sh.ai_request; delete x.sh.ai_done } });
  save(); render();
}


function allShotsOrdered() {
  return DATA.scenes.flatMap(sc => (sc.shots || []).map(sh => ({ sc, sh })));
}


// "▶ Chạy tuần tự" ĐÃ BỎ 2026-08-12 (user chốt). Nó chạy TỪNG ẢNH MỘT — mỗi ảnh
// một tin nhắn, không gửi `luatchung`, không gom lô — nên vừa chậm vừa cho ảnh
// mất neo bối cảnh. Thay bằng "▶▶ Chạy hết phim" (tự chia task 10 ảnh cùng địa
// điểm) và các nút T1/T2 để chạy tay từng task.


// Nút "🎬 Xuất CapCut" và "+ Thêm scene" đã BỎ 2026-08-09 theo yêu cầu user.
// API /api/export-capcut phía server vẫn còn, gọi tay được nếu cần.

// ══ THANH NHẢY SCENE (trái) ══ mỗi scene một dòng + % ĐÃ DUYỆT của chế độ đang xem.
// Chế độ Kịch bản đếm video đã duyệt (vstatus), chế độ Start frames đếm SF đã duyệt.
function nguoiRef(id) {
  const m = /^REF_([A-Z0-9]+)_/.exec(id || '');
  return m ? m[1] : (id || '');
}
function chiaRef(list, nguonThuTu = list) {
  const nhanVat = list.filter(f => /_(PORTRAIT|FULL)$/.test(f.id || ''));
  const tapNhanVat = new Set(nhanVat);
  const daoCu = list.filter(f => !tapNhanVat.has(f) && (f.id || '').startsWith('REF_PROP_'));
  const tapDaoCu = new Set(daoCu);
  const boiCanh = list.filter(f => !tapNhanVat.has(f) && !tapDaoCu.has(f));
  const portraits = nguonThuTu.filter(f => (f.id || '').endsWith('_PORTRAIT'));
  const thuTu = new Map();
  portraits.forEach(f => {
    const ten = nguoiRef(f.id);
    if (!thuTu.has(ten)) thuTu.set(ten, thuTu.size);
  });
  return { nhanVat, daoCu, boiCanh, thuTu };
}
function tienDoRef(items) {
  const n = items.length;
  const co = items.filter(x => x.image).length;
  const duyet = items.filter(x => x.status === 'approved').length;
  return {
    n, co, duyet,
    pctCo: n ? Math.round(co * 100 / n) : 0,
    pctDuyet: n ? Math.round(duyet * 100 / n) : 0,
  };
}
function taoRefSection(id, ten, items) {
  if (!items.length) return null;
  const p = tienDoRef(items);
  const sec = document.createElement('section');
  sec.className = 'ref-section';
  sec.id = id;
  sec.innerHTML = `<div class="ref-section-h"><div><h3>${esc(ten)}</h3>
    <p>${p.co}/${p.n} đã có ảnh · ${p.duyet}/${p.n} đã duyệt</p></div></div>
    <div class="ref-grid"></div>`;
  return sec;
}
function refSubRow(label, anchor, items) {
  const p = tienDoRef(items);
  if (!p.n) return '';
  return `<button type="button" class="refsub"
    aria-label="${esc(label)}: ${p.co}/${p.n} đã có ảnh, ${p.duyet}/${p.n} đã duyệt"
    title="${esc(label)} · ${p.co}/${p.n} đã có ảnh · ${p.duyet}/${p.n} đã duyệt"
    onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();jumpRefGroup('${anchor}')}"
    onclick="jumpRefGroup('${anchor}')">
      <span class="sv">${esc(label)}</span>
      <span class="si ${p.co === p.n ? 'du' : ''}">${p.pctCo}%</span>
      <span class="sp">${p.pctDuyet}%</span>
    </button>`;
}
function jumpRefGroup(anchor) {
  const el = document.getElementById(anchor);
  if (!el) return;
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  el.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
}
function snav() {
  const nav = document.getElementById('snav');
  const vid = VIEW === 'script';
  // REF CÓ MẶT TRONG THANH BÊN ở tab Start frame (user chốt 2026-08-07): chân
  // dung và trang phục cũng là thứ hay phải nhảy tới. Bỏ ở tab Kịch bản vì tab
  // đó không dựng khối REF — link sẽ trỏ vào hư không.
  const scenes = (DATA.scenes || []).filter(s => s.id !== 'REF' || !vid);
  if (!scenes.length) { nav.innerHTML = ''; document.body.classList.remove('hasnav'); return }
  document.body.classList.add('hasnav');
  const rows = scenes.map(sc => {
    const items = vid ? (sc.shots || []) : (sc.sfs || []);
    const n = items.length;
    const d = vid ? items.filter(x => x.vstatus === 'approved').length
      : items.filter(x => x.status === 'approved').length;
    // HAI CON SỐ, HAI CHẶNG KHÁC NHAU: đã có ảnh/video chưa (tiến độ RENDER) và
    // đã duyệt chưa (tiến độ DUYỆT). Trước đây thanh bên chỉ có số duyệt, nên
    // scene render xong sạch vẫn hiện 0% — nhìn như chưa làm gì.
    const co = vid ? items.filter(x => x.video).length
      : items.filter(x => x.image).length;
    const pct = n ? Math.round(d * 100 / n) : 0;
    const pctCo = n ? Math.round(co * 100 / n) : 0;
    const row = `<a onclick="jumpScene('${sc.id}')" id="nv-${sc.id}" class="${n && d === n ? 'full' : ''}"
  title="${sc.id}: ${co}/${n} ${vid ? 'shot đã có video' : 'SF đã có ảnh'} · ${d}/${n} đã duyệt">
  <span class="r1"><span class="sv">${esc(sc.id)}</span>
    <span class="si ${n && co === n ? 'du' : ''}">${n ? pctCo + '%' : '—'}</span>
    <span class="sp">${n ? pct + '%' : '—'}</span></span>
  <span class="bar"><u style="width:${pctCo}%"></u><i style="width:${pct}%"></i></span></a>`;
    if (sc.id !== 'REF' || vid) return row;
    const ref = chiaRef(sc.sfs || []);
    return row + `<div class="refsubs" aria-label="Nhóm REF">
      ${refSubRow('Nhân vật', 'ref-nhan-vat', ref.nhanVat)}
      ${refSubRow('Đạo cụ', 'ref-dao-cu', ref.daoCu)}
      ${refSubRow('Bối cảnh', 'ref-boi-canh', ref.boiCanh)}
    </div>`;
  }).join('');
  // Dòng tổng "x% — d/n đã duyệt" ở đáy thanh bên đã bỏ 2026-08-09 theo yêu cầu user.
  // Tiêu đề "START FRAME"/"VIDEO" trên đầu thanh bên đã bỏ 2026-08-09: tab đang
  // mở đã nói rõ đang xem gì, dòng này chỉ ăn chỗ của danh sách scene.
  nav.innerHTML = `${rows}
<a class="allm" onclick="showMasters()">🗂 Xem tất cả master</a>`;
  markScene();
}
// bọc render: vẽ xong ở BẤT KỲ chế độ nào cũng cập nhật lại thanh bên trái, và
// nối tay cho các thanh lượt vừa mọc trong thân scene (kéo–thả · mở to · nhớ
// trạng thái mở/đóng). Nối ở đây thay vì trong từng nhánh render để không có
// nhánh nào lỡ quên — thanh lượt không nối tay thì kéo–thả chết câm.
(function () { const _r = render; render = function () { _r.apply(this, arguments); snav(); }; })();
function syncHdr() {
  const h = document.querySelector('header');
  if (h) document.documentElement.style.setProperty('--hdrh', h.offsetHeight + 'px');
}
syncHdr();
window.addEventListener('resize', syncHdr);
if (window.ResizeObserver) {
  const h = document.querySelector('header');
  if (h) new ResizeObserver(syncHdr).observe(h);
}

// ══ CHỌN START FRAME CÓ XEM TRƯỚC ══ dropdown chữ không cho biết ảnh nào,
// nên thay bằng lưới thumbnail: SF của scene này trước, rồi master, rồi phần còn lại.
let SP = null;

// ══ XEM TẤT CẢ MASTER ══ mọi bối cảnh gốc của phim gom một chỗ, kèm số SF con
// đang bám vào — để thấy ngay bối cảnh nào đang bị dồn quá nhiều cảnh.
function showMasters() {
  const all = allSF().map(x => x.f);
  const kids = {};
  all.forEach(f => { const b = f.refs && f.refs.bg; if (b) kids[b] = (kids[b] || 0) + 1 });
  const ms = all.filter(isDiaDiem)
    .sort((a, b) => (kids[b.id] || 0) - (kids[a.id] || 0));
  document.getElementById('ma-n').textContent = ms.length + ' master';
  const g = document.getElementById('ma-g');
  g.innerHTML = ms.map(f => {
    const n = kids[f.id] || 0;
    const warn = n > 25 ? ' style="color:var(--bad);font-weight:700"' : '';
    return `<div class="it" data-m="${esc(f.id)}">
  ${f.image ? `<img src="${thumb(f.image, 420)}" loading="lazy" decoding="async">`
        : '<div class="no">chưa có ảnh</div>'}
  <b>${esc(f.id)}</b><i>${esc(f.label || '')}</i>
  <u${warn}>${n} SF con bám vào${n > 25 ? ' — đang dồn quá nhiều' : ''}</u></div>`;
  }).join('') || '<div style="padding:14px">Chưa có master nào.</div>';
  g.querySelectorAll('[data-m]').forEach(el => el.onclick = () => {
    const r = find(el.dataset.m);
    if (r && r.f && r.f.image) lbOpenAt(r.f); else bao(el.dataset.m + ' chưa có ảnh.');
  });
  mall.showModal();
}

function openSFPick(sc, sh) {
  SP = { sc, sh }; SPMODE = 'shot';
  document.getElementById('sp-t').textContent =
    'Chọn Start frame cho ' + sh.id + ' — chỉ trong scene ' + sc.id;
  document.getElementById('sp-q').value = '';
  drawSFPick();
  sfpick.showModal();
  setTimeout(() => document.getElementById('sp-q').focus(), 30);
}
function drawSFPick() {
  if (!SP) return;
  const q = (document.getElementById('sp-q').value || '').trim().toLowerCase();
  // CHỈ SF CỦA CHÍNH SCENE NÀY. Một SF thuộc về scene nào thì chỉ dòng video của
  // scene đó được dùng — dùng chéo scene là nguồn gốc lỗi tụt pha không gian.
  const hit = f => !q || f.id.toLowerCase().includes(q) || (f.label || '').toLowerCase().includes(q);
  const own = SP.sc.sfs.filter(f => !f.id.startsWith('REF_')).filter(hit);
  const card = f => `<div class="it${f.id === SP.sh.sf ? ' cur' : ''}" data-pick="${esc(f.id)}">
${f.image ? `<img src="${thumb(f.image, 300)}" loading="lazy" decoding="async">`
      : '<div class="no">chưa có ảnh</div>'}
<b>${esc(f.id)}</b><i>${esc(f.label || '')}</i></div>`;
  const g = document.getElementById('sp-g');
  g.innerHTML = own.length
    ? `<div class="hd">Scene ${esc(SP.sc.id)} — ${own.length} start frame</div>` + own.map(card).join('')
    : `<div class="hd">Scene ${esc(SP.sc.id)} chưa có start frame nào${q ? ' khớp "' + esc(q) + '"' : ''}
   — tạo mới ở tab Start frames, hoặc kéo–thả ảnh vào ô SF của dòng này.</div>`;
  g.querySelectorAll('[data-pick]').forEach(el => el.onclick = () => pickSF(el.dataset.pick));
}
function pickSF(id) {
  const sh = SP.sh;
  sh.sf = id;
  // dòng Start frame trong prompt phải đi theo, nếu không ảnh một đằng prompt một nẻo
  if (sh.prompt) sh.prompt = sh.prompt.replace(/Start frame:\s*\S+/, 'Start frame: ' + id);
  save(); sfpick.close(); render();
}
// MỘT hộp thoại chọn, HAI người dùng: chọn SF cho dòng video, và gắn ảnh của
// lượt chờ phân loại. Ô lọc phải gọi đúng bên đang mở.
document.addEventListener('input', e => {
  if (e.target.id !== 'sp-q') return;
  SPMODE === 'ref' ? veRefPick() : drawSFPick();
});


// ══ THỨ TỰ RENDER: MASTER → NEO → góc con ══
// Ảnh nào được SF khác dùng làm refs.bg thì phải render và duyệt TRƯỚC, vì các
// khung sau bám vào nó để giữ vị trí người / bối cảnh. Xem "ẢNH NEO" trong skill.
function bgUsers(sc) {
  const m = {};
  (sc.sfs || []).forEach(f => { const b = (f.refs || {}).bg; if (b) m[b] = (m[b] || 0) + 1 });
  return m;
}
function sfRank(f, users) {
  const isM = isDiaDiem(f);
  const kids = users[f.id] || 0;
  if (isM) return 0;          // master: gốc bối cảnh
  if (kids > 0) return 1;       // neo: có khung khác bám vào
  return 2;                  // góc con
}
function sfOrderTag(f, users) {
  const r = sfRank(f, users), kids = users[f.id] || 0;
  if (r === 0) return `<span class="ordtag m" title="THẺ ĐỊA ĐIỂM — mang luatchung, ${kids} khung bám vào. Chạy TRƯỚC TIÊN.">① ĐỊA ĐIỂM${kids ? ' · ' + kids : ''}</span>`;
  // Bậc 1 = SF KHÔNG mang luatchung nhưng có khung khác bám vào. Với luật hai
  // tầng (thẻ địa điểm → SF thường) đây là BẤT THƯỜNG chứ không phải một loại
  // thẻ hợp lệ — ảnh neo đã bỏ 2026-08-07. Giữ nhãn để BÁO chuỗi ba tầng.
  if (r === 1) return `<span class="ordtag n" title="${kids} khung đặt refs.bg vào thẻ này nhưng nó KHÔNG mang luatchung — chuỗi đang BA TẦNG. Chuỗi đúng chỉ hai: thẻ địa điểm → SF thường.">⚠ 3 TẦNG · ${kids}</span>`;
  return '';
}

function jumpScene(id) {
  // NHẢY THẲNG, KHÔNG CUỘN MƯỢT (user chốt 2026-08-07). Board này dài hàng chục
  // nghìn pixel; cuộn mượt qua 200 thẻ vừa lâu vừa ép trình duyệt giải mã mọi
  // ảnh lướt qua giữa đường. Bấm scene nào là tới ngay scene đó.
  const el = document.getElementById('sc-' + id);
  if (!el) return;
  // NHẢY RỒI CHỈNH LẠI. Ảnh `loading="lazy"` nạp thêm ngay lúc cuộn tới, trang
  // giãn ra và điểm hạ cánh trôi mất — đã đo lệch 746px trên board 68.000px.
  // Nên đo lại vài nhịp khung hình rồi nắn về đúng chỗ; dừng sớm khi đã khớp.
  let lan = 0;
  const toi = () => {
    const hh = (document.querySelector('header') || {}).offsetHeight || 52;
    const lech = el.getBoundingClientRect().top - hh - 6;
    if (Math.abs(lech) > 2) { window.scrollTo({ top: window.scrollY + lech, behavior: 'instant' }) }
    else if (lan > 1) { markScene(); return }
    if (++lan < 8) requestAnimationFrame(toi); else markScene();
  };
  toi();
}
function markScene() {
  const ss = [...document.querySelectorAll('section.scene')];
  if (!ss.length) return;
  let cur = ss[0];
  const hh = (document.querySelector('header') || {}).offsetHeight || 52;
  for (const s of ss) { if (s.getBoundingClientRect().top <= hh + 40) cur = s; }
  document.querySelectorAll('#snav a').forEach(a => a.classList.remove('cur'));
  const a = document.getElementById('nv-' + cur.id.slice(3));
  if (a) a.classList.add('cur');
}
let _mkT = null;
window.addEventListener('scroll', () => { clearTimeout(_mkT); _mkT = setTimeout(markScene, 60) });

function render() {
  stats();
  $('#filter').style.display = VIEW === 'sf' ? '' : 'none';
  $('#vfilter').style.display = VIEW === 'script' ? '' : 'none';
  $('#vfilter').className = $('#vfilter').value === 'all' ? '' : 'act';
  if (VIEW !== 'script') $('#vbulk').style.display = 'none';
  // Nút "Chạy hết video" chỉ có nghĩa ở tab Kịch bản — tab Start frames không
  // có dòng video nào để chạy.
  { const b = $('#vidallbtn'); if (b) b.style.display = VIEW === 'script' ? '' : 'none' }
  // Dòng chú thích dài dưới thanh công cụ (#hint) đã BỎ 2026-08-09 theo yêu cầu user.
  if (VIEW === 'script') { renderScript(); snav(); return }
  const fl = $('#filter').value;
  const _uu = k => {
    const m = {}; DATA.scenes.forEach(sc => (sc.sfs || []).forEach(f => {
      const b = (f.refs || {}).bg; if (b) m[b] = (m[b] || 0) + 1
    })); return m
  };
  const _UU = _uu();
  const keep = f => fl === 'all' ? 1 : fl === 'noimg' ? !f.image
    : fl === 'root' ? (isDiaDiem(f) || (_UU[f.id] || 0) > 0)
      : fl === 'pending' ? f.status === 'proposed' : f.status === fl;
  const root = $('#root'); root.innerHTML = '';
  if (!DATA.scenes.length) { root.innerHTML = '<div class="empty-all">Chưa có scene. Bấm “+ Thêm scene”.</div>'; return }
  DATA.scenes.forEach(sc => {
    const _u = bgUsers(sc);
    // MASTER trước, rồi NEO, rồi góc con — đúng thứ tự phải render
    const list = sc.sfs.filter(keep).slice().sort((a, b) => sfRank(a, _u) - sfRank(b, _u));
    const el = document.createElement('section'); el.className = 'scene'; el.id = 'sc-' + sc.id;
    // MỘT con số thôi: đã có ảnh / tổng SF. Trước đây header đèo cả thời lượng,
    // số shot, mật độ "gợi ý 9–12" và số thẻ đang hiện — bốn cụm chữ cho một
    // dòng tiêu đề, đọc lướt không ra thông tin nào.
    const nsf = sc.sfs.length;
    const coanh = sc.sfs.filter(f => f.image).length;
    el.innerHTML = `<div class="scene-h"><span class="sid">${esc(sc.id)}</span><h2>${esc(sc.name)}</h2>
  <span style="flex:1"></span>
  <span class="sfdens ${nsf && coanh === nsf ? 'ok' : ''}"
    title="${coanh}/${nsf} SF của scene này đã có ảnh">${coanh}/${nsf}</span>
  ${autoBtn(sc, true)}
  ${nutTask(sc, list)}
  <button class="sm" onclick="tickScene('${sc.id}')"
    title="Tích mọi thẻ đang hiện của scene này để 'Tạo lại theo lô'">☑ Chọn hết</button>
  <button class="sm ok-b" onclick="duyetScene('${sc.id}',1)"
    title="Đánh dấu ĐÃ DUYỆT cho mọi thẻ ĐÃ CÓ ẢNH của scene này. Thẻ chưa có ảnh bỏ qua.">✓✓ Duyệt hết</button>
  <button class="sm" onclick="duyetScene('${sc.id}',0)"
    title="Bỏ duyệt mọi thẻ ĐÃ DUYỆT của scene này — đưa chúng về 'chờ duyệt' để sửa/tạo lại.">↺ Bỏ duyệt</button>
  <button class="sm" onclick="addSF('${sc.id}')">+ SF</button>
  <button class="sm bad-b" onclick="delScene('${sc.id}')">Xóa scene</button></div>
  <div class="grid"></div>`;
    const g = el.querySelector('.grid');
    // Nút "＋ SF từ ảnh" đã gỡ khỏi header 2026-08-12 (user chốt: không dùng).
    // Hàm pasteBox() vẫn giữ — kéo–thả ảnh thẳng vào ô ảnh của thẻ vẫn chạy,
    // chỉ mất lối tạo THẺ MỚI từ ảnh.
    if (sc.id === 'REF') {
      const refTatCa = chiaRef(sc.sfs || [], sc.sfs || []);
      const ref = chiaRef(list, sc.sfs || []);
      const themSection = (id, ten, tatCa, dangHien, ve) => {
        const sec = taoRefSection(id, ten, tatCa);
        if (!sec) return;
        const rg = sec.querySelector('.ref-grid');
        if (dangHien.length) ve(rg);
        else rg.innerHTML = '<p class="ref-empty">Không có mục phù hợp bộ lọc hiện tại.</p>';
        g.appendChild(sec);
      };
      // NHÓM THEO NHÂN VẬT: portrait là thẻ chính, các bản trang phục (_FULL)
      // thành dải ảnh nhỏ bên trong thẻ đó — bấm ảnh nhỏ để phóng to,
      // bấm ✎ để mở/đóng các thẻ trang phục đầy đủ (sửa prompt, tạo lại).
      themSection('ref-nhan-vat', 'Nhân vật', refTatCa.nhanVat, ref.nhanVat, rg => {
        const ports = ref.nhanVat.filter(f => f.id.endsWith('_PORTRAIT'));
        const fulls = ref.nhanVat.filter(f => f.id.endsWith('_FULL'));
        const byChar = {};
        fulls.forEach(f => {
          const ch = nguoiRef(f.id);
          (byChar[ch] = byChar[ch] || []).push(f);
        });
        ports.forEach(pf => {
          const ch = nguoiRef(pf.id), kids = byChar[ch] || [];
          delete byChar[ch];
          const d = card(sc, pf);
          const idx = ref.thuTu.get(ch);
          if (Number.isInteger(idx)) {
            const phu = idx >= 4;
            d.querySelector('.sfid').insertAdjacentHTML(
              'afterbegin',
              `<span class="ref-role ${phu ? 'supporting' : 'main'}">${phu ? 'Phụ' : 'Chính'}</span>`
            );
          }
          if (kids.length) {
            const strip = document.createElement('div');
            strip.className = 'wrstrip';
            // Chữ "Trang phục (n)" đã bỏ 2026-08-09 — dải ảnh nhỏ tự nói lên nó là gì.
            strip.innerHTML = kids.map(k =>
              `<span class="wit${k.status === 'approved' ? ' ok' : ''}" data-wsee="${esc(k.id)}"
             title="${esc(k.id)} — bấm để phóng to">
             ${k.image ? `<img src="${thumb(k.image, 120)}" loading="lazy">` : '<i>?</i>'}</span>`).join('')
              + `<button class="sm wtog pri" data-wtog="${esc(ch)}"
             title="${WROPEN[ch] ? 'Đóng' : 'Mở'} thẻ đầy đủ của ${kids.length} bộ trang phục — sửa prompt, tạo lại, duyệt, xoá"
             >${WROPEN[ch] ? '▾' : '✎'}</button>`;
            strip.querySelectorAll('[data-wsee]').forEach(el => {
              el.onclick = () => {
                const r = find(el.dataset.wsee);
                if (r && r.f && r.f.image) lbOpenAt(r.f); else bao(el.dataset.wsee + ' chưa có ảnh.');
              };
              el.title = el.dataset.wsee + ' — bấm để phóng to, KÉO ẢNH VÀO ĐÂY để thay';
              el.ondragover = e => { e.preventDefault(); el.classList.add('drop') };
              el.ondragleave = () => el.classList.remove('drop');
              el.ondrop = async e => {
                e.preventDefault(); el.classList.remove('drop');
                const file = e.dataTransfer.files[0]; if (!file) return;
                await uploadTo(el.dataset.wsee, file, file.name);
                await load();
              };
            });
            strip.querySelector('[data-wtog]').onclick = () => {
              WROPEN[ch] = !WROPEN[ch]; render();
            };
            d.querySelector('.body').insertBefore(strip, d.querySelector('.body').children[1]);
          }
          rg.appendChild(d);
          kids.forEach(k => {
            const kd = card(sc, k);
            if (!WROPEN[ch]) kd.style.display = 'none';
            rg.appendChild(kd);
          });
        });
        Object.values(byChar).flat().forEach(f => rg.appendChild(card(sc, f))); // full mồ côi
      });
      themSection('ref-dao-cu', 'Đạo cụ', refTatCa.daoCu, ref.daoCu,
        rg => ref.daoCu.forEach(f => rg.appendChild(card(sc, f))));
      themSection('ref-boi-canh', 'Bối cảnh', refTatCa.boiCanh, ref.boiCanh,
        rg => ref.boiCanh.forEach(f => rg.appendChild(card(sc, f))));
    } else {
      list.forEach(f => g.appendChild(card(sc, f)));
    }
    root.appendChild(el);
  });
}

/* --- CHẠY TỰ ĐỘNG: bật cho scene rồi để đó, board tự tạo ảnh SF còn thiếu,
   ảnh xong tới đâu đẩy video tới đó, cái nào lỗi tự bắn lại, xong thì tự tắt --- */
async function toggleAuto(id) {
  const r = await (await fetch('/api/auto?op=toggle&scene=' + encodeURIComponent(id),
    { method: 'POST' })).json();
  AUTO = r.auto || {}; render();
}
// SCENE ĐÃ ĐỦ ẢNH MÀ USER VẪN MUỐN VẼ LẠI — đường riêng, KHÔNG đi qua auto.
//
// Vòng quét nền sinh ra để LẤP CHỖ TRỐNG: nó chọn việc bằng `find_file()` (thẻ
// nào chưa có ảnh) và đẩy hàng với `tay=False`, nên bộ lọc "đã có ảnh" ở tầng
// gửi chặn lần thứ hai. Ép nó tạo lại là đi ngược cả hai tầng. Đường này chia
// task y hệt nút T rồi bắn thẳng qua `/api/tao-lo` — cùng lối với "▶ Tạo ảnh đã
// chọn", tức `tay=True`, đè được, và vẫn nằm đủ trong hàng chờ để theo dõi.
async function chayLaiScene(sid) {
  const sc = DATA.scenes.find(s => s.id === sid);
  if (!sc) return;
  const ts = taskCua(sc.sfs.filter(f => (f.prompt || '').trim()), true);
  const n = ts.reduce((s, ds) => s + ds.length, 0);
  if (!n) { bao(`Scene ${sid} không có thẻ nào có prompt để chạy.`); return }
  const nDuyet = sc.sfs.filter(f => f.status === 'approved').length;
  const coDD = sc.sfs.some(f => f.luatchung);
  if (!await hoi(`Scene ${sid} đã đủ ảnh. TẠO LẠI toàn bộ ${n} thẻ (${ts.length} task)?\n\n`
    + `Ảnh mới sẽ ĐÈ lên ảnh đang dùng — bản cũ vẫn nằm trong dãy bản của thẻ.\n`
    + (nDuyet ? `${nDuyet} thẻ đang ở trạng thái ĐÃ DUYỆT: chúng cũng bị đè.\n` : '')
    + (coDD ? `Scene có thẻ địa điểm: nó chạy lại cùng lượt với các thẻ con, nên\n`
      + `lứa con này vẫn bám ảnh địa điểm CŨ. Muốn khớp look thì chạy thẻ địa điểm\n`
      + `trước, duyệt nó, rồi mới tạo lại phần còn lại.\n` : '')
    + `\nMỗi task là một tin nhắn ChatGPT và TỐN LƯỢT.`,
    { dong: `Tạo lại ${n} ảnh` })) return;
  let ok = 0, loi = [];
  for (const ds of ts) {
    const r = (await postJob('/api/tao-lo?sf=' + encodeURIComponent(ds.map(f => f.id).join(',')),
      newJobKey())).body;
    if (r.err) loi.push(r.err); else ok += ds.length;
  }
  $('#runstatus').textContent = `đã xếp ${ok} ảnh của ${sid} để tạo lại`
    + (loi.length ? ` · ${loi.length} task bị chặn` : '');
  if (loi.length) bao(`Có ${loi.length} task không xếp được:\n\n` + loi.slice(0, 3).join('\n'));
  setTimeout(() => $('#runstatus').textContent = '', 9000);
}

// `laiOK` — CHỈ TAB START FRAMES được đổi nút sang "tạo lại". Ở tab Kịch bản,
// cùng nút này còn lo VIDEO: scene đủ ảnh mà thiếu video vẫn phải bật auto được,
// đổi vai ở đó là cắt mất lối chạy video của scene.
function autoBtn(sc, laiOK) {
  const on = AUTO.hasOwnProperty(sc.id);
  const st = AUTO[sc.id] || {};
  // Scene đủ ảnh và auto đang tắt → nút đổi vai thành "tạo lại". Không ẩn đi:
  // ẩn nút là mất luôn lối vẽ lại cả scene, mà đó đúng là lúc user cần nó nhất.
  if (laiOK && !on && sc.sfs.length && sc.sfs.every(f => f.image))
    return `<button class="sm re-b" onclick="chayLaiScene('${sc.id}')"
      title="Scene đã đủ ảnh. Bấm để TẠO LẠI toàn bộ: board chia task ≤10 ảnh cùng địa điểm rồi đẩy hết vào hàng chờ. Ảnh mới đè lên ảnh cũ, bản cũ vẫn nằm trong dãy bản."
      >↻ Tạo lại hết</button>`;
  // TỰ ĐẾM KHI SERVER CHƯA KỊP TRẢ SỐ. Số liệu này do vòng quét nền ghi ra, mà
  // vòng đó chạy theo nhịp riêng — bản cũ hiện "⏳ đang quét…" cho tới lượt quét
  // kế tiếp, nên bấm xong nhìn như bấm hụt. Dữ liệu để đếm đã nằm sẵn ở đây.
  const _ni = sc.sfs.length, _mi = sc.sfs.filter(f => !f.image).length;
  const _nv = (sc.shots || []).length, _mv = (sc.shots || []).filter(s => !s.video).length;
  const lab = on
    ? (st.img && st.vid
      ? `⏳ ${st.img[0]}/${st.img[1]} ảnh · ${st.vid[0]}/${st.vid[1]} video`
      : `⏳ ${_ni - _mi}/${_ni} ảnh · ${_nv - _mv}/${_nv} video`)
    : '▶ Chạy hết';
  const tip = on ? 'Đang tự chạy scene này. Bấm để dừng (việc đã xếp hàng vẫn chạy nốt).'
    : 'Tự tạo mọi ảnh SF còn thiếu của scene, ảnh xong tới đâu đẩy video tới đó, '
    + 'cái nào lỗi tự bắn lại. Xong cả scene thì tự tắt.';
  return `<button class="sm auto-b ${on ? 'on' : ''}" title="${tip}" `
    + `onclick="toggleAuto('${sc.id}')">${lab}</button>`;
}

/* ---------------- CHẾ ĐỘ KỊCH BẢN ---------------- */
function sfById(id) { const x = find(id); return x ? x.f : null }

function renderScript() {
  const root = $('#root'); root.innerHTML = '';
  const scenes = DATA.scenes.filter(s => s.id !== 'REF');
  if (!scenes.length) { root.innerHTML = '<div class="empty-all">Chưa có scene.</div>'; return }
  const flt = $('#vfilter').value;
  let shown = 0, hidden = 0;
  scenes.forEach(sc => {
    const all = sc.shots || [];
    const shots = all.filter(vkeep);
    shown += shots.length; hidden += all.length - shots.length;
    if (flt !== 'all' && !shots.length) return;          // scene không còn gì để xử lý → ẩn
    // Cùng lối với tab Start frames: MỘT con số "đã tạo / tổng". Ở tab này
    // "đã tạo" là shot ĐÃ CÓ VIDEO, không phải shot đã có SF.
    const covid = all.filter(s => s.video).length;
    // Thời lượng ĐÃ DỰNG / tổng của scene. Đếm shot ≠ đếm phút: 3 shot 6s xong
    // không bằng 1 shot 10s xong, mà thứ phải giao là số PHÚT phim.
    const _gy = x => x.reduce((a, s) => a + (s.dur || 10), 0);
    const gyCo = _gy(all.filter(s => s.video)), gyAll = _gy(all);
    const el = document.createElement('section'); el.className = 'scene'; el.id = 'sc-' + sc.id;
    el.innerHTML = `<div class="scene-h"><span class="sid">${esc(sc.id)}</span><h2>${esc(sc.name)}</h2>
  <span style="flex:1"></span>
  <span class="sfdens ${gyAll && gyCo === gyAll ? 'ok' : ''}"
    title="Thời lượng đã có video / tổng của scene này">${mmss(gyCo)} / ${mmss(gyAll)}</span>
  <span class="sfdens ${all.length && covid === all.length ? 'ok' : ''}"
    title="${covid}/${all.length} shot của scene này đã có video">${covid}/${all.length}</span>
  ${autoBtn(sc)}
  <button class="sm" onclick="addShot('${sc.id}')">+ video</button></div>
  ${sc.script ? `<details class="scr" ${shots.length ? '' : 'open'}><summary>📖 Kịch bản gốc</summary>
    <pre>${esc(sc.script)}</pre></details>` : ''}
  <div class="shots"></div>`;
    const box = el.querySelector('.shots');
    shots.forEach(sh => box.appendChild(shotRow(sc, sh, all.indexOf(sh))));
    root.appendChild(el);
  });
  vbulkBar(shown, hidden);
  if (flt !== 'all' && !shown)
    root.innerHTML = '<div class="empty-all">Không có video nào ở trạng thái này ✓</div>';
}

/* Nút thao tác hàng loạt trên đúng nhóm đang lọc */
// Chỉ ba nhóm này thì "tạo lại" mới đúng là việc cần làm. "Trống thời lượng" và
// "prompt lệch thoại" phải sửa chia thoại / viết lại prompt TRƯỚC — render lại ngay
// chỉ dựng lại đúng cái sai cũ.
const VBULK_OK = { novid: 'chưa có video', err: 'lỗi khi tạo', rejected: 'bị loại' };

// CỔNG VIDEO (nút 🔒 khoá/mở tạo video) đã BỎ 2026-08-09 theo yêu cầu user.
// Thay bằng CÔNG TẮC AUTO-VIDEO: chỉ chặn vòng quét tự động xếp việc video, KHÔNG
// chặn nút "Tạo video" bấm tay. Trạng thái về theo mỗi vòng poll /api/jobs.
let AVON = false;
function veAutoVid() {
  const b = document.getElementById('avbtn'); if (!b) return;
  b.textContent = AVON ? '🎞 Auto video: BẬT' : '🎞 Auto video: tắt';
  b.classList.toggle('on', AVON);
  b.style.color = AVON ? 'var(--acc)' : '';
  b.style.borderColor = AVON ? 'var(--acc)' : '';
}
// "▶ Chạy tuần tự" ĐÃ BỎ 2026-08-12 (user chốt). Nó chạy TỪNG ẢNH MỘT — mỗi
// ảnh một tin nhắn, không gửi luatchung, không gom lô — nên vừa chậm vừa cho ảnh
// mất neo bối cảnh. Thay bằng "▶▶ Chạy hết phim" (auto chia task 10 ảnh cùng địa
// điểm) và các nút T1/T2 để chạy tay từng task.

// Nút "bố" của các nút "Chạy hết" từng scene: bật auto cho MỌI scene còn thiếu
// ảnh. Bấm lần nữa để tắt hết. Bỏ REF — thẻ nhân vật/đạo cụ là bản neo, user tự
// chọn tự duyệt từng cái chứ không giao cho máy quét.
async function chayHetPhim() {
  const dangBat = Object.keys(AUTO || {}).length;
  if (dangBat) {
    if (!await hoi(`Tắt "Chạy hết" ở ${dangBat} scene?\n\nViệc đã xếp vào hàng chờ vẫn chạy nốt.`,
      { dong: 'Tắt hết' })) return;
    const r = await (await fetch('/api/auto?op=offall', { method: 'POST' })).json();
    AUTO = r.auto || {}; render();
    $('#runstatus').textContent = 'đã tắt auto ở mọi scene';
    setTimeout(() => $('#runstatus').textContent = '', 5000);
    return;
  }
  const thieu = DATA.scenes.filter(s => s.id !== 'REF' && s.sfs.some(f => !f.image));
  const n = thieu.reduce((s, sc) => s + sc.sfs.filter(f => !f.image).length, 0);
  if (!thieu.length) {
    // KHÔNG tự tạo lại cả phim ở đây. Nút này là "lấp chỗ thiếu"; tạo lại vài
    // trăm ảnh một phát vì bấm nhầm là mất cả ngày lượt. Muốn vẽ lại thì vào
    // từng scene — ở đó nút đã đổi thành "↻ Tạo lại hết" và có hỏi xác nhận.
    bao('Mọi scene đã đủ ảnh — không còn gì để lấp.\n\n'
      + 'Muốn VẼ LẠI thì vào từng scene: nút "↻ Tạo lại hết" ở đầu scene, '
      + 'hoặc các nút T1↻ / T2↻ để tạo lại từng task 10 ảnh.');
    return;
  }
  if (!await hoi(`Chạy hết ${n} ảnh còn thiếu của ${thieu.length} scene?\n\n`
    + `Board tự chia task ≤10 ảnh cùng địa điểm rồi đẩy lần lượt vào hàng chờ,\n`
    + `lỗi thì tự bắn lại, xong scene nào tự tắt scene đó.\n\n`
    + `Thẻ đã có ảnh và scene REF được bỏ qua — REF có nút "▶ Chạy hết" riêng.`,
    { dong: 'Chạy hết phim' })) return;
  const r = await (await fetch('/api/auto?op=onall', { method: 'POST' })).json();
  AUTO = r.auto || {}; render();
  $('#runstatus').textContent = `đã bật auto cho ${r.so} scene: ${(r.scenes || []).join(', ')}`;
  setTimeout(() => $('#runstatus').textContent = '', 9000);
}

function veChayHetPhim() {
  const b = $('#allbtn'); if (!b) return;
  const n = Object.keys(AUTO || {}).length;
  b.textContent = n ? `■ Dừng auto (${n} scene)` : '▶▶ Chạy hết phim';
  b.classList.toggle('on', !!n);
}

// Xếp hàng loạt VIDEO cho CẢ PHIM (nút 🎬 trên thanh công cụ).
// Header từng scene KHÔNG có nút này (user chốt 2026-08-13): ở đó đã có
// "▶ Chạy hết" lo cả ảnh lẫn video của scene. Hàm vẫn nhận `sid` để dùng lại
// được nếu sau này cần chạy riêng một scene.
// Khác "Chạy hết phim" (ảnh): video KHÔNG gom lô được, Grok chỉ nhận một ảnh +
// một prompt mỗi lượt, nên đây là xếp từng việc rời vào hàng đợi.
async function chayHetVideo(sid) {
  const scs = DATA.scenes.filter(s => !sid || s.id === sid);
  const dung = sh => {
    const f = sfById(sh.sf);
    return (sh.prompt || '').trim() && f && f.image;
  };
  const dem = scs.reduce((n, sc) => n + (sc.shots || []).filter(sh => !sh.video && dung(sh)).length, 0);
  // ĐỦ VIDEO RỒI THÌ CHUYỂN SANG TẠO LẠI, KHÔNG BÁO "không có gì để chạy"
  // (cùng luật với nút ảnh, user chốt 2026-08-14). Phim dựng xong mà nút này
  // câm thì không còn lối làm lại hàng loạt, chỉ còn bấm từng dòng.
  const lai = !dem;
  const demLai = scs.reduce((n, sc) => n + (sc.shots || []).filter(dung).length, 0);
  const so = lai ? demLai : dem;
  if (!so) {
    bao(sid ? `Scene ${sid} không có dòng nào chạy được — thiếu prompt hoặc ảnh SF chưa vẽ.`
      : 'Không có dòng nào chạy được — mọi dòng đều thiếu prompt hoặc ảnh SF chưa vẽ.');
    return;
  }
  if (!await hoi(
    (lai ? `Mọi dòng đã có video. TẠO LẠI ${so} video${sid ? ' của ' + sid : ' của cả phim'}?\n\n`
      + `Video mới ĐÈ lên bản đang dùng — bản cũ vẫn nằm trong dãy bản của dòng đó.\n`
      : `Tạo ${so} video${sid ? ' của ' + sid : ' của cả phim'}?\n\n`)
    + `Mỗi video là một lượt Grok riêng và TỐN CREDIT.\n`
    + `Bỏ qua dòng thiếu prompt hoặc ảnh SF chưa vẽ xong.`,
    { dong: (lai ? 'Tạo lại ' : 'Tạo ') + so + ' video' })) return;
  const qs = [sid ? 'scene=' + encodeURIComponent(sid) : '', lai ? 'lai=1' : ''].filter(Boolean).join('&');
  const r = (await postJob('/api/video-lo' + (qs ? '?' + qs : ''), newJobKey())).body;
  const b = r.bo || {};
  $('#runstatus').textContent = `đã xếp ${r.so} video`
    + (b.co_video ? ` · bỏ ${b.co_video} đã có` : '')
    + (b.thieu_sf ? ` · ${b.thieu_sf} thiếu ảnh SF` : '')
    + (b.thieu_prompt ? ` · ${b.thieu_prompt} thiếu prompt` : '');
  setTimeout(() => $('#runstatus').textContent = '', 9000);
}

async function toggleAutoVid() {
  const r = await (await fetch('/api/auto-video?on=' + (AVON ? '0' : '1'), { method: 'POST' })).json();
  AVON = !!r.on; veAutoVid();
}
let WROPEN = {};   // nhân vật nào đang mở thẻ trang phục đầy đủ

// ══ LIGHTBOX ĐIỀU HƯỚNG ‹ › ══ danh sách ảnh theo đúng thứ tự đang hiển thị.
let LB_LIST = [], LB_IDX = -1;
function lbOpen(items, idx) {
  LB_LIST = items; LB_IDX = idx; lbShow(); lightbox.showModal();
}
function lbShow() {
  if (LB_IDX < 0 || LB_IDX >= LB_LIST.length) return;
  const it = LB_LIST[LB_IDX];
  document.getElementById('lb-t').textContent = it.t;
  document.getElementById('lb-i').src = it.src;
  document.getElementById('lb-n').textContent = (LB_IDX + 1) + '/' + LB_LIST.length;
  lbBan();
  // Nút lùi chỉ hiện khi THẬT SỰ có cái để lùi — nút chết bấm không ăn gì còn
  // tệ hơn không có nút.
  const nl = document.getElementById('lb-lui');
  if (nl) nl.style.display = HTAC.ht ? '' : 'none';
}
async function lbLui() {
  const r = await (await fetch('/api/gan-lui', { method: 'POST' })).json();
  if (!r.ok) { bao(r.err || 'Không còn gì để lùi'); return }
  await load();
  const it = LB_LIST[LB_IDX] || {}, moi = find(it.id);
  if (moi && moi.f.image) LB_LIST[LB_IDX] = { ...it, src: moi.f.image };
  HTAC.ht = Math.max(0, HTAC.ht - 1);
  lbShow();
}
/* DẢI SF CÙNG SCENE TRONG KHUNG PHÓNG TO.

   Mỗi ô là start frame của một video khác trong cùng scene, và có HAI hành động
   tách bạch — lẫn hai thứ này vào một cú bấm là kiểu bấm nhầm không ai ngờ:
     · bấm ẢNH   → chỉ NHẢY sang xem ô đó, không ghi gì
     · bấm "dùng" → LẤY ảnh ô đó về thẻ đang xem

   "dùng" là CHÉP, không phải chuyển: thẻ nguồn giữ nguyên ảnh, thẻ đang xem
   được thêm một bản mới và dùng bản đó. Chép nhầm thì bấm ↩ ở thanh trên cùng.

   Dãy BẢN của chính thẻ (v1/v2/…) KHÔNG nằm ở đây (user chốt 2026-08-07): lúc
   phóng to là lúc chọn KHUNG, không phải lúc soi lại bản cũ của chính khung đó
   — dãy bản vẫn ở dưới thẻ trên board. */
function lbBan() {
  const box = document.getElementById('lb-v'); if (!box) return;
  const it = LB_LIST[LB_IDX] || {};
  const r = find(it.id);
  if (!r) { box.style.display = 'none'; box.innerHTML = ''; return }
  box.style.display = '';
  const anhEm = (r.sc.sfs || []).filter(f => f.image);
  const the = (f) => `<span class="lbv${f.id === r.f.id ? ' cur' : ''}" data-lbsf="${esc(f.id)}"
  title="${esc(f.id)} — ${esc(f.label || '')}${f.goc ? '\n' + esc(f.goc) : ''}">
  <img src="${thumb(f.image, 420)}" loading="lazy" decoding="async"><b>${esc(f.id)}</b>
  ${f.id === r.f.id ? '<u class="dang">đang xem</u>'
      : `<u data-lbdoi="${esc(f.id)}" class="doi"
         title="TRÁO ĐỔI ảnh giữa ${esc(f.id)} và ${esc(r.f.id)} — mỗi thẻ nhận ảnh của thẻ kia">⇄</u>`
      + `<u data-lbdung="${esc(f.id)}" title="Lấy ảnh của ${esc(f.id)} về dùng cho ${esc(r.f.id)} (${esc(f.id)} giữ nguyên ảnh của nó)">⤵ dùng</u>`}</span>`;
  // Nhãn "SF trong scene … (n ảnh · bấm ảnh để xem · …)" đã bỏ 2026-08-09: mỗi ô
  // đã có tooltip riêng, dòng chú thích chỉ ăn chỗ của dải ảnh.
  // GIỮ NGUYÊN CHỖ ĐANG CUỘN. Mỗi cú bấm là dựng lại cả dải, mà dải mới bắt đầu
  // ở mép trái — trước đây chữa bằng scrollIntoView nên ảnh vừa chọn bị KÉO RA
  // GIỮA, cả dải giật một cái. Nhớ scrollLeft rồi trả lại thì dải đứng yên, ai
  // cần xem xa hơn thì tự cuộn ngang.
  const _cu = box.querySelector('.lbrow');
  const _sl = _cu ? _cu.scrollLeft : 0;
  box.innerHTML = `<div class="lbrow">${anhEm.map(the).join('')}</div>`;
  const _moi = box.querySelector('.lbrow');
  if (_moi && _sl) _moi.scrollLeft = _sl;
  // NHẢY sang SF khác — chỉ đổi chỗ đang xem, không ghi gì.
  box.querySelectorAll('[data-lbsf]').forEach(el => el.onclick = e => {
    if (e.target.closest('[data-lbdung],[data-lbdoi]')) return;   // nút có handler riêng
    const id = el.dataset.lbsf;
    let j = LB_LIST.findIndex(x => x.id === id);
    if (j < 0) {
      const t = find(id);
      if (!t || !t.f.image) return;
      LB_LIST.push({ id, src: t.f.image, t: id + ' — ' + (t.f.label || '') });
      j = LB_LIST.length - 1;
    }
    LB_IDX = j; lbShow();
  });
  box.querySelectorAll('[data-lbdoi]').forEach(el => el.onclick = async e => {
    e.stopPropagation();
    const kia = el.dataset.lbdoi, day = r.f.id;
    if (!await hoi(`Tráo đổi ảnh giữa ${day} và ${kia}?\n\n`
      + `${day} sẽ nhận ảnh của ${kia}, và ${kia} nhận ảnh của ${day}.\n`
      + `Ảnh cũ của cả hai vẫn nằm trong dãy bản. Bấm nhầm thì ↩ ở thanh trên cùng `
      + `lùi TRỌN cặp trong một nhát.`)) return;
    const qq = await (await fetch(`/api/sf-doi?a=${encodeURIComponent(day)}`
      + `&b=${encodeURIComponent(kia)}`, { method: 'POST' })).json();
    if (!qq.ok) { bao('Không tráo được: ' + (qq.err || '?')); return }
    HTAC.ht = (HTAC.ht || 0) + 1;
    await load();
    const moi = find(day);
    if (moi && moi.f.image) { LB_LIST[LB_IDX] = { ...it, src: moi.f.image } }
    lbShow();
  });
  box.querySelectorAll('[data-lbdung]').forEach(el => el.onclick = async e => {
    e.stopPropagation();
    const tu = el.dataset.lbdung, den = r.f.id;
    if (!await hoi(`Dùng ảnh của ${tu} cho ${den}?\n\n`
      + `${tu} GIỮ NGUYÊN ảnh của nó — ${den} được thêm một bản mới và dùng bản đó.\n`
      + `Bấm nhầm thì có nút ↩ ở thanh trên cùng của khung này.`)) return;
    const q = await (await fetch(`/api/sf-chuyen?tu=${encodeURIComponent(tu)}`
      + `&den=${encodeURIComponent(den)}`, { method: 'POST' })).json();
    if (!q.ok) { bao('Không dùng được: ' + (q.err || '?')); return }
    // ĐẾM NGAY TẠI CHỖ, đừng đợi vòng poll. `HTAC.ht` chỉ được cập nhật mỗi
    // nhịp poll, nên nút ↩ không kịp hiện đúng lúc user cần nó nhất — ngay sau
    // cú bấm vừa rồi. Đã đo: bấm "dùng" xong nút vẫn ẩn.
    HTAC.ht = (HTAC.ht || 0) + 1;
    await load();
    const moi = find(den);
    if (moi && moi.f.image) { LB_LIST[LB_IDX] = { ...it, src: moi.f.image } }
    lbShow();
  });
}
function lbNav(d) {
  if (!LB_LIST.length) return;
  LB_IDX = (LB_IDX + d + LB_LIST.length) % LB_LIST.length; lbShow();
}
document.addEventListener('keydown', e => {
  if (!document.getElementById('lightbox').open) return;
  if (e.key === 'ArrowLeft') { e.preventDefault(); lbNav(-1) }
  else if (e.key === 'ArrowRight') { e.preventDefault(); lbNav(1) }
});
function lbCollect() {
  // Gom theo ĐÚNG thứ tự thẻ đang hiển thị trên trang, nhưng lấy ẢNH GỐC và
  // nhãn từ DATA (không đoán URL từ src thu nhỏ — trước đây ghép sai nên
  // findIndex luôn trượt và lightbox mở ở cuối danh sách).
  const byId = {};
  (DATA.scenes || []).forEach(sc => (sc.sfs || []).forEach(f => { byId[f.id] = f }));
  const out = [];
  document.querySelectorAll('.thumb[data-sf]').forEach(th => {
    if (th.closest('#lightbox')) return;
    const f = byId[th.dataset.sf];
    if (f && f.image) out.push({ id: f.id, src: f.image, t: f.id + ' — ' + (f.label || '') });
  });
  return out;
}
function lbOpenAt(f) {
  // Mở lightbox ĐÚNG tại ảnh vừa bấm, để ‹ › đi tiếp từ chính nó.
  const L = lbCollect();
  let i = L.findIndex(x => x.id === f.id);
  if (i < 0) { L.push({ id: f.id, src: f.image, t: f.id + ' — ' + (f.label || '') }); i = L.length - 1 }
  lbOpen(L, i);
}

function vbulkBar(shown, hidden) {
  const b = $('#vbulk'), fl = $('#vfilter').value;
  // chỉ cho tạo lại hàng loạt ở những nhóm thật sự cần render lại —
  // "chưa duyệt"/"đã duyệt"/"nhiều bản" là nhóm để XEM, bấm nhầm thì rất tốn
  if (!VBULK_OK[fl] || !shown) { b.style.display = 'none'; return }
  b.style.display = '';
  b.textContent = `↻ Tạo lại ${shown} video đang hiện`;
  b.onclick = async () => {
    if (!await hoi(`Tạo lại ${shown} video thuộc nhóm “${VBULK_OK[fl]}”?\n\n`
      + `Bản cũ vẫn giữ lại thành version để so sánh.`)) return;
    const list = allShots().map(x => x.sh).filter(vkeep);
    // Mỗi shot một khoá riêng: gửi lại đúng shot nào thì chỉ shot đó replay.
    for (const sh of list) await postJob('/api/genvideo?sf=' + encodeURIComponent(sh.id), newJobKey());
    $('#runstatus').textContent = `đã xếp ${list.length} video vào hàng đợi`;
    setTimeout(() => $('#runstatus').textContent = '', 4000);
  };
}

// ~3.0 từ/giây — đo theo tốc độ đọc thực tế của giọng AI (điều chỉnh sau thực nghiệm)
function estimate(text) {
  const clean = (text || '').replace(/^[A-ZĐÂÊÔƠƯ][A-ZĐÂÊÔƠƯ\s.]*:/gm, ' ')  // bỏ nhãn tên
    .replace(/\([^)]*\)/g, ' ')                       // bỏ chú thích trong ngoặc
    .replace(/[—–-]{1,2}\s*[a-z, ]+:/g, ' ');          // bỏ chỉ dẫn giọng
  const words = clean.trim().split(/\s+/).filter(w => /[a-zA-ZÀ-ỹ']/.test(w));
  return { n: words.length, sec: words.length / 3.0 };
}
// Thoại đã bị sửa sau khi prompt video được viết → prompt đang mô tả bản thoại cũ.
// prompt_text là ảnh chụp lời thoại tại lúc AI viết prompt; shot chưa có mốc thì bỏ qua.
/* Nhóm trạng thái của một video, dùng cho bộ lọc ở chế độ Kịch bản */
function vcat(sh) {
  const f = sfById(sh.sf);
  const { sec } = estimate(sh.text);
  return {
    novid: !sh.video,
    approved: sh.vstatus === 'approved',
    rejected: sh.vstatus === 'rejected',
    pending: sh.vstatus !== 'approved' && sh.vstatus !== 'rejected',
    multi: (sh.vversions || []).length > 1,
    err: (JOBS[sh.id] || {}).state === 'error',
    gap: ((sh.dur || 10) - sec) > 3.2,
    stale: stale(sh),
    note: !!(sh.notes || '').trim(),
    nosf: !f || !f.image,
    beat: /-B\d+$/.test(sh.id),          // nhịp không thoại: id kết thúc bằng -B<số>
    talk: !/-B\d+$/.test(sh.id),
  };
}
function vkeep(sh) {
  const fl = $('#vfilter').value;
  return fl === 'all' ? true : !!vcat(sh)[fl];
}

/* Bản thu nhỏ cho lưới — ảnh gốc chỉ nạp khi phóng to (lightbox) hoặc tải về */
function thumb(u, w) { return u ? u + (u.includes('?') ? '&' : '?') + 'w=' + (w || 420) : u }

function stale(sh) {
  if (!sh.prompt || !sh.prompt.trim()) return false;
  if (sh.prompt_text === undefined || sh.prompt_text === null) return false;
  return (sh.prompt_text || '').trim() !== (sh.text || '').trim();
}
function estBadge(sh) {
  const { n, sec } = estimate(sh.text);
  const dur = sh.dur || 10;
  if (!n) return `<span class="est empty" title="Chưa có lời thoại">— / ${dur}s</span>`;
  let cls = 'ok', tip = `${n} từ · vừa khít ${dur}s`;
  if (sec > dur) { cls = 'over'; tip = `${n} từ ≈ ${sec.toFixed(1)}s — THỪA LỜI so với ${dur}s. Hãy tách bớt sang video khác hoặc đổi lên 10s.` }
  else if (sec < dur * 0.35) { cls = 'thin'; tip = `${n} từ ≈ ${sec.toFixed(1)}s — hơi trống so với ${dur}s. Có thể gộp với dòng kế hoặc hạ xuống 6s.` }
  return `<span class="est ${cls}" title="${tip}">≈${sec.toFixed(1)}s / ${dur}s</span>`;
}
function newVidId() {
  let mx = 0;
  DATA.scenes.forEach(s => (s.shots || []).forEach(x => {
    const m = /(\d+)/.exec(x.id); if (m) mx = Math.max(mx, +m[1]);
  }));
  return 'VID_' + String(mx + 1).padStart(3, '0');
}


/* --- Prompt nhạc Suno cho nhịp không thoại: 2 lựa chọn, bấm để chép --- */
function musicBox(sh) {
  const m = sh.music;
  if (!m || !m.a) return '';
  const opt = (tag) => {
    const val = m[tag] || '', kind = m[tag + '_kind'] || '';
    if (!val) return '';
    return `<div class="mopt">
  <div class="mhead"><b>${tag.toUpperCase()}</b>
    <span class="hint">${esc(kind)}</span>
    <span style="flex:1"></span>
    <button class="sm" data-mcopy="${tag}" title="Chép prompt này để dán sang Suno">⧉ chép</button></div>
  <textarea class="mtext" data-mk="${tag}" spellcheck="false">${esc(val)}</textarea>
</div>`;
  };
  const role = m.role ? `<div class="mrole"><b>Vai trò nhạc:</b> ${esc(m.role)}</div>` : '';
  return `<details class="music"><summary>🎵 Nhạc Suno — ${esc(m.emo || '')}</summary>
${role}${opt('a')}${opt('b')}</details>`;
}

function shotRow(sc, sh, idx) {
  const f = sfById(sh.sf);
  const opts = allSF().map(x => x.f).filter(x => !x.id.startsWith('REF_'));
  const vjob = viecHienTai(sh.id); const vrun = vjob.state === 'running';
  const d = document.createElement('div');
  d.className = 'shot' + (!f || !f.image ? ' warn-sf' : '')
    + (sh.vstatus === 'approved' ? ' vok' : sh.vstatus === 'rejected' ? ' vbad' : sh.video ? ' vnew' : '');
  // Badge ĐÈ LÊN ẢNH đã bỏ 2026-08-09 — nó che mất chính cái ảnh đang cần nhìn.
  // Badge CẠNH MÃ SHOT thì thêm lại 2026-08-15: hai thứ khác nhau, đừng gộp.
  // Viền thẻ (--okline #1e5c3a) quá nhạt để đọc ở khoảng cách xa, còn nút
  // ✓/✎/✕ không mang class `on` nên không cho biết trạng thái nào đang bật.
  d.innerHTML = `
<div class="sf-side">
  <div class="fr">${f && f.image ? `<img src="${thumb(f.image, 640)}" loading="lazy" decoding="async">`
      : `<div class="no">${f ? 'SF chưa có ảnh' : 'chưa gán SF'}</div>`}</div>
  <div class="pick">
    <button class="sm sfpick" data-sfpick title="Bấm để chọn Start frame — có xem trước ảnh">
      ${f && f.image ? `<img src="${thumb(f.image, 80)}" loading="lazy">` : '<span class="nosf">⚠</span>'}
      <span>${esc(sh.sf || 'chưa chọn SF')}</span> ▾</button>
  </div>
  ${f ? `<div class="hint" style="font-size:11px">${esc(f.label || '')}</div>` : ''}
  ${/* Ô `goc` NẰM NGAY DƯỚI ẢNH, không phải ở cột giữa: công dụng của nó là
       đọc song song với tấm ảnh để biết SF có đúng khung không. Tách sang cột
       khác là mắt phải nhảy qua nhảy lại, mất đúng cái lợi đó. */''}
  <textarea class="sf-goc" data-k="goc"
    title="Tiêu chuẩn khung của DÒNG VIDEO này — đổi SF nào vào cũng phải đạt. Gõ vào đây là lưu vào shot."
    placeholder="🎥 Góc máy: ai nét · ai vai-gáy · ai quay lưng · hậu cảnh mờ?">${esc(sh.goc || (f && f.goc) || '')}</textarea>
</div>
<div class="sh-main">
  <div class="sh-head">
    <span class="vid">${esc(sh.id)}</span>${stag(sh.vstatus)}
    <select class="dur" data-dur>
      <option value="6" ${sh.dur == 6 ? 'selected' : ''}>6s</option>
      <option value="10" ${sh.dur == 10 ? 'selected' : ''}>10s</option>
    </select>
    ${estBadge(sh)}
    ${stale(sh) ? `<span class="stale" title="Bạn đã sửa lời thoại sau khi prompt video được viết. Prompt hiện tại mô tả bản thoại cũ — bảo AI viết lại prompt cho khớp, rồi bấm ✓ đã khớp.">⚠ thoại đã đổi — prompt video chưa viết lại</span>
    <button class="sm" data-sync title="Đánh dấu prompt đã khớp với thoại hiện tại">✓ đã khớp</button>`: ''}
    <span style="flex:1"></span>
    <button class="sm" data-ins title="Thêm một video trống ngay dưới dòng này">＋ Thêm dưới</button>
    <button class="sm" data-mv="-1">↑</button><button class="sm" data-mv="1">↓</button>
    <button class="sm bad-b" data-del title="Xóa video này khỏi kịch bản">🗑</button>
  </div>
  <textarea class="script" data-k="text" spellcheck="false" placeholder="Lời thoại / hành động trong kịch bản…">${esc(sh.text || '')}</textarea>
  <details><summary>Prompt video</summary>
    <textarea data-k="prompt" spellcheck="false" placeholder="Prompt gửi Grok…">${esc(sh.prompt || '')}</textarea></details>
  ${musicBox(sh)}
  <textarea class="notes vnotes" data-k="notes"
    placeholder="Ghi chú">${esc(sh.notes || '')}</textarea>
  <div class="noterow">
    <button class="sm ai ${sh.ai_request ? 'on' : ''}" data-va="ai"
      title="Ghi rõ vấn đề ở ô trên rồi bấm — mục này vào danh sách yêu cầu AI ở header">
      ${sh.ai_request ? '✓ đã gửi AI' : '🤖 Yêu cầu AI'}</button>
  </div>
</div>
<div class="v-side">
  <div class="vbox">
    ${sh.video ? `<video src="${sh.video}" controls preload="none"></video>`
      : `<div class="vempty">chưa có video<br><span>kéo–thả .mp4 vào đây<br>hoặc bấm Tạo video</span></div>`}
    ${vrun ? `<div class="run"><div class="spin"></div><div>${esc(vjob.msg || '')}</div></div>` : ''}
  </div>
  ${(sh.vversions && sh.vversions.length > 1) ? `<div class="vers">${sh.vversions.map((v, i) =>
        `<span class="vwrap"><button class="sm${v.file === sh.vpicked ? ' vpick' : ''}" data-vv="${v.file}"
      title="${v.at}${v.file === sh.vpicked ? ' — ĐANG DÙNG' : ''}">v${i + 1}${v.file === sh.vpicked ? (sh.vstatus === 'approved' ? ' ✓' : ' •') : ''}</button>
      <span class="vx" data-vvdel="${v.file}" title="Xoá bản v${i + 1} này">×</span></span>`).join('')}</div>` : ''}
  <div class="vacts">
    <button class="sm pri" data-va="gen" ${vrun ? 'disabled' : ''}>${sh.video ? 'Tạo lại' : 'Tạo video'}</button>
    <button class="sm ok-b" data-va="approved">✓</button>
    <button class="sm bad-b" data-va="rejected">✕</button>
    ${sh.video ? `<button class="sm" data-va="frame" title="Tua video tới khung ưng ý rồi bấm — lưu khung đó thành SF mới (tự chọn dòng dùng sau)">📸→SF</button>` : ''}
    ${sh.video ? `<button class="sm" data-va="framedown" title="Tua video tới khung cuối rồi bấm — cắt khung đó thành SF và GÁN LUÔN cho video ngay bên dưới, để hai clip nối liền không bị khựng">📸↓</button>` : ''}
    ${sh.video ? `<a class="sm dl" href="${sh.video}?dl=1&name=${encodeURIComponent(sh.id)}" download="${sh.id}.mp4" title="Tải video về máy">⬇</a>` : ''}
    ${sh.video ? '<button class="sm bad-b" data-va="delv">🗑</button>' : ''}
  </div>
  ${vjob.state === 'error' ? `<div class="err" style="padding:0">⚠ ${esc(vjob.msg)}</div>` : ''}
  ${sh.ai_done ? `<div class="aidone"><span>🤖 ${esc(sh.ai_done)}</span>
    <span class="x" data-va="donex" title="Xong việc này rồi — xoá dòng báo để ghi yêu cầu mới">✕ dọn</span></div>`: ''}
</div>`;
  const fr = d.querySelector('.fr');
  fr.onclick = () => { if (f && f.image) lbOpenAt(f) };
  fr.title = 'Bấm để phóng to · kéo–thả ảnh vào đây để tạo SF MỚI và gán cho dòng này';
  fr.ondragover = e => { e.preventDefault(); fr.classList.add('drop') };
  fr.ondragleave = () => fr.classList.remove('drop');
  fr.ondrop = async e => {
    e.preventDefault(); fr.classList.remove('drop');
    const file = e.dataTransfer.files[0];
    if (!file || !file.type.startsWith('image/')) { bao('Chỉ nhận file ảnh.'); return }
    await dropSFtoShot(sc, sh, file, file.name);
  };

  d.querySelectorAll('[data-mcopy]').forEach(b => b.onclick = async () => {
    const t = d.querySelector(`[data-mk="${b.dataset.mcopy}"]`);
    try {
      await navigator.clipboard.writeText(t.value);
      const o = b.textContent; b.textContent = '✓ đã chép'; setTimeout(() => b.textContent = o, 1400);
    } catch (e) { t.select(); document.execCommand('copy') }
  });
  d.querySelectorAll('[data-mk]').forEach(t => t.onchange = () => {
    sh.music = sh.music || {}; sh.music[t.dataset.mk] = t.value; save();
  });
  const vbox = d.querySelector('.vbox');
  vbox.ondragover = e => { e.preventDefault(); vbox.classList.add('drop') };
  vbox.ondragleave = () => vbox.classList.remove('drop');
  vbox.ondrop = async e => {
    e.preventDefault(); vbox.classList.remove('drop');
    const file = e.dataTransfer.files[0]; if (!file) return;
    await fetch('/api/upload-video?sf=' + encodeURIComponent(sh.id), { method: 'POST', body: file });
    await load();
  };
  d.querySelectorAll('[data-vv]').forEach(el => el.onclick = async () => {
    await fetch(`/api/pick-vversion?sf=${encodeURIComponent(sh.id)}&file=${encodeURIComponent(el.dataset.vv)}`, { method: 'POST' });
    await load();
  });
  d.querySelectorAll('[data-vvdel]').forEach(el => el.onclick = async e => {
    e.stopPropagation();
    if (!await hoi('Xoá hẳn bản video này khỏi ổ đĩa?\n\n' + el.dataset.vvdel + '\n\nKhông khôi phục được.', { bad: true })) return;
    const r = await (await fetch(`/api/del-vversion?sf=${encodeURIComponent(sh.id)}&file=${encodeURIComponent(el.dataset.vvdel)}`,
      { method: 'POST' })).json();
    if (!r.ok) { bao(r.err || 'Không xoá được'); return }
    await load();
  });
  d.querySelectorAll('[data-va]').forEach(b => b.onclick = async () => {
    const a = b.dataset.va;
    if (a === 'gen') {
      if (sh.vstatus === 'approved' && !await hoi(
        'Video này ĐÃ DUYỆT — bản đang hiển thị là bản bạn chốt.\n\n' +
        'Tạo bản mới sẽ KHÔNG thay bản đã duyệt; bản mới nằm ở dãy bản để so.\n' +
        'Muốn thay hẳn thì bấm ✓ lần nữa để bỏ duyệt trước.\n\nVẫn tạo thêm bản mới?')) return;
      SUBMITTING[sh.id] = { state: 'running', msg: 'đang gửi yêu cầu…' }; render();
      try {
        const request = await postJob('/api/genvideo?sf=' + encodeURIComponent(sh.id), newJobKey());
        if (!request.body.ok) { delete SUBMITTING[sh.id]; render(); }
        else SUBMITTING[sh.id] = { state: 'queued', msg: 'đã nhận · chờ lịch bền vững',
          job_id: request.body.job_id, job_ids: request.body.job_ids || [] };
      } catch (error) {
        delete SUBMITTING[sh.id]; render(); throw error;
      }
      return
    }
    if (a === 'donex') { delete sh.ai_done; save(); render(); return }
    if (a === 'ai') {
      sh.ai_request = !sh.ai_request;
      if (sh.ai_request) delete sh.ai_done;   // yêu cầu mới → báo cáo cũ hết hiệu lực
      save(); render(); return
    }
    if (a === 'frame') { await frameToSF(sc, sh, d); return }
    if (a === 'framedown') { await frameToNextShot(sc, sh, idx, d); return }
    if (a === 'delv') {
      if (!await hoi('Xóa video ' + sh.id + ' (cả lịch sử)?', { bad: true })) return;
      await fetch('/api/delete-video?sf=' + encodeURIComponent(sh.id), { method: 'POST' }); await load(); return
    }
    // bấm lại đúng trạng thái đang có = bỏ đánh dấu → đó là cách mở khoá bản chốt
    sh.vstatus = (sh.vstatus === a) ? null : a;
    save(); render();
  });
  d.querySelector('[data-sfpick]').onclick = () => openSFPick(sc, sh);
  d.querySelector('[data-dur]').onchange = e => { sh.dur = +e.target.value; save(); render() };
  if ((sh.notes || '').trim()) d.classList.add('hasnote');
  d.querySelectorAll('[data-k]').forEach(el => el.oninput = e => {
    sh[e.target.dataset.k] = e.target.value; save();
    if (e.target.dataset.k === 'notes')
      d.classList.toggle('hasnote', !!e.target.value.trim());
    if (e.target.dataset.k === 'text') {
      const badge = d.querySelector('.sh-head .est');
      if (badge) badge.outerHTML = estBadge(sh);
    }
  });
  d.querySelectorAll('[data-mv]').forEach(b => b.onclick = () => {
    const j = idx + (+b.dataset.mv); if (j < 0 || j >= sc.shots.length) return;
    [sc.shots[idx], sc.shots[j]] = [sc.shots[j], sc.shots[idx]]; save(); render()
  });
  d.querySelector('[data-del]').onclick = async () => {
    if (!await hoi('Xóa ' + sh.id + '?', { bad: true })) return;
    sc.shots.splice(idx, 1); save(); render()
  };

  d.querySelector('[data-ins]').onclick = () => {
    sc.shots.splice(idx + 1, 0, {
      id: newVidId(), sf: sh.sf, dur: 10, text: '',
      prompt: '', status: 'todo', notes: ''
    });
    save(); render();
  };
  const syncb = d.querySelector('[data-sync]');
  if (syncb) syncb.onclick = () => { sh.prompt_text = sh.text || ''; save(); render() };
  return d;
}

// Cắt khung hiện tại của video này thành SF rồi GÁN LUÔN cho shot ngay bên dưới —
// dùng khi muốn hai clip nối liền: frame cuối clip trước = frame đầu clip sau.
async function frameToNextShot(sc, sh, idx, rowEl) {
  const next = sc.shots[idx + 1];
  if (!next) { bao('Đây là video cuối của scene, không có dòng nào bên dưới để gán.'); return }
  const v = rowEl.querySelector('.vbox video');
  if (!v) { bao('Chưa có video'); return }
  const t = v.currentTime;
  if (!t || t < 0.05) {
    bao('Hãy TUA video tới đúng khung hình muốn lấy (thường là khung CUỐI), bấm tạm dừng, rồi mới bấm 📸↓.\n\nHiện con trỏ đang ở giây ' + t.toFixed(2));
    return;
  }
  const used = new Set(sc.sfs.map(f => f.id));
  let suggest = '';
  for (let i = 0; i < 26; i++) {
    const c = String.fromCharCode(65 + i);
    const cand = `SF-${sc.id}-${c}`;
    if (!used.has(cand)) { suggest = cand; break }
  }
  const old = next.sf || '(chưa có)';
  if (!await hoi(`Cắt khung tại giây ${t.toFixed(2)} của ${sh.id}\n→ tạo SF "${suggest}"\n→ GÁN cho ${next.id} (đang dùng ${old}).\n\nTiếp tục?`)) return;
  const r = await (await fetch(`/api/frame-to-sf?shot=${encodeURIComponent(sh.id)}&t=${t}&sf=${encodeURIComponent(suggest)}`,
    { method: 'POST' })).json();
  if (!r.ok) { bao('Lỗi: ' + r.err); return }
  await load();
  // gán cho shot dưới sau khi board đã nạp lại (next là tham chiếu cũ nên tìm lại theo id)
  const sc2 = DATA.scenes.find(s => s.id === sc.id);
  const n2 = sc2 && sc2.shots.find(x => x.id === next.id);
  if (n2) { n2.sf = r.sf; save(); render(); }
  bao(`Đã tạo ${r.sf} và gán cho ${next.id}.\n\nNhớ bảo AI viết lại prompt video của ${next.id} cho khớp khung mới.`);
}

async function frameToSF(sc, sh, rowEl) {
  const v = rowEl.querySelector('.vbox video');
  if (!v) { bao('Chưa có video'); return }
  const t = v.currentTime;
  if (!t || t < 0.05) {
    bao('Hãy TUA video tới đúng khung hình bạn muốn giữ (bấm play rồi tạm dừng), sau đó mới bấm 📸→SF.\n\nHiện con trỏ đang ở giây ' + t.toFixed(2));
    return;
  }
  // gợi ý mã SF kế tiếp trong scene
  const used = new Set(sc.sfs.map(f => f.id));
  let suggest = '';
  for (let i = 0; i < 26; i++) {
    const c = String.fromCharCode(65 + i);
    const cand = `SF-${sc.id}-${c}`;
    if (!used.has(cand)) { suggest = cand; break }
  }
  const id = await nhap(`Lưu khung hình tại giây ${t.toFixed(2)} của ${sh.id} thành SF mới.`,
    { tieude: 'Cắt khung thành SF mới', macdinh: suggest, dong: 'Tạo SF' });
  if (!id) return;
  const r = await (await fetch(`/api/frame-to-sf?shot=${encodeURIComponent(sh.id)}&t=${t}&sf=${encodeURIComponent(id.trim())}`,
    { method: 'POST' })).json();
  if (r.ok) { await load(); bao('Đã tạo ' + r.sf + ' từ khung hình này.\nXem ở tab "Start frames", và nó đã có trong dropdown chọn SF của mọi dòng.'); }
  else bao('Lỗi: ' + r.err);
}

async function addShot(sid) {
  const sc = DATA.scenes.find(s => s.id === sid);
  const n = sc.shots.length + 1;
  const id = await nhap('Mã của dòng video mới:',
    { tieude: 'Thêm dòng video', macdinh: 'VID_' + String(n).padStart(3, '0'), dong: 'Thêm' });
  if (!id) return;
  sc.shots.push({ id: id.trim(), sf: (sc.sfs[0] || {}).id || '', dur: 10, text: '', prompt: '', status: 'todo', notes: '' });
  save(); render();
}

/* ---------------- DÁN ẢNH ---------------- */
let SEL = null;   // SF đang được chọn để Ctrl+V đè ảnh

function nextSFId(sc) {
  const used = new Set(sc.sfs.map(f => f.id));
  for (let i = 0; i < 26; i++) {
    const c = `SF-${sc.id}-${String.fromCharCode(65 + i)}`;
    if (!used.has(c)) return c;
  }
  return `SF-${sc.id}-${Date.now() % 1000}`;
}

async function uploadTo(sfId, blob, name) {
  await fetch(`/api/upload?sf=${encodeURIComponent(sfId)}&name=${encodeURIComponent(name || 'paste.png')}`,
    { method: 'POST', body: blob });
}


// Kéo–thả ảnh vào ô SF bên tab Kịch bản: tạo SF MỚI (vào danh sách SF của scene,
// hiện trong dropdown mọi dòng video) rồi GÁN luôn cho chính dòng vừa thả.
// Không ghi đè ảnh của SF đang dùng — SF cũ có thể đang được dòng khác dùng chung.
async function dropSFtoShot(sc, sh, blob, name) {
  const id = await nhap(
    'Tạo SF MỚI từ ảnh này và gán cho ' + sh.id + '.\n' +
    'SF hiện tại (' + (sh.sf || 'chưa có') + ') KHÔNG bị thay — nó có thể đang dùng ở dòng khác.',
    { tieude: 'Kéo ảnh vào dòng video', macdinh: nextSFId(sc), dong: 'Tạo & gán' });
  if (!id) return;
  const key = id.trim();
  if (find(key)) { bao('Mã ' + key + ' đã tồn tại. Chọn mã khác.'); return }
  sc.sfs.push({
    id: key, label: '(ảnh kéo vào)',
    desc: 'Ảnh kéo thẳng vào dòng ' + sh.id + ' ở tab Kịch bản.',
    prompt: '', status: 'proposed', notes: '', usedBy: [], refs: { chars: [], bg: null }
  });
  sh.sf = key;                                  // gán ngay cho dòng vừa thả
  if (sh.prompt) sh.prompt = sh.prompt.replace(/Start frame:\s*\S+/, 'Start frame: ' + key);
  await fetch('/api/board', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(DATA)
  });
  await uploadTo(key, blob, name);
  await load();
}

async function createSFfromBlob(sc, blob, name) {
  const id = await nhap('Tạo SF mới từ ảnh này.',
    { tieude: 'SF mới từ ảnh', macdinh: nextSFId(sc), dong: 'Tạo SF' });
  if (!id) return;
  const key = id.trim();
  if (find(key)) { bao('Mã ' + key + ' đã tồn tại. Chọn mã khác.'); return }
  sc.sfs.push({
    id: key, label: '(ảnh dán vào)', desc: 'Frame lấy lại / ảnh dán từ ngoài.',
    prompt: '', status: 'proposed', notes: '', usedBy: [], refs: { chars: [], bg: null }
  });
  await fetch('/api/board', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(DATA) });
  await uploadTo(key, blob, name);
  await load();
  bao('Đã tạo ' + key + '.\nSang tab "Kịch bản" là chọn được nó trong dropdown SF của mọi dòng video.');
}

function pasteBox(sc) {
  const d = document.createElement('button');
  d.className = 'sm pastebox';
  d.textContent = '＋ SF từ ảnh';
  d.title = 'Bấm để chọn file ảnh · hoặc bấm rồi Ctrl+V để dán ảnh trong clipboard · '
    + 'hoặc kéo–thả file ảnh thẳng vào nút này';
  const chon = () => {   // bấm = vừa chọn đích cho Ctrl+V, vừa mở hộp chọn file
    SEL = { scene: sc, sf: null };
    document.querySelectorAll('.pastebox').forEach(x => x.classList.remove('on'));
    d.classList.add('on');
    document.querySelectorAll('.card').forEach(c => c.classList.remove('sel'));
  };
  d.onclick = () => {
    chon();
    const inp = document.createElement('input');
    inp.type = 'file'; inp.accept = 'image/*';
    inp.onchange = async () => { const f = inp.files[0]; if (f) await createSFfromBlob(sc, f, f.name) };
    inp.click();
  };
  d.ondragover = e => { e.preventDefault(); d.classList.add('on') };
  d.ondragleave = () => d.classList.remove('on');
  d.ondrop = async e => {
    e.preventDefault(); d.classList.remove('on');
    const f = e.dataTransfer.files[0]; if (f) await createSFfromBlob(sc, f, f.name);
  };
  return d;
}

// Ctrl+V toàn trang
window.addEventListener('paste', async e => {
  if (VIEW !== 'sf') return;
  const items = [...(e.clipboardData?.items || [])].filter(i => i.type.startsWith('image/'));
  if (!items.length) return;
  e.preventDefault();
  const blob = items[0].getAsFile();
  if (!SEL) { bao('Hãy bấm chọn một thẻ SF (để thay ảnh) hoặc ô "Tạo SF mới từ ảnh" trước, rồi Ctrl+V.'); return }
  if (SEL.sf) { await uploadTo(SEL.sf, blob, 'paste.png'); await load(); }
  else if (SEL.scene) { await createSFfromBlob(SEL.scene, blob, 'paste.png'); }
});

/* ---------------- CHẾ ĐỘ START FRAME ---------------- */
// ── TẠO LẠI THEO LÔ ──
// TÍCH GÌ TẠO NẤY. Các ảnh tích chung một lần được gửi trong MỘT tin nhắn nên
// vẽ cùng lúc và đồng bộ với nhau. Nếu tích lẫn nhiều địa điểm thì server tự
// tách thành nhiều tin — không phải để "chia lô", mà vì mỗi địa điểm có luật
// chung riêng, gửi một lần ở đầu tin nhắn.
const TICK = new Set();
function veLoBar() {
  $('#lobar').style.display = TICK.size ? 'flex' : 'none';
  $('#lonum').textContent = TICK.size;
}
function tick(id, on) {
  on ? TICK.add(id) : TICK.delete(id);
  veLoBar();
}
function loBo() {
  TICK.clear();
  document.querySelectorAll('input[data-tick]').forEach(e => e.checked = false);
  $('#lobar').style.display = 'none';
}
async function dungHet() {
  if (!await hoi('DỪNG TẤT CẢ?\n\n· tắt mọi "Chạy hết"\n· vứt sạch hàng đợi\n· bấm STOP trên đoạn chat đang sinh (cắt thật, không để nó vẽ tiếp)\n· ĐÓNG cửa sổ Chrome đang chạy (ảnh render dở sẽ mất)\n\nMở lại Chrome ở ⚙ Tài khoản.', { bad: true, dong: 'Dừng tất cả' })) return;
  const r = await (await fetch('/api/dung-het', { method: 'POST' })).json();
  $('#runstatus').textContent = `đã dừng — bỏ ${r.bo} việc chờ, cắt ${r.dung} việc đang chạy`
    + (r.da_bam_stop ? `, bấm stop trên ${r.da_bam_stop} đoạn chat` : '')
    + (r.dong_chrome && r.dong_chrome.length ? `, đóng ${r.dong_chrome.length} cửa sổ Chrome` : '');
  await load();
  setTimeout(() => $('#runstatus').textContent = '', 12000);
}
async function huyHang() {
  const r = await (await fetch('/api/huy', { method: 'POST' })).json();
  $('#runstatus').textContent = `đã bỏ ${r.bo} việc chờ`
    + (r.dang_chay && r.dang_chay.length ? ` · còn ${r.dang_chay.length} việc ĐANG chạy, để chạy nốt` : '');
  setTimeout(() => $('#runstatus').textContent = '', 9000);
}
/* Chọn hết trong PHẠM VI MỘT SCENE — lô chạy theo địa điểm nên chọn cả scene là
   thao tác hay dùng nhất; tickHet() quét cả trang thì rộng quá. */
// ---- CHỌN NHANH THEO TASK -------------------------------------------------
// Một lượt gửi quá nhiều ảnh thì ChatGPT hay bỏ sót và lẫn mặt, nên thực tế cứ
// ~10 ảnh một tin là vừa. Chia sẵn thành từng khối 10 để khỏi phải tích tay
// từng thẻ rồi đếm nhẩm; phần dư dồn vào task cuối.
const TASK_CO = 10;

// KHOÁ NHÓM của một thẻ — phải khớp cách BOARD gom lô, nếu không nút T hứa một
// đằng mà board chạy một nẻo (bấm T1 "10 ảnh" rồi board xé thành 5 tin nhắn).
//   · scene thường → theo địa điểm (refs.bg)
//   · REF_PROP_…   → đạo cụ, một nhóm
//   · REF_<TÊN>_…  → theo NHÂN VẬT: chân dung và mọi bộ trang phục của cùng một
//     người phải vẽ chung một chat, nếu không khuôn mặt trôi dần qua từng bộ.
function khoaNhom(f) {
  const id = f.id || '';
  if (id.startsWith('REF_PROP_')) return 'PROP';
  const m = /^REF_([A-Z0-9]+)_/.exec(id);
  if (m) return 'NV:' + m[1];
  return (f.refs || {}).bg || '';
}

// Hai luật khi chia:
//   1. MẶC ĐỊNH CHỈ THẺ CHƯA CÓ ẢNH. Nút này để TẠO, mà thẻ đã có ảnh thì vòng
//      quét nền bỏ qua — chia theo tổng số thì "T1 (10)" thực chất gửi 3 ảnh.
//      `lai=true` là CHẾ ĐỘ TẠO LẠI: chia trên MỌI thẻ, dùng khi scene đã đủ
//      ảnh mà user vẫn muốn vẽ lại. Đường tạo tay (`/api/tao-lo`) chạy với
//      `tay=True` nên không bị bộ lọc "đã có ảnh" gạt — chia được là chạy được.
//   2. MỘT TASK = MỘT NHÓM (địa điểm, hoặc nhân vật với thẻ REF). Một tin nhắn
//      chỉ mang được một khối `luatchung`, nên lô lẫn hai địa điểm bị board CHẶN
//      THẲNG. Đã đo trên phim này: S12 có 2 địa điểm, S15 có 2 — chia thuần theo
//      thứ tự là hai scene đó bấm phát nào chặn phát ấy.
function taskCua(list, lai) {
  const con = lai ? list.slice() : list.filter(f => !f.image);
  const theoBg = new Map();
  for (const f of con) {
    const k = khoaNhom(f);
    if (!theoBg.has(k)) theoBg.set(k, []);
    theoBg.get(k).push(f);
  }
  // CẮT ĐÚNG 10, DƯ BAO NHIÊU THÀNH TASK CUỐI. Không dồn phần dư ngược lên:
  // đã thử và sai — 14 thẻ dồn thành MỘT task 14 ảnh, phá đúng cái trần 10 sinh
  // ra để tránh ChatGPT lẫn mặt và bỏ sót ảnh. Thà một task 4 ảnh.
  const ra = [];
  for (const nhom of theoBg.values())
    for (let i = 0; i < nhom.length; i += TASK_CO) ra.push(nhom.slice(i, i + TASK_CO));
  return ra;
}

// Danh sách task của mỗi scene, chốt NGAY LÚC VẼ NÚT. Tính lại lúc bấm là sai:
// bộ lọc trên header có thể đang giấu bớt thẻ, và giữa hai thời điểm có thể vừa
// có ảnh mới về — nút ghi "10" mà tích ra 7 thẻ thì không ai hiểu vì sao.
let TASKS = {};
let TASKS_LAI = {};        // scene nào đang ở CHẾ ĐỘ TẠO LẠI (đã đủ ảnh)

function nutTask(sc, list) {
  // SCENE ĐỦ ẢNH THÌ CHUYỂN SANG CHIA TẠO LẠI, KHÔNG BIẾN MẤT (user chốt
  // 2026-08-14). Bản cũ ẩn nút T ngay khi scene hết thẻ thiếu — nhìn ra thành
  // "scene này có T, scene kia không" mà chẳng lý do nào hiện ở đâu, và user
  // muốn vẽ lại một scene thì không còn lối nào ngoài tích tay từng thẻ.
  let lai = false;
  let ts = taskCua(list, false);
  if (!ts.length) { lai = true; ts = taskCua(list, true); }
  TASKS[sc.id] = ts.map(ds => ds.map(f => f.id));
  TASKS_LAI[sc.id] = lai;
  // HIỆN CẢ KHI CHỈ CÓ MỘT TASK. Trước đây ẩn đi cho gọn, nhưng thành ra scene
  // này có T scene kia không, và không ai đoán được vì sao — mà lý do (10 thẻ
  // là ranh giới) chẳng hiện ở đâu cả.
  if (!ts.length) return '';
  const mo = ds => `${lai ? 'TẠO LẠI ' : ''}${ds.length} thẻ: `
    + ds.slice(0, 4).map(f => f.id).join(', ') + (ds.length > 4 ? '…' : '');
  // QUÁ NHIỀU TASK THÌ THẢ XUỐNG, KHÔNG RẢI NÚT (user báo 2026-08-14).
  // REF chia theo NHÂN VẬT chứ không theo địa điểm, mà mỗi nhân vật chỉ 1–3 thẻ
  // — 136 thẻ ra 22 task tí hon, hàng nút tràn ngang và bóp nút bên cạnh thành
  // chữ dọc. Ngưỡng 8 là chỗ hàng nút bắt đầu chiếm quá nửa dòng tiêu đề.
  if (ts.length > 8)
    return `<select class="sm tsel ${lai ? 're-b' : ''}" title="Chọn nhanh một task"
        onchange="if(this.value!=='')tickTask('${sc.id}',+this.value); this.value=''">
      <option value="">T ▾ ${ts.length} task${lai ? ' (tạo lại)' : ''}</option>`
      + ts.map((ds, i) => `<option value="${i}">T${i + 1} · ${mo(ds)}</option>`).join('')
      + `</select>`;
  return ts.map((ds, i) =>
    `<button class="sm ${lai ? 're-b' : ''}" onclick="tickTask('${sc.id}',${i})"
       title="${lai ? 'Scene đã đủ ảnh — tích để TẠO LẠI (ảnh mới đè lên ảnh cũ, bản cũ vẫn nằm trong dãy bản). '
                    : 'Tích các thẻ chưa có ảnh. '}${mo(ds)}"
     >T${i + 1}${lai ? '↻' : ''}<i class="tn">${ds.length}</i></button>`).join('');
}

function tickTask(sid, idx) {
  const ds = (TASKS[sid] || [])[idx] || [];
  if (!ds.length) { bao('Task này không còn thẻ nào.'); return }
  TICK.clear();                        // chọn task là chọn ĐÚNG task đó, không cộng dồn
  ds.forEach(id => TICK.add(id));
  document.querySelectorAll('input[data-tick]').forEach(e => { e.checked = TICK.has(e.dataset.tick) });
  veLoBar();
  $('#runstatus').textContent = `Task ${idx + 1}: đã chọn ${ds.length} thẻ của ${sid}`
    + (TASKS_LAI[sid] ? ' — TẠO LẠI, ảnh mới sẽ đè lên ảnh cũ' : '');
  setTimeout(() => $('#runstatus').textContent = '', 4000);
}

// bat=1 duyệt hết · bat=0 bỏ duyệt hết. Một hàm cho cả hai chiều — hai hàm gần
// giống nhau là chỗ để lệch nhau về sau.
async function duyetScene(sid, bat) {
  const r = DATA.scenes.find(s => s.id === sid);
  if (!r) return;
  const ds = bat ? r.sfs.filter(f => f.image && f.status !== 'approved')
                 : r.sfs.filter(f => f.status === 'approved');
  if (!ds.length) {
    bao(bat ? `Scene ${sid} không còn thẻ nào để duyệt (chưa có ảnh, hoặc đã duyệt hết).`
            : `Scene ${sid} không có thẻ nào đang ở trạng thái đã duyệt.`);
    return;
  }
  const ok = bat
    ? await hoi(`Đánh dấu ĐÃ DUYỆT cho ${ds.length} thẻ của ${sid}?\n\n`
      + `Ảnh đã duyệt là bản chốt: board sẽ không ghi đè, không tạo lại.`, { dong: 'Duyệt hết' })
    : await hoi(`Bỏ duyệt ${ds.length} thẻ của ${sid}?\n\n`
      + `Chúng về 'chờ duyệt'. Ảnh KHÔNG bị xoá — chỉ mất lớp khoá chống ghi đè,\n`
      + `nên từ giờ board được phép tạo lại đè lên chúng.`, { dong: 'Bỏ duyệt' });
  if (!ok) return;
  ds.forEach(f => f.status = bat ? 'approved' : 'proposed');
  save(); render();
  $('#runstatus').textContent = `${bat ? 'đã duyệt' : 'đã bỏ duyệt'} ${ds.length} thẻ của ${sid}`;
  setTimeout(() => $('#runstatus').textContent = '', 5000);
}

function tickScene(sid) {
  const sec = document.getElementById('sc-' + sid);
  if (!sec) return;
  const os = [...sec.querySelectorAll('input[data-tick]')].filter(e => e.offsetParent !== null);
  if (!os.length) { bao('Scene ' + sid + ' không có thẻ nào đang hiện để tích.'); return }
  os.forEach(e => { e.checked = true; TICK.add(e.dataset.tick) });
  veLoBar();
}
async function loChay() {
  if (!TICK.size) return;
  const ids = [...TICK];
  const nut = $('#lotao');
  if (nut) { nut.disabled = true; nut.textContent = '⏳ đang xếp…'; }
  try {
    const r = (await postJob('/api/tao-lo?sf=' + encodeURIComponent(ids.join(',')),
      newJobKey())).body;
    if (r.err) {
      // Nói NGAY và nói đủ. Hai ca hay gặp có lời khuyên riêng cho từng ca.
      bao(r.lan
        ? r.err + '\n\nBỏ tích bớt để chỉ còn MỘT địa điểm, rồi chạy địa điểm kia sau.'
        : r.khoa
          ? r.err + '\n\nDùng nút “📍 Ảnh gốc địa điểm” để chạy chúng trước, rồi quay lại đây.'
          : 'Không xếp được: ' + r.err);
      return;
    }
    const mo = Object.entries(r.lo || {})
      .map(([m, n]) => `${m.replace('SF-M-', '')}: ${n} ảnh`).join(' · ');
    const n = r.so_lo || Object.keys(r.lo || {}).length;
    $('#runstatus').textContent =
      `đã xếp ${n} tin nhắn — ${mo}`;
    loBo();
    setTimeout(() => $('#runstatus').textContent = '', 9000);
  } finally {
    if (nut) { nut.disabled = false; nut.textContent = '▶ Tạo ảnh đã chọn'; }
  }
}

// DẢI ẢNH CHỜ ĐÃ BỎ 2026-08-12 (user chốt). Lượt lệch giờ ghép thẳng theo thứ
// tự — về bao nhiêu ghép bấy nhiêu — nên không còn ảnh nào nằm chờ user bấm.
// Backend vẫn giữ hộp chờ (cho-phan-loai/) làm nơi ảnh hạ cánh và làm bản lưu,
// cùng route /api/gan-anh để gắn tay khi cần; chỉ giao diện là bỏ.

function card(sc, f) {
  const _bu = bgUsers(sc), _rank = sfRank(f, _bu), _otag = sfOrderTag(f, _bu);
  const _bg = (f.refs || {}).bg;
  const job = viecHienTai(f.id); const running = job.state === 'running';
  const refs = f.refs || { chars: [], bg: null };
  const d = document.createElement('div');
  const isM = isDiaDiem(f);
  const isR = f.id.startsWith('REF_');
  const isPortrait = isR && f.id.endsWith('_PORTRAIT');
  d.className = 'card ' + (f.status === 'approved' ? 'approved' : f.status === 'rejected' ? 'rejected' : f.status === 'revise' ? 'revise' : '')
    + (isM ? ' ismaster' : '');
  d.innerHTML = `
   <div class="thumb" data-sf="${f.id}"${f.turn ? ` title="Ảnh này ra từ LƯỢT ${f.turn}, ảnh thứ ${f.turn_o} của lượt${f.turn_port ? ', tài khoản cổng ' + f.turn_port : ''}.&#10;Tìm theo số lượt này trong log và trong thư mục ${PLDIR}/."` : ''}>
 ${f.image ? `<img src="${thumb(f.image, 320)}" loading="lazy" decoding="async"
    draggable="true" data-sfimg="${esc(f.id)}">` : `<div class="empty">Chưa có ảnh<br><b>Kéo–thả ảnh vào đây</b><br>hoặc bấm <b>Tạo ảnh</b></div>`}
 <label class="tick" title="Tích để tạo lại theo LÔ. Các thẻ cùng địa điểm đi chung một tin nhắn trong đúng đoạn chat của địa điểm đó; thẻ REF không có địa điểm nên gom chung một lô."
   onclick="event.stopPropagation()"><input type="checkbox" data-tick="${f.id}"
   ${TICK.has(f.id) ? 'checked' : ''} onchange="tick('${f.id}',this.checked)"></label>
 ${running ? `<div class="run"><div class="spin"></div><div>${esc(job.msg || 'đang tạo…')}</div></div>` : ''}
   </div>
   <div class="body">
 <div class="sfid">${isM ? '<span class="kindtag m">MASTER</span>' : ''}${esc(f.id)}${stag(f.status)}</div>
 <input class="ed" data-k="label" value="${esc(f.label || '')}" placeholder="Tên góc máy…">
 ${(isR && !isM) ? `<textarea class="ed" data-k="desc" placeholder="Mô tả / dùng cho beat nào…">${esc(f.desc || '')}</textarea>` : ''}
 ${/* `goc` sống trên SHOT (2026-08-09) — nó là tiêu chuẩn của vị trí trong
      timeline, thay SF nào vào cũng phải đạt. SF thường vì thế KHÔNG còn ô
      này. Chừa đúng hai loại KHÔNG shot nào trỏ tới nên `goc` của chúng
      chẳng có chỗ nào khác để ở: thẻ địa điểm và thẻ REF. */''}
 ${(isR || isM) ? `<textarea class="ed" data-k="goc" placeholder="🎥 Góc máy: ai nét · ai vai-gáy…">${esc(f.goc || '')}</textarea>` : ''}
 <div class="refrow"><b>Nhân vật</b><div class="picker" data-p="chars">
   ${(refs.chars || []).map(r => `<span class="pill ref" data-see="${esc(r)}" title="Bấm để xem ảnh"
     >${esc(r)}<b class="x" data-rm="${esc(r)}" title="Bỏ ref này">✕</b></span>`).join('')}
   <span class="pill add" data-add="chars">+ thêm</span></div></div>
 <div class="refrow"><b>Bối cảnh</b><div class="picker" data-p="bg">
   ${refs.bg ? `<span class="pill bg ref" data-see="${esc(refs.bg)}" title="Bấm để xem ảnh"
     >${esc(refs.bg)}<b class="x" data-rmbg="1" title="Bỏ ref này">✕</b></span>`
      : `<span class="pill add" data-add="bg">+ chọn</span>`}
   </div></div>
 ${(f.versions && f.versions.length > 1) ? `<div class="vers"><span class="vlab">bản:</span>
   ${f.versions.map((v, i) => `<span class="vwrap"><img src="${thumb(v.url, 240)}" loading="lazy"
     decoding="async" title="v${i + 1} · ${v.at}${v.turn ? ' · lượt ' + v.turn + ' ảnh #' + String(v.turn_o || 0).padStart(2, '0') : ''} — bấm để chọn làm ảnh chính"
     class="${v.file === f.picked ? 'cur' : ''}" data-v="${v.file}">
     <span class="vx" data-vdel="${v.file}" title="Xoá bản v${i + 1} này">×</span></span>`).join('')}</div>` : ''}
 <details><summary>Prompt</summary>
   <textarea data-k="prompt" spellcheck="false">${esc(f.prompt || '')}</textarea></details>
 <textarea class="notes" data-k="notes" placeholder="Ghi chú">${esc(f.notes || '')}</textarea>
 ${f.ai_done ? `<div class="aidone"><span>🤖 ${esc(f.ai_done)}</span>
   <span class="x" data-a="donex" title="Xong việc này rồi — xoá dòng báo để ghi yêu cầu mới">✕ dọn</span></div>`: ''}
   </div>
   ${/* `nhe` = cảnh báo nhẹ (lượt về thiếu ảnh nên thẻ này chưa có ảnh). Nó vẫn
        nằm ở ngăn kéo Hàng đợi và hộp 🐞, nhưng KHÔNG dán dải đỏ lên thẻ: thẻ
        trống đã tự nói lên điều đó, thêm dải nữa chỉ làm bảng đầy cảnh báo. */''}
   ${job.state === 'error' && !job.nhe ? `<div class="err">⚠ ${esc(job.msg)}</div>` : ''}
   <div class="acts">
 <button class="sm pri" data-a="gen" ${running ? 'disabled' : ''}>${f.image ? 'Tạo lại' : 'Tạo ảnh'}</button>
 <button class="sm ok-b" data-a="approved">✓</button>
 <button class="sm warn-b" data-a="revise">✎</button>
 <button class="sm bad-b" data-a="rejected">✕</button>
 <span style="flex:1"></span>
 ${f.image ? `<a class="sm dl" href="${f.image}?dl=1&name=${encodeURIComponent(f.id)}" download="${f.id}.png" title="Tải ảnh về máy">⬇</a>` : ''}
 ${f.image ? `<button class="sm" data-a="delimg"
   title="Xoá ẢNH của thẻ này (cả dãy bản) — GIỮ NGUYÊN thẻ, prompt và ref. Thẻ về trạng thái chưa có ảnh để tạo lại.">🧹</button>` : ''}
 <button class="sm ai ${f.ai_request ? 'on' : ''}" data-a="ai" title="Ghi rõ vấn đề ở ô ghi chú rồi bấm — mục này vào danh sách yêu cầu AI ở header">${f.ai_request ? '✓ đã gửi AI' : '🤖 Yêu cầu AI'}</button>
 <button class="sm bad-b" data-a="del">🗑</button>
   </div>`;

  const th = d.querySelector('.thumb');
  th.onclick = e => {
    if (e.shiftKey || !f.image) {   // chọn thẻ để dán đè (hoặc thẻ chưa có ảnh)
      SEL = { scene: sc, sf: f.id };
      document.querySelectorAll('.card').forEach(c => c.classList.remove('sel'));
      document.querySelectorAll('.pastebox').forEach(x => x.classList.remove('on'));
      d.classList.add('sel');
      return;
    }
    lbOpenAt(f);
  };
  // KÉO ẢNH CỦA THẺ NÀY đi nơi khác — đường sửa khi board gắn nhầm thẻ.
  const _im = d.querySelector('[data-sfimg]');
  if (_im) _im.ondragstart = e => {
    e.dataTransfer.setData('text/x-sf', f.id);
    e.dataTransfer.effectAllowed = 'copy';
  };
  th.ondragover = e => {
    e.preventDefault();
    th.classList.add(e.dataTransfer.types.some(t => t === 'text/x-sf')
      ? 'drop-sf' : 'drop')
  };
  th.ondragleave = () => th.classList.remove('drop', 'drop-sf');
  th.ondrop = async e => {
    e.preventDefault(); th.classList.remove('drop', 'drop-sf');
    // ảnh kéo TỪ THẺ KHÁC sang → chép sang thẻ này. CHÉP, không phải chuyển:
    //    thẻ nguồn giữ nguyên ảnh, thẻ đích được THÊM một bản mới. Nhờ vậy kéo
    //    nhầm không làm mất gì, và ảnh đã duyệt ở thẻ nguồn không bị đụng.
    const tu = e.dataTransfer.getData('text/x-sf');
    if (tu) {
      if (tu === f.id) return;
      if (!await hoi(`Chép ảnh đang dùng của ${tu} sang ${f.id}?\n\n`
        + `${tu} GIỮ NGUYÊN ảnh của nó — ${f.id} được thêm một bản mới và dùng bản đó.\n`
        + `Muốn bỏ ảnh ở ${tu} thì sau đó gắn ảnh đúng cho nó, hoặc xoá bản ở dãy "bản:".`)) return;
      const r = await (await fetch(`/api/sf-chuyen?tu=${encodeURIComponent(tu)}`
        + `&den=${encodeURIComponent(f.id)}`, { method: 'POST' })).json();
      if (!r.ok) { bao('Không chép được: ' + (r.err || '?')); return }
      $('#runstatus').textContent = `đã chép ảnh ${tu} → ${f.id}`;
      setTimeout(() => $('#runstatus').textContent = '', 7000);
      await load(); return
    }
    // 3) file thả từ máy → tải lên như cũ
    const file = e.dataTransfer.files[0]; if (!file) return;
    await fetch(`/api/upload?sf=${encodeURIComponent(f.id)}&name=${encodeURIComponent(file.name)}`, { method: 'POST', body: file });
    await load();
  };

  d.querySelectorAll('[data-k]').forEach(el => el.oninput = e => { f[e.target.dataset.k] = e.target.value; save() });
  d.querySelectorAll('[data-v]').forEach(el => el.onclick = async e => {
    e.stopPropagation();
    await fetch(`/api/pick-version?sf=${encodeURIComponent(f.id)}&file=${encodeURIComponent(el.dataset.v)}`, { method: 'POST' });
    await load();
  });
  d.querySelectorAll('[data-vdel]').forEach(el => el.onclick = async e => {
    e.stopPropagation();
    if (!await hoi('Xoá hẳn bản này khỏi ổ đĩa?\n\n' + el.dataset.vdel + '\n\nKhông khôi phục được.', { bad: true })) return;
    const r = await (await fetch(`/api/del-version?sf=${encodeURIComponent(f.id)}&file=${encodeURIComponent(el.dataset.vdel)}`,
      { method: 'POST' })).json();
    if (!r.ok) { bao(r.err || 'Không xoá được'); return }
    await load();
  });
  d.querySelectorAll('[data-see]').forEach(el => el.onclick = e => {
    if (e.target.classList.contains('x')) return;      // bấm ✕ thì để handler xoá lo
    const r = find(el.dataset.see);
    if (r && r.f && r.f.image) lbOpenAt(r.f); else bao(el.dataset.see + ' chưa có ảnh.');
  });
  d.querySelectorAll('[data-rm]').forEach(el => el.onclick = e => {
    e.stopPropagation();
    f.refs.chars = f.refs.chars.filter(x => x !== el.dataset.rm); save(); render()
  });
  const rmbg = d.querySelector('[data-rmbg]');
  if (rmbg) rmbg.onclick = e => { e.stopPropagation(); f.refs.bg = null; save(); render() };
  d.querySelectorAll('[data-add]').forEach(el => el.onclick = () => addRef(f, el.dataset.add));
  // Ô chọn số bản (×1…×4) đã bỏ 2026-08-09 — mỗi lần bấm tạo ĐÚNG MỘT bản.
  d.querySelectorAll('[data-a]').forEach(b => b.onclick = () => act(sc, f, b.dataset.a, 1));
  return d;
}

/* CHỌN REF BẰNG BẢNG ẢNH. Bản cũ dùng prompt() của trình duyệt: nó đổ mã của MỌI
   SF trong phim thành một cột chữ rồi bắt user GÕ LẠI cho đúng — sai một ký tự là
   "Không có mã". Nay dùng lại đúng hộp thoại #sfpick đã có (ảnh · ô lọc · bấm là
   chọn), chỉ thêm mode thứ ba. */
let REFPICK = null;
function addRef(f, kind) {
  REFPICK = { f, kind }; SPMODE = 'ref';
  $('#sp-q').value = '';
  veRefPick();
  sfpick.showModal();
  setTimeout(() => $('#sp-q').focus(), 30);
}
function veRefPick() {
  if (!REFPICK) return;
  const { f, kind } = REFPICK;
  const bg = kind === 'bg';
  $('#sp-t').textContent = `Chọn ảnh ${bg ? 'BỐI CẢNH' : 'NHÂN VẬT'} cho ${f.id}`;
  const q = ($('#sp-q').value || '').trim().toLowerCase();
  const hit = x => !q || x.f.id.toLowerCase().includes(q) || (x.f.label || '').toLowerCase().includes(q);
  // Nhân vật thì thẻ REF_ lên trước, bối cảnh thì thẻ địa điểm lên trước — đó là
  // thứ user tìm 9/10 lần, khỏi phải cuộn.
  const uu = x => bg ? (isDiaDiem(x.f) ? 0 : 1) : (x.f.id.startsWith('REF_') ? 0 : 1);
  const ds = allSF().filter(x => x.f.id !== f.id).filter(hit)
    .sort((a, b) => uu(a) - uu(b));
  const dang = bg ? [(f.refs || {}).bg] : ((f.refs || {}).chars || []);
  const the = ({ sc, f: x }) => `<div class="it${dang.includes(x.id) ? ' cur' : ''}" data-refpick="${esc(x.id)}">
${x.image ? `<img src="${thumb(x.image, 300)}" loading="lazy" decoding="async">`
      : '<div class="no">chưa có ảnh</div>'}
<b>${esc(x.id)}</b><i>${esc(x.label || '')}</i>
<u>${esc(sc.id)}${isDiaDiem(x) ? ' · thẻ địa điểm' : ''}</u></div>`;
  $('#sp-g').innerHTML = `<div class="hd">${ds.length} thẻ${q ? ' khớp "' + esc(q) + '"' : ''}`
    + `${dang.filter(Boolean).length ? ' · đang gắn: ' + esc(dang.filter(Boolean).join(', ')) : ''}</div>`
    + (ds.map(the).join('') || '<div style="padding:14px">Không có thẻ nào khớp.</div>');
  $('#sp-g').querySelectorAll('[data-refpick]').forEach(el => el.onclick = () => {
    const id = el.dataset.refpick;
    f.refs = f.refs || { chars: [], bg: null };
    if (bg) f.refs.bg = id;
    else if (!f.refs.chars.includes(id)) f.refs.chars.push(id);
    save();
    // Nhân vật gắn được NHIỀU nên để hộp thoại mở, chọn tiếp; bối cảnh chỉ một nên đóng.
    if (bg) { sfpick.close(); render() } else { render(); veRefPick() }
  });
}

async function act(sc, f, a, n) {
  if (a === 'gen') {
    n = Math.max(1, Math.min(+n || 1, 4));
    SUBMITTING[f.id] = { state: 'running', msg: n > 1 ? `đang gửi yêu cầu ${n} bản…` : 'đang gửi yêu cầu…' }; render();
    try {
      const request = await postJob(`/api/generate?sf=${encodeURIComponent(f.id)}&n=${n}`, newJobKey());
      if (!request.body.ok) { delete SUBMITTING[f.id]; render(); }
      else SUBMITTING[f.id] = { state: 'queued', msg: 'đã nhận · chờ lịch bền vững',
        job_id: request.body.job_id, job_ids: request.body.job_ids || [] };
    } catch (error) {
      delete SUBMITTING[f.id]; render(); throw error;
    }
    return
  }
  // XOÁ ẢNH, GIỮ THẺ — khác hẳn nút 🗑 (xoá cả thẻ khỏi kịch bản). Cần khi ảnh
  // ra không ưng: dọn sạch rồi tạo lại, prompt và ref vẫn nguyên.
  if (a === 'delimg') {
    const nv = (f.versions || []).length;
    if (!await hoi(`Xoá ẢNH của ${f.id}?\n\n`
      + `· xoá ảnh đang dùng${nv > 1 ? ` và cả ${nv} bản trong dãy bản` : ''}\n`
      + `· GIỮ NGUYÊN thẻ, prompt, ref, ghi chú\n`
      + (f.status === 'approved' ? '\n⚠ Thẻ này ĐÃ DUYỆT — xoá là mất bản đã chốt.\n' : '')
      + `\nKhông khôi phục được.`, { bad: true, dong: 'Xoá ảnh' })) return;
    await fetch('/api/delete-files?sf=' + encodeURIComponent(f.id), { method: 'POST' });
    await load();
    $('#runstatus').textContent = `đã xoá ảnh của ${f.id}`;
    setTimeout(() => $('#runstatus').textContent = '', 5000);
    return;
  }
  if (a === 'del') {
    if (!await hoi('Xóa ' + f.id + ' (kèm mọi ảnh & phiên bản)?', { bad: true })) return;
    await fetch('/api/delete-files?sf=' + encodeURIComponent(f.id), { method: 'POST' });
    sc.sfs = sc.sfs.filter(x => x.id !== f.id); save(); render(); return
  }
  if (a === 'donex') { delete f.ai_done; save(); render(); return }
  if (a === 'ai') {
    f.ai_request = !f.ai_request;
    if (f.ai_request) delete f.ai_done;       // yêu cầu mới → báo cáo cũ hết hiệu lực
    save(); render(); return
  }
  // 'dup' (Nhân bản) và 'copy' (Copy sang scene khác) đã bỏ 2026-08-09 cùng hai nút.
  f.status = (f.status === a) ? 'proposed' : a;
  save(); render();
}

async function addSF(sid) {
  const sc = DATA.scenes.find(s => s.id === sid);
  const id = await nhap('Mã của SF mới:',
    { tieude: 'Thêm SF', macdinh: 'SF-' + sid + '-' + String.fromCharCode(65 + sc.sfs.length), dong: 'Thêm' });
  if (!id) return; if (find(id.trim())) { bao('Mã đã tồn tại'); return }
  sc.sfs.push({ id: id.trim(), label: '', desc: '', prompt: '', status: 'proposed', notes: '', usedBy: [], refs: { chars: [], bg: null } });
  save(); render();
}
async function delScene(sid) {
  if (!await hoi('Xóa scene ' + sid + ' và toàn bộ SF?', { bad: true })) return;
  DATA.scenes = DATA.scenes.filter(s => s.id !== sid); save(); render();
}
/* ---- sáng / tối ---- */
function setTheme(t) {
  document.documentElement.dataset.theme = t;
  localStorage.setItem('sfboard-theme', t);
  $('#theme').textContent = t === 'dark' ? '🌙' : '☀️';
}
setTheme(localStorage.getItem('sfboard-theme') ||
  (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'));
$('#theme').onclick = () => setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');

$('#filter').onchange = render;
$('#vfilter').onchange = render;
document.querySelectorAll('#tabs button').forEach(b => b.onclick = () => {
  VIEW = b.dataset.v;
  localStorage.setItem('sfboard-view', VIEW);
  veTab();
  render();
});
function veTab() {   // đồng bộ nút sáng với VIEW — cần cả lúc mới tải trang
  document.querySelectorAll('#tabs button')
    .forEach(x => x.classList.toggle('on', x.dataset.v === VIEW));
}
veTab();
loadProjects();
veAutoVid();          // nhãn tạm; poll đầu tiên sẽ trả trạng thái thật
load();
