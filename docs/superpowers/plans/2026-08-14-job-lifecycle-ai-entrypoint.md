# Job Lifecycle AI Entrypoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tạo một cửa vào ngắn để Codex, Serena, Superpowers và Claude Code định tuyến đúng tài liệu/test lifecycle mà không phải đọc toàn bộ tài liệu nguồn.

**Architecture:** `docs/JOB-LIFECYCLE-README.md` là nguồn routing duy nhất. `AGENTS.md` và một block ngắn trong `CLAUDE.md` chỉ đóng vai trò adapter, trỏ tới README và không sao chép state machine/invariant table.

**Tech Stack:** Markdown, shell verification, `rg`, Python stdlib qua `./.venv/bin/python3`; không thêm dependency.

## Global Constraints

- Không sửa production, queue, retry, account, API hoặc UI.
- Không rút gọn hoặc xoá năm tài liệu lifecycle nguồn.
- Không tạo hoặc sửa custom skill.
- `docs/JOB-LIFECYCLE-README.md` tối đa 150 dòng.
- `AGENTS.md` tối đa 25 dòng.
- Nội dung routing chỉ tồn tại trong README; adapter chỉ giữ trigger, pointer và workflow ngắn.
- Legacy vẫn là production authority; `sfboard/jobs` chưa được runtime import.
- Năm known ambiguity tiếp tục là `expectedFailure` cho đến phase sửa tương ứng.
- Mọi lệnh Python trong tài liệu dùng `./.venv/bin/python3` theo luật repo.
- Commit message là `update` theo `CLAUDE.md`.

---

## File map

| File | Thao tác | Trách nhiệm |
|---|---|---|
| `docs/JOB-LIFECYCLE-README.md` | Create | Current phase, routing, invariants, workflow, verification và file map |
| `AGENTS.md` | Create | Adapter cho Codex/Serena/Superpowers |
| `CLAUDE.md` | Modify near line 7 | Adapter cho Claude Code; giữ nguyên toàn bộ luật hiện có |

---

### Task 1: Tạo AI entrypoint và hai adapter

**Files:**
- Create: `docs/JOB-LIFECYCLE-README.md`
- Create: `AGENTS.md`
- Modify: `CLAUDE.md:7`
- Verify: shell contract và lifecycle suite hiện có.

**Interfaces:**
- Consumes: `docs/superpowers/specs/2026-08-14-job-lifecycle-ai-entrypoint-design.md`, năm tài liệu lifecycle nguồn và Phase 0–1 tests.
- Produces: một routing entrypoint ổn định tại `docs/JOB-LIFECYCLE-README.md`; adapter cho Codex/Claude chỉ trỏ tới entrypoint này.

- [ ] **Step 1: Chạy contract trước implementation và xác nhận nó fail**

Run:

```bash
test -f docs/JOB-LIFECYCLE-README.md \
  && test -f AGENTS.md \
  && rg -q 'docs/JOB-LIFECYCLE-README.md' AGENTS.md \
  && rg -q 'docs/JOB-LIFECYCLE-README.md' CLAUDE.md
```

Expected: FAIL vì README và `AGENTS.md` chưa tồn tại.

- [ ] **Step 2: Tạo README với nội dung chuẩn dưới đây**

Create `docs/JOB-LIFECYCLE-README.md`:

````markdown
# Job lifecycle — cửa vào cho AI

Đọc file này trước khi điều tra hoặc sửa job ảnh/video, `JOBS`, queue, state,
retry, cancel/stop, account assignment, auto producer, worker hoặc job API/UI.

## Đọc trong 60 giây

- Current phase: **Phase 0–1 đã triển khai trên branch lifecycle**.
- Production authority vẫn là legacy: `JOBS`, `PriorityQueue`, worker, retry và auto.
- `sfboard/jobs` mới chỉ là immutable domain model; production chưa import nó.
- 5 known ambiguity đang được khóa bằng `expectedFailure`, chưa được coi là đã sửa:
  cancel identity lô, auto-video enqueue trùng, auto/stop race, multi-copy identity,
  và forced-account retry mất constraint.
- Không refactor production trước khi xác định phase, owner và regression test.

## Quy trình sửa lỗi bắt buộc

1. Phân loại triệu chứng bằng bảng routing bên dưới.
2. Đọc đúng tài liệu được route, không nạp cả năm file nếu không cần.
3. Dùng Serena tìm definition, callers/references và mọi writer liên quan.
4. Dùng `superpowers:systematic-debugging` để xác định nguyên nhân gốc.
5. Viết regression test tái hiện lỗi và chạy thấy fail trước khi sửa.
6. Sửa đúng owner; không thêm writer, retry hoặc re-enqueue authority mới.
7. Chạy full lifecycle suite, compile gate và đọc diff trước khi kết luận.

## Đọc file nào?

