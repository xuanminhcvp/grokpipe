"""DOM của Grok Imagine — selector và mọi đoạn JS chạy trong trang.

TÁCH KHỎI video_grok.py 2026-08-12, đúng khuôn `dom_chatgpt.py`. Lý do y hệt:
Grok đổi giao diện liên tục, và mỗi lần đổi là phải lần trong hơn 600 dòng điều
phối để tìm chỗ sửa. Gom vào đây thì lần sau chỉ mở một file.

Ba luật khi sửa (rút từ những lần hỏng thật, xem thêm skill `grokpipe-ops`):
  1. BÁM THUỘC TÍNH, ĐỪNG BÁM CHỮ. Giao diện có thể sang tiếng Việt bất cứ lúc
     nào; `button[type=submit]` thì không đổi theo ngôn ngữ. Chữ chỉ để dự phòng.
  2. DOM GROK KHÔNG NHẤT QUÁN. Cùng một nút lúc là `role=radio`, lúc là
     `button` — luôn quét CẢ HAI và khớp `aria-label` HOẶC `textContent`.
  3. FAIL-CLOSED. Phân biệt cho được "không thấy nút" với "thấy nhưng bấm trượt";
     nhập nhèm hai cái đó thì job chết mà log vẫn sạch.
"""

# --------------------------------------------------------------------------
# Selector — chỉnh ở đây khi Grok đổi giao diện.
# --------------------------------------------------------------------------
SELECTORS = {
    "composer": "[contenteditable='true']",
    "file_input": "input[type=file]",
    "submit": "button[type=submit]",
}

URL_IMAGINE = "https://grok.com/imagine"

# Trang kết quả. Đứng ở đây thì KHÔNG có nút mode 'Video' (chỉ có 'Make video'),
# nên mọi bước chọn chế độ đều trượt — phải về /imagine trước.
DAU_TRANG_POST = "/imagine/post/"

# Tên nút "mở lượt mới" theo thứ tự ưu tiên. Đây là ĐƯỜNG VỀ trang soạn khi SPA
# cứ kéo tab lại trang post: `goto` bị Grok khôi phục phiên cũ đè lên, còn bấm
# nút thì đi đúng luồng của chính nó. Ba tên vì Grok đổi chữ theo phiên bản.
TEN_LUOT_MOI = ("New Generation", "New generation", "Imagine", "New Project")


# ---- ĐỌC HIỆN TRẠNG ------------------------------------------------------
# Mọi thông báo lỗi selector phải đính hiện trạng kèm theo, nếu không người sau
# chỉ có mỗi câu "không thấy nút" và phải dựng lại cả phiên để đoán.
JS_NUT_DANG_CO = """() => [...document.querySelectorAll('[role=radio],button')]
     .filter(e => e.getBoundingClientRect().width > 0)
     .map(e => (e.getAttribute('aria-label')||'').trim()
               || (e.textContent||'').trim())
     .filter(t => t && t.length < 24).slice(0, 18)"""

# Ảnh chụp toàn cảnh cho log lỗi. Gộp vào MỘT lần evaluate, không phải năm lần:
# trang đang hỏng thì mỗi lần gọi thêm là một cơ hội ném exception khác, và ảnh
# chụp sẽ mô tả năm thời điểm khác nhau thay vì một.
JS_CHAN_DOAN = """() => {
    const hien = e => e.getBoundingClientRect().width > 0;
    const nut = [...document.querySelectorAll('[role=radio],button')].filter(hien);
    const ten = e => (e.getAttribute('aria-label')||'').trim() || (e.textContent||'').trim();
    return {
        url: location.href,
        lang: document.documentElement.lang || '',
        tieu_de: (document.title || '').slice(0, 60),
        o_soan: [...document.querySelectorAll("[contenteditable='true']")].filter(hien).length,
        nut_gui: [...document.querySelectorAll('button[type=submit]')].filter(hien).length,
        co_mode_video: nut.some(e => ten(e) === 'Video'),
        co_luot_moi: nut.filter(e => /new generation|new project|^imagine$/i.test(ten(e)))
                        .map(ten),
        so_video: document.querySelectorAll('video').length,
        nut: nut.map(ten).filter(t => t && t.length < 24).slice(0, 18),
    };
}"""

JS_CO_MODE_VIDEO = """() => [...document.querySelectorAll('[role=radio]')]
     .some(e => (e.getAttribute('aria-label')||'') === 'Video'
                && e.getBoundingClientRect().width > 0)"""

JS_CO_NUT_GUI = """() => !![...document.querySelectorAll('button[type=submit]')]
     .find(e => e.getBoundingClientRect().width > 0)"""

JS_HET_CREDIT = """() => [...document.querySelectorAll('[aria-label]')]
     .some(e => /100% credits used/i.test(e.getAttribute('aria-label')||''))"""

