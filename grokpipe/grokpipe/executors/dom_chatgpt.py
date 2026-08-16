"""DOM của ChatGPT — selector và mọi đoạn JS chạy trong trang.

TÁCH KHỎI image_chatgpt.py 2026-08-12. Lý do: ChatGPT đổi giao diện liên tục, và
mỗi lần đổi là phải lần trong hơn 1.600 dòng điều phối để tìm chỗ sửa. Gom vào
đây thì lần sau chỉ mở một file — `image_chatgpt.py` còn lại thuần phần điều
phối lô, không dính DOM.

Ba luật khi sửa (rút từ những lần hỏng thật):
  1. BÁM THUỘC TÍNH, ĐỪNG BÁM CHỮ. Giao diện có thể sang tiếng Việt bất cứ lúc
     nào; `data-testid` thì không đổi theo ngôn ngữ. Chữ chỉ để dự phòng.
  2. COI CHỪNG PHẦN TỬ ẨN ĐỨNG TRƯỚC PHẦN TỬ THẬT. `querySelector` lấy cái đầu
     tiên trong DOM, mà cái đầu tiên có lúc là ô ẩn — xem `JS_O_SOAN`.
  3. FAIL-CLOSED. Phân biệt cho được "không thấy gì" với "thấy nhưng rỗng";
     nhập nhèm hai cái đó thì lô chết mà log vẫn sạch.
"""

# --------------------------------------------------------------------------
# Selector — chỉnh ở đây khi ChatGPT đổi giao diện.
# --------------------------------------------------------------------------
SELECTORS = {
    "composer": "#prompt-textarea",
    "file_input": "input[type=file]",
    "send_button": "button[data-testid='send-button']",
    "stop_button": "button[data-testid='stop-button']",
    # UI mới dùng data-turn=assistant trên <section>; giữ selector cũ để tương
    # thích. generate() sẽ loại toàn bộ URL đã có trước khi gửi prompt.
    "assistant_turn": "[data-turn='assistant'], [data-message-author-role='assistant']",
    "assistant_image": "[data-turn='assistant'] img, [data-message-author-role='assistant'] img",
    # khối overlay Edit/tải xuất hiện khi ảnh đã sinh xong
    "image_done": "[data-testid='image-gen-overlay-actions']",
    # thumbnail ảnh đính kèm hiện trong ô soạn (đếm để XÁC MINH upload đủ)
    # Thumbnail ảnh đính kèm nằm trong <form> của ô soạn. Đã đo trên UI thật:
    # "form img" = đúng số ảnh đang đính, và = 0 khi chưa đính gì.
    "composer_attachment": "form img",
    # NÚT CHỌN SỨC MẠNH (Instant · Medium · High) trong ô soạn — cái "pill" nhỏ
    # cạnh nút +. BÁM THUỘC TÍNH, vì CHỮ trên nút dịch theo ngôn ngữ tài khoản:
    # giao diện tiếng Việt ghi "Tức thì · Vừa · Cao", và bản cũ dò bằng regex
    # tiếng Anh nên đọc ra chuỗi rỗng rồi bỏ luôn việc đổi chế độ — cả buổi
    # render chạy ở Instant mà log chỉ có một dòng cảnh báo (2026-08-15).
    "mode_pill": "form button[aria-haspopup='menu']:has([data-animated-slider-trigger])",
    # đường lui khi ChatGPT đổi tên thuộc tính trên: trong <form> của ô soạn chỉ
    # nút này mang aria-haspopup=menu (nút + không có) — đã đo trên UI thật.
    "mode_pill_alt": "form button[aria-haspopup='menu']",
}


# Ô soạn ĐANG HIỆN, đọc từ TRONG TRANG. Mọi khối `evaluate` chạm ô soạn phải đi
# qua đây thay cho `querySelector('#prompt-textarea')`.
#
# `querySelector` lấy cái ĐẦU TIÊN trong DOM, mà cái đầu tiên có lúc là ô ẩn
# (`aria-hidden="true"`) — đúng thứ đã giết lô SF-S7-02..07 ngày 2026-08-07.
# Vá `_o_soan()` phía Python là chưa đủ: phía JS vẫn đọc/ghi vào ô ẩn, và hậu
# quả nặng hơn cú timeout ban đầu vì nó IM LẶNG —
#   · đọc ngược ra chuỗi rỗng  → báo "ô prompt không khớp" rồi bỏ cả lô
#   · `_da_roi_o_soan()` thấy trống → báo GỬI THÀNH CÔNG dù click bị nuốt,
#     board ngồi chờ ảnh không bao giờ về.
# Là BIỂU THỨC (IIFE) chứ không phải câu lệnh, để nối được vào giữa arrow
# function mà `page.evaluate` nhận.
_JS_O_SOAN = """(() => {
    const ds = [...document.querySelectorAll('#prompt-textarea')];
    return ds.find(e => {
        const r = e.getBoundingClientRect();
        return e.getAttribute('aria-hidden') !== 'true' && r.width > 0 && r.height > 0;
    }) || null;
})()"""


