// Giao diện SF Board — phần JavaScript.
// Tách khỏi board.html 2026-08-12. Board phục vụ file này ở /ui/board.js.
// SỬA GIAO DIỆN THÌ SỬA ĐÂY, đừng dán ngược vào board.html.
// VIEW nhớ qua các lần tải lại: đang làm dở tab nào thì F5 vẫn ở tab đó. Lưu chung
// cho mọi phim như cờ sáng/tối — đây là chỗ đang làm việc, không phải thuộc tính phim.
const VIEW_OK = ['script', 'sf'];
let DATA = { scenes: [] }, JOBS = {}, AUTO = {}, T = null, DIRTY = false, MTIME = 0;
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
  const r = await (await fetch('/api/master?chay=1' + (lai ? '&lai=1' : ''), { method: 'POST' })).json();
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
  const dang = [], cho = [], loi = [];
  for (const [id, j] of Object.entries(JOBS || {})) {
    if (id.startsWith('LO:')) continue;              // ident lô — đã rải cho từng SF
    if (j.state === 'running') { if (!QSEEN[id]) QSEEN[id] = nay; dang.push([id, j]) }
    else {
      delete QSEEN[id];
      if (j.state === 'queued') cho.push([id, j]);
      else if (j.state === 'error') loi.push([id, j])
    }
  }
  const n = dang.length + cho.length;
  const b = $('#qbtn');
  if (b) b.textContent = n ? `▤ Hàng đợi (${n})` : '▤ Hàng đợi';
  const fab = $('#qfab'), fabn = $('#qfabn');
  if (fab) { fab.classList.toggle('has', !!n); if (fabn) fabn.textContent = n > 99 ? '99+' : n }
  const tom = $('#qtom');
  if (tom) tom.textContent = n || loi.length
    ? `${dang.length} đang chạy · ${cho.length} chờ${loi.length ? ' · ' + loi.length + ' lỗi' : ''}`
    : 'không có việc nào';
  const don = $('#qdon');
  if (don) don.style.display = loi.length ? '' : 'none';
  const con = new Set([...dang, ...cho, ...loi].map(x => x[0]));   // bỏ chọn id đã biến mất
  [...QTICK].forEach(i => { if (!con.has(i)) QTICK.delete(i) });
  qCapNhatChon();
  if (!QOPEN) return;
  const MAU = { running: '#16a34a', queued: '#9ca3af', error: '#dc2626' };
  const gom = {};
  for (const [tt, ds] of [['running', dang], ['queued', cho], ['error', loi]])
    for (const [id, j] of ds) {
      const g = (QNHOM || {})[id] || { bieu_tuong: '•', nhan: '(chưa xếp nhóm)' };
      const k = g.bieu_tuong + ' ' + g.nhan;
      (gom[k] = gom[k] || []).push([id, j, tt]);
    }
  const box = $('#qbody');
  if (!Object.keys(gom).length) {
    box.innerHTML = '<div class="hint" style="padding:10px 0">Hàng đợi trống — không có việc nào đang chạy hay đang chờ.</div>';
    return;
  }
  let h = '';
  for (const [ten, ds] of Object.entries(gom)) {
    h += `<div class="qg"><b>${esc(ten)}</b> <span class="hint">${ds.length} việc</span>`;
    for (const [id, j, tt] of ds) {
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
      h += `<div class="qi" title="${esc(j.msg || '')}">`
        + `<input type="checkbox" data-qt="${esc(id)}" ${QTICK.has(id) ? 'checked' : ''}
        onclick="qTick('${esc(id)}',this.checked)" style="flex:none;margin:0">`
        + `<span class="d" style="background:${MAU[tt]}"></span>`
        + `<span class="n">${esc(id)}</span>`
        + `<span class="t">${tt === 'running' ? (giay ? giay + 's' : '…') : tt === 'queued' ? 'chờ' : 'lỗi'}</span>`
        + nut + `</div>`;
      if (tt === 'error' && j.msg)
        h += `<div class="hint" style="font-size:11px;margin:-2px 0 4px 14px;color:#b45309">${esc(j.msg.slice(0, 150))}</div>`;
    }
    h += '</div>';
  }
  box.innerHTML = h;
}
/* CHỌN NHIỀU rồi xử một lượt — khúc giữa còn thiếu giữa "một cái" và "tất cả".
   Mỗi trạng thái cần một cách xử khác nhau nên gom vào đây, thay vì bắt user tự
   nhớ: đang chạy → dừng · đang chờ → huỷ · lỗi → dọn. */
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
    const u = st === 'running' ? '/api/dung-viec?sf=' + encodeURIComponent(id)
      : st === 'queued' ? '/api/huy-viec?sf=' + encodeURIComponent(id)
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
  delete JOBS[id]; veHangDoi();
}
async function dungMotViec(id) {
  if (!await hoi(`Dừng riêng "${id}"?\n\nCả lô chứa nó sẽ dừng theo — một lô là MỘT tin nhắn nên không cắt đôi được.\nChrome KHÔNG bị đóng, các việc khác vẫn chạy bình thường.`)) return;
  const r = await (await fetch('/api/dung-viec?sf=' + encodeURIComponent(id), { method: 'POST' })).json();
  if (!r.ok) { bao(r.err || 'Không dừng được'); return }
  $('#runstatus').textContent = `đang dừng ${id}…`;
  setTimeout(() => $('#runstatus').textContent = '', 7000);
}
async function huyMotViec(id) {
  const r = await (await fetch('/api/huy-viec?sf=' + encodeURIComponent(id),
    { method: 'POST' })).json();
  if (!r.ok) { bao(r.err || 'Không huỷ được'); return }
  $('#runstatus').textContent = `đã huỷ ${id}` + (r.con_lai ? ` · xếp lại lô ${r.con_lai} ảnh còn lại` : '');
  setTimeout(() => $('#runstatus').textContent = '', 7000);
  veHangDoi();
}
let QNHOM = {};
async function poll() {
  const r = await (await fetch('/api/jobs')).json();
  const j = r.jobs || {};
  QNHOM = r.nhom || {};
  const a = r.auto || {};
  const changed = JSON.stringify(j) !== JSON.stringify(JOBS) || JSON.stringify(a) !== JSON.stringify(AUTO);
  AUTO = a;
  const wasRunning = Object.values(JOBS).some(x => x.state === 'running');
  JOBS = j;
  veHangDoi();          // cập nhật số trên nút + nội dung ngăn kéo mỗi vòng poll
  // Lượt mới rơi vào diện chờ phân loại → nạp lại dải ảnh. So bằng chuỗi đếm
  // để không gọi /api/luot mỗi vòng poll khi chẳng có gì đổi.
  if (r.dan_ma !== undefined && !!r.dan_ma !== MAON) { MAON = !!r.dan_ma; veMa() }
  if (r.auto_vid !== undefined && !!r.auto_vid !== AVON) { AVON = !!r.auto_vid; veAutoVid() }
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

// ---------------------------------------------------------------- accounts
let ACCT_OPEN = false, ACCT_TIMER = null;
function toggleAccts() {
  ACCT_OPEN = !ACCT_OPEN;
  $('#acctpanel').style.display = ACCT_OPEN ? 'block' : 'none';
  $('#acctbtn').classList.toggle('on', ACCT_OPEN);
  if (ACCT_OPEN) { pollAccts(); ACCT_TIMER = setInterval(pollAccts, 4000) }
  else if (ACCT_TIMER) { clearInterval(ACCT_TIMER); ACCT_TIMER = null }
}
async function pollAccts() {
  try {
    const r = await (await fetch('/api/accounts')).json();
    const rows = (r.accounts || []).map(a => {
      const dot = a.chrome ? '🟢' : '🔴';
      const kind = a.kind === 'img' ? 'ChatGPT · ảnh' : 'Grok · video';
      const st = !a.enabled ? '<span style="color:var(--tx2)">đang tắt</span>'
        : a.dead ? `<span style="color:var(--bad)">${esc(a.dead)}</span>`
          : a.worker ? '<span style="color:var(--acc)">sẵn sàng</span>'
            : '<span style="color:var(--tx2)">chờ thợ…</span>';
      return `<div style="display:flex;align-items:center;gap:8px;font-size:13px">
    <span>${dot}</span><b style="width:64px">${esc(a.id)}</b>
    <span style="width:96px">${kind}</span>
    <span style="width:76px">:${a.port}</span>
    <span style="flex:1">${st}</span>
    <span title="Số bản tài khoản này làm XONG hôm nay, và ngày cao nhất từng đạt.&#10;ChatGPT/Grok không công bố trần mỗi ngày — cứ chạy tới lúc bị chặn thì con số 'cao nhất' chính là trần thật."
          style="color:var(--tx2);font-variant-numeric:tabular-nums">hôm nay <b style="color:var(--acc)">${a.hom_nay || 0}</b>${a.ky_luc ? ` · cao nhất <b style="color:var(--tx)">${a.ky_luc}</b> <span style="opacity:.7">(${esc(a.ky_luc_ngay || '')})</span>` : ''}</span>
    <label title="Số tab chạy ĐỒNG THỜI trên cùng cửa sổ Chrome này.&#10;1 = chạy tuần tự từng việc (mặc định).&#10;Tăng lên để tạo nhiều video/ảnh song song trên CÙNG một tài khoản.&#10;Càng nhiều tab càng tốn RAM — tăng dần và xem máy có chịu nổi không."
           style="display:flex;align-items:center;gap:4px;color:var(--tx2)">tab
      <input type="number" min="1" max="6" value="${a.tabs || 1}" style="width:44px"
             onchange="acctTabs(${a.port},this.value)">
      ${a.tho_song > 1 ? `<span style="color:var(--acc)">×${a.tho_song}</span>` : ''}
    </label>
    ${a.chrome ? '' : `<button onclick="acctOp('launch',${a.port})">Mở Chrome</button>`}
    ${a.dead ? `<button onclick="acctOp('revive',${a.port})">Thử lại</button>` : ''}
    <button onclick="acctOp('toggle',${a.port})">${a.enabled ? 'Tắt' : 'Bật'}</button>
    <button class="bad-b" title="Xóa hẳn tài khoản này khỏi danh sách (dữ liệu đăng nhập trong profile Chrome vẫn giữ)" onclick="acctDel('${esc(a.id)}',${a.port},${a.enabled})">🗑</button>
  </div>`});
    $('#acctrows').innerHTML = rows.join('') || '<span class="hint">chưa có tài khoản nào</span>';
  } catch (e) { }
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

let RUNALL = { active: false, stop: false };

function allShotsOrdered() {
  return DATA.scenes.flatMap(sc => (sc.shots || []).map(sh => ({ sc, sh })));
}

async function waitJob(id) {
  while (true) {
    const r = await (await fetch('/api/jobs')).json();
    const j = (r.jobs || r)[id];   // tương thích cả 2 dạng response cũ/mới
    if (!j || j.state !== 'running') return j;
    await new Promise(res => setTimeout(res, 4000));
    if (RUNALL.stop) return j;
  }
}

async function toggleRunAll() {
  if (RUNALL.active) { RUNALL.stop = true; $('#runstatus').textContent = 'đang dừng…'; return }

  if (VIEW === 'sf') {
    const all = allSF().filter(x => x.f.prompt && !x.f.image);
    if (!all.length) { bao('Không có ảnh SF/Ref nào cần chạy (tất cả đã có ảnh hoặc thiếu prompt).'); return }
    if (!await hoi(`Sẽ chạy tuần tự ${all.length} ảnh CHƯA có sẵn.\nCó thể bấm lại nút để DỪNG giữa chừng.\n\nBắt đầu?`)) return;

    RUNALL = { active: true, stop: false };
    $('#runall').textContent = '■ Dừng'; $('#runall').classList.add('on');

    let done = 0, failed = [];
    for (const { f } of all) {
      if (RUNALL.stop) break;
      $('#runstatus').textContent = `Đang tạo ảnh ${done + 1}/${all.length}: ${f.id}…`;
      JOBS[f.id] = { state: 'running', msg: 'khởi động…' }; render();
      await fetch('/api/generate?sf=' + encodeURIComponent(f.id), { method: 'POST' });
      const j = await waitJob(f.id);
      if (RUNALL.stop) break;
      done++;
      if (j && j.state === 'error') failed.push(f.id + ': ' + j.msg);
      await load();
    }
    RUNALL.active = false;
    $('#runall').textContent = '▶ Chạy tuần tự'; $('#runall').classList.remove('on');
    $('#runstatus').textContent = '';
    bao(`Xong. Đã tạo ${done}/${all.length} ảnh.` + (failed.length ? `\n\nLỗi (${failed.length}):\n` + failed.join('\n') : ''));
    return;
  }

  const all = allShotsOrdered().filter(x => {
    const f = sfById(x.sh.sf);
    return f && f.image && (x.sh.prompt || '').trim() && !x.sh.video;
  });
  if (!all.length) { bao('Không có video nào cần chạy (mọi dòng đã có video, hoặc thiếu SF/prompt).'); return }
  if (!await hoi(`Sẽ chạy tuần tự ${all.length} video CHƯA có sẵn (bỏ qua dòng đã có video).\nCó thể bấm lại nút để DỪNG giữa chừng.\n\nBắt đầu?`)) return;

  RUNALL = { active: true, stop: false };
  $('#runall').textContent = '■ Dừng'; $('#runall').classList.add('on');

  let done = 0, failed = [];
  for (const { sh } of all) {
    if (RUNALL.stop) break;
    $('#runstatus').textContent = `Đang chạy ${done + 1}/${all.length}: ${sh.id}…`;
    JOBS[sh.id] = { state: 'running', msg: 'khởi động…' }; render();
    await fetch('/api/genvideo?sf=' + encodeURIComponent(sh.id), { method: 'POST' });
    const j = await waitJob(sh.id);
    if (RUNALL.stop) break;
    done++;
    if (j && j.state === 'error') failed.push(sh.id + ': ' + j.msg);
    await load();
  }

  RUNALL.active = false;
  $('#runall').textContent = '▶ Chạy tuần tự'; $('#runall').classList.remove('on');
  $('#runstatus').textContent = '';
  bao(`Xong. Đã chạy ${done}/${all.length} video.` + (failed.length ? `\n\nLỗi (${failed.length}):\n` + failed.join('\n') : ''));
}

// Nút "🎬 Xuất CapCut" và "+ Thêm scene" đã BỎ 2026-08-09 theo yêu cầu user.
// API /api/export-capcut phía server vẫn còn, gọi tay được nếu cần.

// ══ THANH NHẢY SCENE (trái) ══ mỗi scene một dòng + % ĐÃ DUYỆT của chế độ đang xem.
// Chế độ Kịch bản đếm video đã duyệt (vstatus), chế độ Start frames đếm SF đã duyệt.
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
    const pct = n ? Math.round(d * 100 / n) : 0;
    return `<a onclick="jumpScene('${sc.id}')" id="nv-${sc.id}" class="${n && d === n ? 'full' : ''}">
  <span class="r1"><span class="sv">${esc(sc.id)}</span><span class="sp">${n ? pct + '%' : '—'}</span></span>
  <span class="bar"><i style="width:${pct}%"></i></span></a>`;
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
  $('#runall').style.display = '';
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
  ${sc.id !== 'REF' ? autoBtn(sc) : ''}
  <button class="sm" onclick="tickScene('${sc.id}')"
    title="Tích mọi thẻ đang hiện của scene này để 'Tạo lại theo lô'">☑ Chọn hết</button>
  <button class="sm" onclick="addSF('${sc.id}')">+ SF</button>
  <button class="sm bad-b" onclick="delScene('${sc.id}')">Xóa scene</button></div>
  <div class="grid"></div>`;
    const g = el.querySelector('.grid');
    // Nút "SF từ ảnh" nằm ở HEADER, không phải trong lưới: đặt trong lưới thì grid
    // kéo nó cao bằng cả hàng thẻ SF, chiếm nguyên một ô cho một cái nút.
    el.querySelector('.scene-h').insertBefore(
      pasteBox(sc), el.querySelector('.scene-h .bad-b'));
    if (sc.id === 'REF') {
      // NHÓM THEO NHÂN VẬT: portrait là thẻ chính, các bản trang phục (_FULL)
      // thành dải ảnh nhỏ bên trong thẻ đó — bấm ảnh nhỏ để phóng to,
      // bấm ✎ để mở/đóng các thẻ trang phục đầy đủ (sửa prompt, tạo lại).
      const who = id => id.split('_')[1] || id;
      const ports = list.filter(f => f.id.endsWith('_PORTRAIT'));
      const fulls = list.filter(f => f.id.endsWith('_FULL'));
      const rest = list.filter(f => !f.id.endsWith('_PORTRAIT') && !f.id.endsWith('_FULL'));
      const byChar = {};
      fulls.forEach(f => (byChar[who(f.id)] = byChar[who(f.id)] || []).push(f));
      ports.forEach(pf => {
        const ch = who(pf.id), kids = byChar[ch] || [];
        delete byChar[ch];
        const d = card(sc, pf);
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
          strip.querySelector('[data-wtog]').onclick = e => {
            WROPEN[ch] = !WROPEN[ch]; render();
          };
          d.querySelector('.body').insertBefore(strip, d.querySelector('.body').children[1]);
        }
        g.appendChild(d);
        kids.forEach(k => { const kd = card(sc, k); if (!WROPEN[ch]) kd.style.display = 'none'; g.appendChild(kd); });
      });
      Object.values(byChar).flat().forEach(f => g.appendChild(card(sc, f)));   // full mồ côi
      rest.forEach(f => g.appendChild(card(sc, f)));
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
function autoBtn(sc) {
  const on = AUTO.hasOwnProperty(sc.id);
  const st = AUTO[sc.id] || {};
  const lab = on ? (st.img && st.vid ? `⏳ ${st.img[0]}/${st.img[1]} ảnh · ${st.vid[0]}/${st.vid[1]} video`
    : '⏳ đang quét…') : '▶ Chạy hết';
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
    for (const sh of list) await fetch('/api/genvideo?sf=' + encodeURIComponent(sh.id), { method: 'POST' });
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
  const vjob = JOBS[sh.id] || {}; const vrun = vjob.state === 'running';
  const d = document.createElement('div');
  d.className = 'shot' + (!f || !f.image ? ' warn-sf' : '')
    + (sh.vstatus === 'approved' ? ' vok' : sh.vstatus === 'rejected' ? ' vbad' : sh.video ? ' vnew' : '');
  // Badge trạng thái đè lên ảnh đã bỏ 2026-08-09 — viền thẻ và nút ✓/✎/✕ đã nói đủ.
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
    <span class="vid">${esc(sh.id)}</span>
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
      JOBS[sh.id] = { state: 'running', msg: 'khởi động…' }; render();
      await fetch('/api/genvideo?sf=' + encodeURIComponent(sh.id), { method: 'POST' }); return
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
    const r = await (await fetch('/api/tao-lo?sf=' + encodeURIComponent(ids.join(',')),
      { method: 'POST' })).json();
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

function card(sc, f) {
  const _bu = bgUsers(sc), _rank = sfRank(f, _bu), _otag = sfOrderTag(f, _bu);
  const _bg = (f.refs || {}).bg;
  const job = JOBS[f.id] || {}; const running = job.state === 'running';
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
 <div class="sfid">${isM ? '<span class="kindtag m">MASTER</span>' : ''}${esc(f.id)}</div>
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
   ${job.state === 'error' ? `<div class="err">⚠ ${esc(job.msg)}</div>` : ''}
   <div class="acts">
 <button class="sm pri" data-a="gen" ${running ? 'disabled' : ''}>${f.image ? 'Tạo lại' : 'Tạo ảnh'}</button>
 <button class="sm ok-b" data-a="approved">✓</button>
 <button class="sm warn-b" data-a="revise">✎</button>
 <button class="sm bad-b" data-a="rejected">✕</button>
 <span style="flex:1"></span>
 ${f.image ? `<a class="sm dl" href="${f.image}?dl=1&name=${encodeURIComponent(f.id)}" download="${f.id}.png" title="Tải ảnh về máy">⬇</a>` : ''}
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
    JOBS[f.id] = { state: 'running', msg: n > 1 ? `đang tạo 0/${n} bản…` : 'khởi động…' }; render();
    await fetch(`/api/generate?sf=${encodeURIComponent(f.id)}&n=${n}`, { method: 'POST' }); return
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