| Triệu chứng/công việc | Đọc tiếp |
|---|---|
| State sai, terminal regress, transition mơ hồ | [State machine](JOB-STATE-MACHINE.md) |
| Retry vô hạn, enqueue trùng, job hồi sinh | [Audit](JOB-LIFECYCLE-AUDIT.md) + [Decisions](JOB-LIFECYCLE-DECISIONS.md) |
| Cancel riêng, stop-all, late result | [State machine](JOB-STATE-MACHINE.md) + [Audit](JOB-LIFECYCLE-AUDIT.md) |
| Chọn/xoay/ép sai tài khoản | [Architecture](JOB-ARCHITECTURE-TARGET.md) + [Decisions](JOB-LIFECYCLE-DECISIONS.md) |
| `/api/jobs`, create/cancel response hoặc queue UI | [HTTP characterization tests](../tests/job_lifecycle/test_http_contract.py) + [Migration plan](JOB-MIGRATION-PLAN.md) |
| Refactor, shadow mode, cutover authority | [Migration plan](JOB-MIGRATION-PLAN.md) + [Architecture](JOB-ARCHITECTURE-TARGET.md) |
| Không rõ expected behavior | [Decisions](JOB-LIFECYCLE-DECISIONS.md) |

## Invariant không được phá

- Mỗi lifecycle fact có đúng một authority quyết định.
- `COMPLETED`, `FAILED`, `CANCELLED` không chuyển state nữa.
- Cancel/stop xong không có timer, watchdog hoặc auto snapshot nào được hồi sinh job.
- Outcome sau submit không chắc chắn phải vào `NEEDS_ATTENTION`, không tự submit lại.
- Forced account áp dụng cho mọi retry trừ khi job cho phép fallback rõ ràng.
- Explicit rerun tạo Job mới và giữ `rerun_of`; không revive terminal Job.
- Asset ID không phải Job, Execution hoặc Attempt ID.
- Queue token/state text không được dùng thay durable identity/version.

## Dùng Serena và Superpowers

Serena dùng cho code navigation, không phải nguồn kiến trúc riêng:

1. Tìm symbol định nghĩa hành vi.
2. Tìm callers/references và call path.
3. Tìm mọi writer của `JOBS`, queue, retry state và account assignment.
4. Xác nhận không còn writer/re-enqueue authority thứ hai sau thay đổi.

Superpowers workflow:

- Bug/unexpected behavior → `systematic-debugging`.
- Bugfix/behavior change → `test-driven-development`.
- Nhiều bước → `writing-plans`, rồi `executing-plans` hoặc subagent workflow.
- Trước kết luận hoàn tất → `verification-before-completion`.

## Verification

```bash
./.venv/bin/python3 -m unittest discover -s tests/job_lifecycle -p 'test_*.py'
./.venv/bin/python3 -m py_compile \
  sfboard/hangdoi.py sfboard/sfboard.py \
  sfboard/jobs/__init__.py sfboard/jobs/models.py sfboard/jobs/errors.py
```

Kết quả Phase 0–1 hiện tại: 35 tests, 30 pass và đúng 5 `expectedFailure`.
Một expected failure biến thành unexpected success cũng phải được giải thích: chỉ bỏ decorator
ở phase sửa lỗi tương ứng và sau khi đã xác minh target behavior.

## File map

- [Decisions](JOB-LIFECYCLE-DECISIONS.md): expected behavior đã được duyệt.
- [State machine](JOB-STATE-MACHINE.md): legal/illegal transitions.
- [Architecture](JOB-ARCHITECTURE-TARGET.md): owner và dependency direction.
- [Audit](JOB-LIFECYCLE-AUDIT.md): writer, re-enqueue, ambiguity và duplicated responsibility.
- [Migration plan](JOB-MIGRATION-PLAN.md): current/cutover phase và rollback gate.
- [Domain models](../sfboard/jobs/models.py): identity và immutable facts Phase 1.
- [Lifecycle tests](../tests/job_lifecycle/): executable legacy/domain contract.
- [Legacy queue/state](../sfboard/hangdoi.py) và [runtime/API](../sfboard/sfboard.py):
  production authority hiện tại.

## Khi phải dừng hỏi người dùng

- Expected behavior chưa có trong Decisions hoặc mâu thuẫn giữa hai quyết định.
- Cần đổi retry budget, credit semantics, overwrite asset hoặc stop policy.
- Fix cần mở rộng sang production subsystem ngoài lifecycle đã audit.
- Cần chạy live integration có thể mở Chrome, submit provider hoặc tiêu credit.
````

- [ ] **Step 3: Tạo adapter Codex/Serena/Superpowers**

Create `AGENTS.md` với đúng nội dung:

```markdown
# Hướng dẫn AI trong repo

Luôn trả lời người dùng bằng tiếng Việt.

Khi task liên quan job ảnh/video, `JOBS`, queue, state, retry, cancel/stop,
account assignment, auto producer, worker, watchdog hoặc job API/UI:

1. Đọc `docs/JOB-LIFECYCLE-README.md` trước.
2. Xác định migration phase và production authority trước khi sửa.
3. Dùng Serena tìm symbol, callers/references và mọi writer liên quan.
4. Dùng `superpowers:systematic-debugging` cho lỗi hoặc hành vi bất ngờ.
5. Viết regression test trước mọi bugfix/behavior change.
6. Không tạo thêm writer, retry hoặc re-enqueue authority.
7. Chạy full lifecycle suite và compile gate trước khi kết luận.

Không tự ý sửa skill, ảnh/video đang dùng hoặc chạy live provider có thể tiêu credit.
```

- [ ] **Step 4: Thêm adapter Claude Code mà không sửa luật hiện có**

Insert ngay sau đoạn mở đầu của `CLAUDE.md`, trước `## ⛔ LUẬT CỨNG`:

```markdown
## Lifecycle job ảnh/video

Khi task liên quan `JOBS`, queue, state, retry, cancel/stop, account assignment,
auto/worker/watchdog hoặc job API/UI, bắt buộc đọc
[`docs/JOB-LIFECYCLE-README.md`](docs/JOB-LIFECYCLE-README.md) trước.

Làm theo chuỗi: README → tài liệu được route → symbol/writer bằng Serena nếu khả
dụng → regression test → fix đúng owner → full verification gate. Không tạo thêm
writer, retry hoặc re-enqueue authority.
```

Không chỉnh sửa bất kỳ section nào khác của `CLAUDE.md`.

- [ ] **Step 5: Chạy structural contract**

Run:

```bash
set -e
test "$(wc -l < docs/JOB-LIFECYCLE-README.md)" -le 150
test "$(wc -l < AGENTS.md)" -le 25
test "$(rg -c 'docs/JOB-LIFECYCLE-README.md' AGENTS.md)" -eq 1
test "$(rg -c 'docs/JOB-LIFECYCLE-README.md' CLAUDE.md)" -eq 1
for marker in \
  JOB-LIFECYCLE-DECISIONS.md JOB-STATE-MACHINE.md JOB-ARCHITECTURE-TARGET.md \
  JOB-LIFECYCLE-AUDIT.md JOB-MIGRATION-PLAN.md \
  systematic-debugging test-driven-development verification-before-completion
do
  rg -q "$marker" docs/JOB-LIFECYCLE-README.md
done
```

Expected: exit code 0; README ≤150 dòng, AGENTS ≤25 dòng và mỗi adapter có đúng một pointer.

- [ ] **Step 6: Kiểm mọi relative Markdown link trong README**

Run:

```bash
/Users/may1/Desktop/grokpipe/.venv/bin/python3 - <<'PY'
import re
from pathlib import Path

doc = Path("docs/JOB-LIFECYCLE-README.md")
targets = re.findall(r"\[[^]]+\]\(([^)#]+)(?:#[^)]+)?\)", doc.read_text())
missing = [target for target in targets if not (doc.parent / target).resolve().exists()]
if missing:
    raise SystemExit(f"Missing README links: {missing}")
print(f"OK: {len(targets)} relative links tồn tại")
PY
```

Expected: `OK: <N> relative links tồn tại`, không có missing link.

- [ ] **Step 7: Chạy lifecycle regression và compile gate**

Run:

```bash
/Users/may1/Desktop/grokpipe/.venv/bin/python3 \
  -m unittest discover -s tests/job_lifecycle -p 'test_*.py'
/Users/may1/Desktop/grokpipe/.venv/bin/python3 -m py_compile \
  sfboard/hangdoi.py sfboard/sfboard.py \
  sfboard/jobs/__init__.py sfboard/jobs/models.py sfboard/jobs/errors.py
```

Expected: 35 tests `OK (expected failures=5)`; compile exit code 0.

- [ ] **Step 8: Xác minh scope và commit**

Run:

```bash
git diff --check
git diff --name-only
```

Expected: chỉ có `AGENTS.md`, `CLAUDE.md`, `docs/JOB-LIFECYCLE-README.md`.

Commit:

```bash
git add AGENTS.md CLAUDE.md docs/JOB-LIFECYCLE-README.md
git commit -m "update"
```

## Definition of Done

- Codex/Serena/Superpowers và Claude Code có cùng một lifecycle entrypoint.
- README không quá 150 dòng và AGENTS không quá 25 dòng.
- Adapter không sao chép routing/invariant table.
- Mọi link tương đối tồn tại.
- README nói rõ legacy vẫn là production authority và domain package chưa nối runtime.
- README ghi rõ 5 expected failures và full verification commands.
- Full lifecycle suite/compile gate pass.
- Không có production file nào thay đổi.