# Nhận ra ảnh REF (ảnh mình đính lên) bằng DẤU HIỆU KHÔNG THEO NGÔN NGỮ.
#
# Bản cũ lọc bằng `alt === 'Generated image'` và `aria-label^="Open image "`.
# Trên Chrome để giao diện tiếng Việt, ChatGPT dịch cả hai chuỗi đó, nên phép
# lọc quét sạch MỌI ảnh output: quét ra 0 ảnh, job chờ tới hết giờ rồi trả 0/N
# trong khi ảnh hiện đủ trên màn hình. Cùng lúc `JS_DANH_SACH_REF_ID` (logic
# ngược) lại xếp chính ảnh vừa vẽ vào diện REF.
# Thứ không dịch được là TÊN FILE: ref luôn mang tên file ở `alt` hoặc ở
# `aria-label` của nút mở ảnh; output thì không bao giờ.
_JS_LA_REF = r"""
    const laRef = i => {
        const alt = (i.alt || '').trim();
        if (/\.(png|jpe?g|webp)$/i.test(alt)) return true;
        const n = i.closest('button[aria-label]');
        return !!(n && /\.(png|jpe?g|webp)/i.test(n.getAttribute('aria-label') || ''));
    };
"""


# NHÃN đang hiện trên nút sức mạnh — CHỈ để ghi log và cho giao diện kiểu cũ.
# Đừng dùng nó làm căn cứ đổi chế độ: nhãn dịch theo ngôn ngữ tài khoản.
# Tìm form bằng ô soạn ĐANG HIỆN chứ không `querySelector('form')`: thanh bên
# cũng có form tìm kiếm, và ô ẩn vẫn nằm trong DOM (xem `_JS_O_SOAN`).
JS_NHAN_CHE_DO = """() => {
                    const vis = e => { const r = e.getBoundingClientRect();
                                       return r.width > 0 && r.height > 0; };
                    const o = """ + _JS_O_SOAN + """;
                    const f = o ? o.closest('form') : document.querySelector('form');
                    if (!f) return '';
                    const bs = [...f.querySelectorAll("button[aria-haspopup='menu']")].filter(vis);
                    const b = bs.find(e => e.querySelector('[data-animated-slider-trigger]')) || bs[0];
                    return b ? (b.textContent || '').trim() : ''; }"""

# NẤC sức mạnh đọc bằng SỐ — thứ duy nhất không dịch được.
# Giao diện 2026-08 là MỘT THANH TRƯỢT ba nấc, chỉ hiện khi menu đang mở:
# aria-valuenow 0/1/2 = Instant/Medium/High, aria-valuemax cho biết nấc cao nhất
# tài khoản này với tới. Trả null khi menu chưa mở hoặc giao diện là kiểu cũ
# (menu ba mục radio) — hai ca đó phải phân biệt được, không được nhập nhèm.
JS_DOC_NAC = """() => {
                    const vis = e => { const r = e.getBoundingClientRect();
                                       return r.width > 0 && r.height > 0; };
                    const s = [...document.querySelectorAll('[role=slider]')].filter(vis)[0];
                    if (!s) return null;
                    const n = parseInt(s.getAttribute('aria-valuenow'), 10);
                    const m = parseInt(s.getAttribute('aria-valuemax'), 10);
                    return {nac: Number.isNaN(n) ? null : n,
                            toida: Number.isNaN(m) ? null : m}; }"""

JS_DOWNLOAD = """(u) => {
                    const imgs = Array.from(document.querySelectorAll(
                        "[data-turn='assistant'] img, [data-message-author-role='assistant'] img"
                    ));
                    const img = imgs.find(i => (i.currentSrc || i.src || '') === u);
                    if (!img || !img.complete || !img.naturalWidth) return null;
                    const canvas = document.createElement('canvas');
                    canvas.width = img.naturalWidth;
                    canvas.height = img.naturalHeight;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0);
                    return canvas.toDataURL('image/png').split(',')[1];
                }"""

JS_DOWNLOAD_2 = """async (u) => {
                    const r = await fetch(u, {credentials: 'include'});
                    const b = await r.blob();
                    return await new Promise(res => {
                        const fr = new FileReader();
                        fr.onloadend = () => res(fr.result.split(',')[1]);
                        fr.readAsDataURL(b);
                    });
                }"""

