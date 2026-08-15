# REF Batching and Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gộp REF độc lập theo lô an toàn và chia UI/sidebar REF thành Nhân vật, Đạo cụ, Bối cảnh.

**Architecture:** Giữ `_auto_scene()` là production enqueue authority và chỉ thay khóa nhóm dùng khi scene là `REF`. UI dùng các hàm phân loại thuần trong `board.js` để cả nội dung chính và sidebar đọc cùng một quy tắc ID; không thêm schema hoặc endpoint mới.

**Tech Stack:** Python 3.14, pytest, JavaScript thuần, HTML/CSS thuần, `ThreadingHTTPServer` legacy.

## Global Constraints

- Bốn `*_PORTRAIT` đầu trong thứ tự scene REF là nhân vật chính; từ người thứ năm là nhân vật phụ.
- `_FULL` chỉ được enqueue khi mọi ref của chính nó đã có file.
- Portrait độc lập gộp tối đa `TRAN_MAY_TU_GOM`; `_FULL` phụ dùng chung nhóm nhưng vẫn qua `TRAN_REF`.
- Không tạo writer, retry hoặc re-enqueue authority mới; giữ `JOBS`, `IMG_QUEUE`, `_auto_scene()` và stop-generation hiện tại.
- Không gọi Chrome/provider hoặc bấm **Chạy hết REF** trong test/verification.
- Giữ nguyên mọi thay đổi không liên quan trong worktree đang bẩn.
- UI phải dùng text hiển thị và phần trăm, không dùng màu làm tín hiệu duy nhất; keyboard focus phải nhìn thấy.

---

### Task 1: Khóa hành vi gộp REF bằng regression test

**Files:**
- Modify: `tests/job_lifecycle/test_ref_run_all.py:26-105`

**Interfaces:**
- Consumes: `_auto_scene(sc: dict, st: dict, cyc: int)`, `IMG_QUEUE`, `_RefBoard.files`.
- Produces: regression contract cho portrait batch và `_FULL` chính/phụ.

- [ ] **Step 1: Viết test RED cho portrait độc lập**

Thêm test gọi endpoint auto thật, chạy một chu kỳ và yêu cầu hai portrait trong fixture hiện tại nằm trong cùng một queue item, còn đạo cụ là task riêng:

```python
def test_portrait_doc_lap_duoc_gom_chung_mot_lo(self):
    self._post("/api/auto?op=toggle&scene=REF")

    self.m._auto_scene(self.scene, self.m.AUTO["REF"], 1)
    idents = [item[1] for item in self._lay_het_hang_anh()]

    assert "LO:REF_AN_PORTRAIT,REF_BINH_PORTRAIT" in idents
    assert "LO:REF_PROP_PHONE" in idents
    assert all("_FULL" not in ident for ident in idents)
```

- [ ] **Step 2: Chạy test và xác nhận RED đúng nguyên nhân**

Run:

```bash
./.venv/bin/python3 -m pytest -q \
  tests/job_lifecycle/test_ref_run_all.py::TestRefRunAll::test_portrait_doc_lap_duoc_gom_chung_mot_lo
```

Expected: FAIL vì production hiện tạo hai item một ảnh `LO:REF_AN_PORTRAIT` và `LO:REF_BINH_PORTRAIT`.

- [ ] **Step 3: Viết test RED cho bốn nhân vật chính và nhóm phụ**

Thêm helper dựng sáu nhân vật theo đúng thứ tự portrait; đánh dấu toàn bộ portrait đã có file rồi chạy `_auto_scene()`:

```python
def test_full_bon_nhan_vat_chinh_tach_rieng_tu_nguoi_thu_nam_gom_chung(self):
    sfs = []
    for ten in ("A", "B", "C", "D", "E", "F"):
        portrait = f"REF_{ten}_PORTRAIT"
        sfs.extend([
            {"id": portrait, "prompt": f"portrait {ten}", "refs": {}},
            {"id": f"REF_{ten}_FULL", "prompt": f"full {ten}",
             "refs": {"chars": [portrait]}},
        ])
    self.scene["sfs"] = sfs
    self.board.files.update(f"REF_{ten}_PORTRAIT" for ten in "ABCDEF")
    self._post("/api/auto?op=toggle&scene=REF")

    self.m._auto_scene(self.scene, self.m.AUTO["REF"], 1)
    idents = [item[1] for item in self._lay_het_hang_anh()]

    for ten in "ABCD":
        assert f"LO:REF_{ten}_FULL" in idents
    assert "LO:REF_E_FULL,REF_F_FULL" in idents
```

- [ ] **Step 4: Chạy test thứ hai và xác nhận RED**

Run:

```bash
./.venv/bin/python3 -m pytest -q \
  tests/job_lifecycle/test_ref_run_all.py::TestRefRunAll::test_full_bon_nhan_vat_chinh_tach_rieng_tu_nguoi_thu_nam_gom_chung
```

Expected: FAIL vì `_nhom_cua()` hiện trả `NV:E` và `NV:F`, tạo hai lô riêng.

- [ ] **Step 5: Commit riêng regression tests**

```bash
git add tests/job_lifecycle/test_ref_run_all.py
git commit -m "test: require REF batch grouping"
```

---

### Task 2: Thay khóa nhóm auto REF tối thiểu

**Files:**
- Modify: `sfboard/sfboard.py:2348-2416`
- Modify: `sfboard/sfboard.py:3085-3123`

**Interfaces:**
- Consumes: `_nhom_cua(sf_id, data) -> str`, `_chia_lo(...)`, scene order từ `data["scenes"]`.
- Produces: `_nhom_auto_cua(sf_id: str, scene_id: str, data: dict) -> str`.

- [ ] **Step 1: Thêm helper thuần cho khóa nhóm auto**

Đặt helper cạnh `_nhom_cua()`; scene thường giữ nguyên, scene REF áp quy tắc đã duyệt:

```python
def _nhom_auto_cua(sf_id: str, scene_id: str, data: dict) -> str:
    if scene_id != "REF":
        return _nhom_cua(sf_id, data)
    if sf_id.startswith("REF_PROP_"):
        return "PROP"
    if sf_id.endswith("_PORTRAIT"):
        return "REF:PORTRAIT"
    if sf_id.endswith("_FULL"):
        mt = re.match(r"^REF_([A-Z0-9]+)_", sf_id)
        if mt:
            scene = next((s for s in data.get("scenes", []) if s.get("id") == "REF"), {})
            thu_tu = []
            for f in scene.get("sfs", []):
                rid = f.get("id", "")
                m = re.match(r"^REF_([A-Z0-9]+)_PORTRAIT$", rid)
                if m and m.group(1) not in thu_tu:
                    thu_tu.append(m.group(1))
            return "NV:PHU" if mt.group(1) in thu_tu[4:] else "NV:" + mt.group(1)
    return "REF:BOI_CANH"
```

- [ ] **Step 2: Dùng helper chỉ tại quyết định nhóm trong `_auto_scene()`**

Thay đúng một dòng, không đổi writer/queue path:

```python
for i in xep:
    nhom.setdefault(_nhom_auto_cua(i, sc.get("id", ""), _data), []).append(i)
```

- [ ] **Step 3: Chạy hai test RED và test phụ thuộc hiện có**

```bash
./.venv/bin/python3 -m pytest -q tests/job_lifecycle/test_ref_run_all.py
```

Expected: toàn bộ test trong file PASS; test xuyên suốt cũ vẫn chứng minh portrait chạy trước `_FULL` và không enqueue trùng.

- [ ] **Step 4: Chạy nhóm test chia lô/trần ref liên quan**

```bash
./.venv/bin/python3 -m pytest -q \
  tests/job_lifecycle/test_tran_ref.py \
  tests/job_lifecycle/test_phu_thuoc_ref.py \
  tests/job_lifecycle/test_auto_characterization.py
```

Expected: PASS với các expected failure hiện hữu không đổi.

- [ ] **Step 5: Commit production backend**

```bash
git add sfboard/sfboard.py
git commit -m "fix: batch ready REF assets by role"
```

---

### Task 3: Khóa contract UI REF trước khi sửa giao diện

**Files:**
- Create: `tests/job_lifecycle/test_ref_ui_contract.py`

**Interfaces:**
- Consumes: source `sfboard/ui/board.js` và `sfboard/ui/board.css`.
- Produces: contract anchor, sidebar semantic control, focus và reduced-motion.

- [ ] **Step 1: Viết source contract test RED**

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS = (ROOT / "sfboard/ui/board.js").read_text(encoding="utf-8")
CSS = (ROOT / "sfboard/ui/board.css").read_text(encoding="utf-8")


def test_ref_co_ba_section_va_sidebar_con():
    for anchor in ("ref-nhan-vat", "ref-dao-cu", "ref-boi-canh"):
        assert f'id="{anchor}"' in JS
    assert 'class="refsub"' in JS
    assert 'type="button"' in JS
    assert "aria-label=" in JS


def test_ref_sidebar_co_focus_va_ton_trong_reduced_motion():
    assert "#snav .refsub:focus-visible" in CSS
    assert "prefers-reduced-motion: reduce" in JS