JS_CHU_TRONG_O_SOAN = """() => {const b=document.querySelector("[contenteditable='true']");
                          return b ? (b.innerText||'').trim().length : -1}"""


# ---- BẤM -----------------------------------------------------------------
JS_CLICK_TEXT = """(lab) => {
      const cands=[...document.querySelectorAll('button')].filter(b=>{
        const t=(b.textContent||'').trim();
        return b.getBoundingClientRect().width>0 && t===lab;});
      if(!cands.length) return false;
      cands[0].click(); return true;
    }"""

# Quét CẢ `role=radio` LẪN `button`, khớp aria-label HOẶC text: mode Video/Image
# là icon chỉ có aria-label, còn 480p/720p/6s/10s có text.
JS_CLICK_RADIO = """(name) => {
      const els=[...document.querySelectorAll('[role=radio],button')].filter(e=>{
        if (e.getBoundingClientRect().width===0) return false;
        const a=(e.getAttribute('aria-label')||'').trim();
        const t=(e.textContent||'').trim();
        return a===name || t===name;});
      if(!els.length) return false;
      els[0].click(); return true;
    }"""

# Bấm nút mở lượt mới. Khớp LỎNG (regex, không phân biệt hoa thường) vì đây là
# đường thoát cuối khi tab kẹt ở trang post — thà bấm trúng một nút gần đúng còn
# hơn chết cả job. Trả về tên nút đã bấm để log nói được nó đi lối nào.
JS_CLICK_LUOT_MOI = """() => {
      const hien = e => e.getBoundingClientRect().width > 0;
      const ten = e => (e.getAttribute('aria-label')||'').trim()
                       || (e.textContent||'').trim();
      const els = [...document.querySelectorAll('button,[role=radio],a')].filter(hien);
      for (const re of [/^new generation$/i, /^new project$/i, /^imagine$/i]) {
        const e = els.find(x => re.test(ten(x)));
        if (e) { e.click(); return ten(e); }
      }
      return '';
    }"""


# ---- VIDEO ---------------------------------------------------------------
# Chỉ tính KHUNG PHÁT THẬT, bỏ thumbnail thanh bên. Đo 2026-08-09: trang
# /imagine/post/ kèm một dãy video cũ 50×50 ở thanh bên, bản thật ~1131×644.
# Không lọc thì hai chuyện xảy ra cùng lúc: (1) log báo "Grok trả về 2-3 clip"
# trong khi thật ra chỉ có một, (2) `new[-1]` bốc trúng thumbnail của video CŨ
# và board tải nhầm bản — sai kiểu đó hoàn toàn im lặng.
JS_VIDEO_THAT = """() => [...document.querySelectorAll('video')]
     .map(v => ({src: v.currentSrc || v.src || '',
                 dur: v.duration || 0,
                 w: v.getBoundingClientRect().width,
                 cu: v.dataset.gpCu === '1'}))
     .filter(v => v.src.startsWith('http') && v.w >= 200)"""

JS_DONG_DAU_VIDEO_CU = """() => document.querySelectorAll('video')
     .forEach(v => v.dataset.gpCu = '1')"""

JS_DAT_TEN_TAB = """n => { window.name = n }"""


# ---- LỖI MẠNG ------------------------------------------------------------
# Chrome ném các mã này khi tầng vận chuyển hỏng, KHÔNG phải khi selector sai.
# Phân biệt được hai loại thì log mới chỉ đúng chỗ cần chữa: mã dưới đây nghĩa
# là "sửa mạng/Chrome", mọi mã khác mới nghĩa là "Grok đổi giao diện".
MA_LOI_MANG = (
    "ERR_QUIC_PROTOCOL_ERROR",      # HTTP/3 hỏng — hay gặp nhất, xem --disable-quic
    "ERR_CONNECTION_",
    "ERR_NETWORK_CHANGED",
    "ERR_INTERNET_DISCONNECTED",
    "ERR_NAME_NOT_RESOLVED",
    "ERR_TIMED_OUT",
    "ERR_SSL_",
    "ERR_EMPTY_RESPONSE",
    "ERR_HTTP2_",
)


def loi_mang(e) -> str:
    """Mã lỗi mạng trong một exception của Playwright, chuỗi rỗng nếu không phải.

    Dùng để tách "Grok không với tới được" khỏi "Grok đổi giao diện" — hai thứ
    này chữa bằng hai cách hoàn toàn khác nhau, gộp lại là đi sửa nhầm chỗ.
    """
    s = str(e or "")
    for ma in MA_LOI_MANG:
        if ma in s:
            # Cắt đúng mã đầy đủ (ERR_CONNECTION_ là tiền tố của nhiều mã).
            i = s.index(ma)
            j = i
            while j < len(s) and (s[j].isalnum() or s[j] == "_"):
                j += 1
            return s[i:j]
    return ""