JS_ANH_DANG_CO = """() => { const out = [], seen = new Set();
                    document.querySelectorAll("[data-turn='assistant'] img,"
                        + "[data-message-author-role='assistant'] img").forEach(i => {
                        const s = i.currentSrc || i.src || '';
                        if (s && !s.startsWith('blob:') && !seen.has(s)) { seen.add(s); out.push(s); }
                    });
                    return out; }"""

JS_DANH_SACH_ID = """() => { const out = [], seen = new Set();""" + _JS_LA_REF + """
                    const uSel = "[data-turn='user'],[data-message-author-role='user']";
                    document.querySelectorAll('img').forEach(i => {
                        const s = i.currentSrc || i.src || '';
                        if (!s.includes('/backend-api/estuary/content')) return;
                        if (i.closest(uSel)) return;
                        if (laRef(i)) return;
                        let k = s;
                        try { k = new URL(s).searchParams.get('id') || s; } catch (e) {}
                        if (!seen.has(k)) { seen.add(k); out.push([k, s]); } });
                    return out; }"""

JS_DANH_SACH_REF_ID = """() => { const out = [], seen = new Set();""" + _JS_LA_REF + """
                    document.querySelectorAll('img').forEach(i => {
                        const s = i.currentSrc || i.src || '';
                        if (!s.includes('/backend-api/estuary/content')) return;
                        if (!laRef(i)) return;
                        let k = s;
                        try { k = new URL(s).searchParams.get('id') || s; } catch (e) {}
                        if (!seen.has(k)) { seen.add(k); out.push(k); } });
                    return out; }"""

JS_ANH_SAU_MOC_TURN = r"""async ({moc, quet}) => {""" + _JS_LA_REF + r"""
                    const nghi = ms => new Promise(r => setTimeout(r, ms));
                    const out = [];
                    const turns = [...document.querySelectorAll(
                        '[data-turn="assistant"][data-testid^="conversation-turn-"]'
                    )].map(t => {
                        const m = (t.getAttribute('data-testid') || '')
                            .match(/conversation-turn-(\d+)/);
                        return [m ? Number(m[1]) : -1, t];
                    }).filter(([n]) => n > moc).sort((a, b) => a[0] - b[0]);
                    const gom = (n, t, seen) => t.querySelectorAll('img').forEach(i => {
                        const s = i.currentSrc || i.src || '';
                        if (!s.includes('/backend-api/estuary/content')) return;
                        if (laRef(i)) return;
                        let k = s;
                        try { k = new URL(s).searchParams.get('id') || s; } catch (e) {}
                        if (!seen.has(k)) { seen.add(k); out.push([n, k, s]); }
                    });
                    for (const [n, t] of turns) {
                        const seen = new Set();
                        const cs = [...t.querySelectorAll('div')].filter(c => {
                            const st = getComputedStyle(c);
                            return /auto|scroll/.test(st.overflowY || '')
                                && c.querySelector('[class*="group/imagegen-image"]');
                        });
                        if (!quet || !cs.length) {
                            // Trong lúc poll chỉ cần đếm. Ảnh preview lớn và
                            // thumbnail trùng ID nên Set sẽ khử trùng.
                            gom(n, t, seen);
                            continue;
                        }
                        for (const c of cs) {
                            const cu = c.scrollTop;
                            const buoc = Math.max(48, (c.clientHeight || 120) - 8);
                            for (let y = 0; y <= c.scrollHeight; y += buoc) {
                                c.scrollTop = y; await nghi(100);
                            }
                            c.scrollTop = cu;
                            // THỨ TỰ CHỈ lấy từ dãy button thumbnail. Ảnh lớn
                            // là thumbnail ĐANG CHỌN, không phải output số 1;
                            // đặt nó lên đầu từng làm 01↔02 và 07↔08.
                            c.querySelectorAll('button').forEach(b => {
                                const i = b.querySelector('img');
                                const s = i ? (i.currentSrc || i.src || '') : '';
                                if (!s.includes('/backend-api/estuary/content')) return;
                                let k = s;
                                try { k = new URL(s).searchParams.get('id') || s; } catch (e) {}
                                if (!seen.has(k)) { seen.add(k); out.push([n, k, s]); }
                            });
                        }
                    }
                    return out;
                }"""