```

- [ ] **Step 2: Chạy và xác nhận RED**

```bash
./.venv/bin/python3 -m pytest -q tests/job_lifecycle/test_ref_ui_contract.py
```

Expected: hai test FAIL vì anchor, `refsub` và jump behavior chưa tồn tại.

- [ ] **Step 3: Commit UI contract tests**

```bash
git add tests/job_lifecycle/test_ref_ui_contract.py
git commit -m "test: define REF navigation contract"
```

---

### Task 4: Chia nội dung REF và sidebar bằng cùng quy tắc

**Files:**
- Modify: `sfboard/ui/board.js:951-987`
- Modify: `sfboard/ui/board.js:1185-1235`
- Modify: `sfboard/ui/board.css:1381-1523`
- Modify: `sfboard/ui/board.css:1526-1565`

**Interfaces:**
- Consumes: `DATA.scenes`, `card(sc, f)`, `jumpScene(id)`, trường `image/status`.
- Produces: `chiaRef(list)`, `tienDoRef(items)`, `jumpRefGroup(anchor)` và ba section anchor.

- [ ] **Step 1: Thêm helper phân loại dùng chung**

Trong `board.js`, thêm helper thuần trước `snav()`:

```javascript
function chiaRef(list) {
  const nhanVat = list.filter(f => /_(PORTRAIT|FULL)$/.test(f.id || ''));
  const daoCu = list.filter(f => (f.id || '').startsWith('REF_PROP_'));
  const boiCanh = list.filter(f => !nhanVat.includes(f) && !daoCu.includes(f));
  const portraits = nhanVat.filter(f => (f.id || '').endsWith('_PORTRAIT'));
  const thuTu = new Map(portraits.map((f, i) => [(f.id.split('_')[1] || f.id), i]));
  return { nhanVat, daoCu, boiCanh, thuTu };
}

function tienDoRef(items) {
  const n = items.length;
  const co = items.filter(x => x.image).length;
  const duyet = items.filter(x => x.status === 'approved').length;
  return { n, co, duyet, pctCo: n ? Math.round(co * 100 / n) : 0,
           pctDuyet: n ? Math.round(duyet * 100 / n) : 0 };
}
```

- [ ] **Step 2: Render ba section trong scene REF**

Giữ nguyên logic portrait + dải `_FULL`, nhưng append vào nested `.ref-grid` của section `ref-nhan-vat`. Dùng helper section chung để nội dung và tiến độ nhất quán; section rỗng không render:

```javascript
function taoRefSection(id, ten, items) {
  if (!items.length) return null;
  const p = tienDoRef(items);
  const sec = document.createElement('section');
  sec.className = 'ref-section';
  sec.id = id;
  sec.innerHTML = `<div class="ref-section-h"><h3>${esc(ten)}</h3>
    <span>${p.co}/${p.n} đã có ảnh · ${p.duyet}/${p.n} đã duyệt</span></div>
    <div class="ref-grid"></div>`;
  return sec;
}
```

Nhãn vai trò chèn vào thẻ portrait bằng thứ tự `thuTu`: index `< 4` là `Chính`, còn lại là `Phụ`. Không dùng màu làm tín hiệu duy nhất vì nhãn chữ luôn hiện.

```javascript
const idx = ref.thuTu.get(tenNhanVat);
d.querySelector('.body').insertAdjacentHTML(
  'afterbegin',
  `<span class="ref-role ${idx < 4 ? 'main' : 'supporting'}">${idx < 4 ? 'Chính' : 'Phụ'}</span>`
);
```

- [ ] **Step 3: Render sidebar REF cha/con**

Sau dòng cha REF, render ba button con từ cùng kết quả `chiaRef(sc.sfs || [])`:

```javascript
function jumpRefGroup(anchor) {
  const el = document.getElementById(anchor);
  if (!el) return;
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  el.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
}
```

Mỗi button có `type="button"`, `class="refsub"`, `aria-label` chứa tên nhóm và hai số tiến độ; visible text gồm tên nhóm, `% có ảnh`, `% duyệt`.

```javascript
function refSubRow(label, anchor, items) {
  const p = tienDoRef(items);
  if (!p.n) return '';
  return `<button type="button" class="refsub"
    aria-label="${esc(label)}: ${p.co}/${p.n} đã có ảnh, ${p.duyet}/${p.n} đã duyệt"
    onclick="jumpRefGroup('${anchor}')">
      <span class="sv">${esc(label)}</span>
      <span class="si ${p.co === p.n ? 'du' : ''}">${p.pctCo}%</span>
      <span class="sp">${p.pctDuyet}%</span>
    </button>`;
}
```

- [ ] **Step 4: Thêm CSS phân cấp, focus và responsive**

Áp dụng selector chung `#snav a, #snav button.refsub` để button nhận cùng font/tokens. `.refsub` thụt vào nhưng giữ chiều rộng, text không wrap cột phần trăm; `:focus-visible` dùng outline token `--acc`. `.ref-section` có `grid-column: 1 / -1`, `scroll-margin-top`, header phân cấp và nested `.ref-grid` dùng cùng grid sizing hiện có. Không thay breakpoint `1100px`; sidebar chỉ có một DOM và tiếp tục ẩn theo hành vi hiện tại.