JS_QUET_CUON = """async () => {""" + _JS_LA_REF + """
                    const nghi = ms => new Promise(r => setTimeout(r, ms));
                    const out = [], seen = new Set();
                    const uSel = "[data-turn='user'],[data-message-author-role='user']";
                    const gom = () => document.querySelectorAll('img').forEach(i => {
                        const s = i.currentSrc || i.src || '';
                        if (!s.includes('/backend-api/estuary/content')) return;
                        if (i.closest(uSel)) return;
                        if (laRef(i)) return;
                        let k = s;
                        try { k = new URL(s).searchParams.get('id') || s; } catch (e) {}
                        if (!seen.has(k)) { seen.add(k); out.push([k, s]); }
                    });
                    // Carousel ảnh chỉ mount khoảng 2 thumbnail một lúc. Cuộn
                    // riêng từng cột thumbnail; nếu không một lượt đủ 6 trên UI
                    // có thể chỉ còn 2 ID trong DOM và board báo sai 2/6.
                    const quetCarousel = async () => {
                        const cs = [...document.querySelectorAll('div')].filter(c => {
                            const st = getComputedStyle(c);
                            return /auto|scroll/.test(st.overflowY || '')
                                && c.querySelector('[class*="group/imagegen-image"]');
                        });
                        for (const c of cs) {
                            const cu = c.scrollTop;
                            const buoc = Math.max(48, (c.clientHeight || 120) - 8);
                            for (let y = 0; y <= c.scrollHeight; y += buoc) {
                                c.scrollTop = y; await nghi(140); gom();
                            }
                            c.scrollTop = cu;
                        }
                    };
                    // tìm khung cuộn thật của thread, không phải window
                    let el = document.scrollingElement || document.documentElement;
                    for (const c of document.querySelectorAll('main div')) {
                        if (c.scrollHeight > c.clientHeight + 200) { el = c; break; }
                    }
                    const h = el.scrollHeight, buoc = Math.max(400, el.clientHeight - 100);
                    for (let y = 0; y < h; y += buoc) {
                        el.scrollTop = y; await nghi(160); gom(); await quetCarousel();
                    }
                    el.scrollTop = el.scrollHeight;   // trả về đáy như cũ
                    await nghi(180); gom(); await quetCarousel();
                    return out;
                }"""

JS_DEM_TU_CHOI = """() => ((document.body.innerText || '')
                    .match(/guardrail|violate our|something went wrong/gi) || []).length"""

JS_TIN_NHAN_TEXT_TRO_LY = """() => { const out = {};
                    document.querySelectorAll(
                        '[data-message-author-role="assistant"][data-message-id]'
                    ).forEach(e => {
                        const id = e.getAttribute('data-message-id') || '';
                        const text = (e.innerText || e.textContent || '').trim();
                        if (id) out[id] = text;
                    });
                    return out; }"""

JS_TRANG_THAI_O_SOAN = """() => [...document.querySelectorAll('#prompt-textarea')].map(e => {
                    const r = e.getBoundingClientRect();
                    return {hidden: e.getAttribute('aria-hidden'),
                            w: Math.round(r.width), h: Math.round(r.height),
                            disabled: e.getAttribute('contenteditable') === 'false'};
                })"""

JS_TAI_VE = """async u => { const r = await fetch(u); if (!r.ok) return null;
                        const b = await r.blob();
                        return await new Promise(res => { const f = new FileReader();
                            f.onload = () => res(String(f.result).split(',')[1]);
                            f.readAsDataURL(b); }); }"""

JS_MOC_TURN_TRO_LY = r"""() => Math.max(-1, ...[...document.querySelectorAll(
                    '[data-turn="assistant"][data-testid^="conversation-turn-"]'
                )].map(e => Number((e.getAttribute('data-testid') || '')
                    .match(/conversation-turn-(\d+)/)?.[1] || -1)))"""

# Tên các file ĐANG ĐÍNH trong ô soạn.
#
# ƯU TIÊN NÚT NẰM TRONG <form> — đó là thẻ đính kèm của tin SẮP gửi. Nút ngoài
# form (`Open image 3 of 9: …`) là ảnh của tin ĐÃ GỬI: đếm cả chúng thì tab dùng
# lại một chat cũ sẽ báo "đã đính đủ" trong khi ô soạn trống trơn.
# Lọc theo vị trí trong DOM chứ không theo chữ "Remove file": chữ đó dịch theo
# ngôn ngữ giao diện, vị trí thì không.
# Tên trả về CÒN NGUYÊN hậu tố ChatGPT tự thêm — `REF_X(5).jpg`; bên gọi phải
# chuẩn hoá trước khi so (xem `_thieu_theo_ten`).
JS_TEN_DA_LEN = r"""() => {
    const lay = els => els
        .map(e => ((e.getAttribute('aria-label') || '')
             .match(/([^\s:\\/]+\.(?:png|jpe?g|webp))\s*$/i) || [])[1])
        .filter(Boolean);
    const trongForm = lay([...document.querySelectorAll('form button[aria-label]')]);
    if (trongForm.length) return trongForm;
    return lay([...document.querySelectorAll('button[aria-label]')]);
}"""