```css
.ref-section {
  grid-column: 1 / -1;
  scroll-margin-top: calc(var(--hdrh, 52px) + 12px);
}
.ref-section + .ref-section { margin-top: 8px; }
.ref-section-h {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin: 0 0 10px;
  padding: 8px 2px;
  border-bottom: 1px solid var(--line);
}
.ref-section-h h3 { margin: 0; font-size: 14px; }
.ref-section-h span {
  color: var(--tx2);
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
}
.ref-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 15px;
}
#snav button.refsub {
  width: 100%;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
}
#snav .refsub {
  display: flex;
  align-items: baseline;
  gap: 5px;
  padding: 5px 7px 5px 16px;
  white-space: nowrap;
}
#snav .refsub:focus-visible {
  outline: 2px solid var(--acc);
  outline-offset: 2px;
}
```

- [ ] **Step 5: Chạy UI contract test và kiểm syntax JS**

```bash
./.venv/bin/python3 -m pytest -q tests/job_lifecycle/test_ref_ui_contract.py
node --check sfboard/ui/board.js
```

Expected: PASS, không có syntax error.

- [ ] **Step 6: Commit UI implementation**

```bash
git add sfboard/ui/board.js sfboard/ui/board.css
git commit -m "feat: organize REF workspace and sidebar"
```

---

### Task 5: Verification, visual QA và áp dụng runtime

**Files:**
- Verify: `tests/job_lifecycle/test_ref_run_all.py`
- Verify: `tests/job_lifecycle/test_ref_ui_contract.py`
- Verify: `sfboard/ui/board.js`
- Verify: `sfboard/ui/board.css`

**Interfaces:**
- Consumes: lifecycle gate, board local `http://localhost:8784`, in-app browser.
- Produces: bằng chứng test/compile/visual và runtime mới nếu queue đang rỗng.

- [ ] **Step 1: Đọc checklist web UI cần thiết**

Đọc `ui-ux-pro-max/references/quick-reference.md` mục Accessibility, Touch & Interaction, Performance; đối chiếu focus, contrast, responsive và reduced-motion. `pro-rules.md` chỉ dùng các mục áp dụng được cho web/desktop.

- [ ] **Step 2: Chạy test trọng tâm**

```bash
./.venv/bin/python3 -m pytest -q \
  tests/job_lifecycle/test_ref_run_all.py \
  tests/job_lifecycle/test_ref_ui_contract.py
node --check sfboard/ui/board.js
```

- [ ] **Step 3: Chạy full lifecycle + compile gate**

```bash
./test-job-lifecycle.command
```

Expected: tất cả test mới PASS và vẫn đúng bốn `xfailed` đã biết; compile gate PASS.

- [ ] **Step 4: Visual QA không gọi provider**

Mở board local bằng in-app browser, chuyển tab Start frames, cuộn tới REF và xác minh:

- Ba section đúng dữ liệu thật: Nhân vật, Đạo cụ, Bối cảnh.
- Bốn portrait đầu mang nhãn Chính; portrait thứ năm trở đi mang nhãn Phụ.
- Sidebar có ba dòng con với tỷ lệ đúng; click/focus tới đúng anchor.
- Không cuộn ngang hoặc che card ở desktop và viewport dưới breakpoint sidebar.
- Light/dark hiện có vẫn đủ tương phản; focus ring nhìn thấy.

Không bấm **Chạy hết**, **Tạo ảnh** hoặc bất kỳ control provider nào.

- [ ] **Step 5: Restart board có điều kiện**

Đọc `/api/jobs` và `/api/auto`. Chỉ restart khi không có job `running/queued` và REF auto đang tắt. Nếu có live work, giữ code trên đĩa và báo người dùng cần một cửa sổ restart an toàn; không tự dừng provider.

- [ ] **Step 6: Kiểm runtime mới**

Sau restart, xác nhận PID mới, `GET /api/jobs` trả 200, không có job tự hồi sinh và sổ runtime không phát sinh lỗi mới. Không tự chạy live REF để chứng minh batching.

- [ ] **Step 7: Đọc diff và commit phần verification còn lại**

```bash
git diff --check
git status --short
```

Chỉ stage các file thuộc feature này. Nếu không còn file feature chưa commit thì không tạo commit rỗng.
