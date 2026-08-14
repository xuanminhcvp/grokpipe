# Runtime Bug Journal and Beads Bridge Design

Ngày: 2026-08-14
Trạng thái: Thiết kế hội thoại đã duyệt, chờ người dùng duyệt written spec
Phụ thuộc: `2026-08-14-beads-foundation-design.md` đã triển khai và verification xanh

## Mục tiêu

Lưu bền bằng chứng lỗi runtime ảnh/video và tự tạo hoặc cập nhật đúng một Bead cho
mỗi lỗi nghiêm trọng. Khi người dùng mở Codex hoặc Claude, AI phải lần được từ Bead
tới event, stack trace, job/attempt, source file/function/line và regression test
liên quan mà không cần người dùng tự đóng vai tester.

## Hiện trạng

- `LOI_SO` là deque RAM tối đa 800 warning/error; restart board làm mất dữ liệu.
- `VET` là RAM tối đa 40 event/job và 400 job; cleanup/restart làm mất lịch sử.
- `/api/loi`, `/api/jobs`, `/api/chan-doan` đọc được khi board đang sống.
- Server log record hiện chỉ giữ `getMessage()`, không giữ full exception traceback.
- Lỗi JavaScript UI chỉ nằm trong memory của trang và mất khi reload.
- `ErrorFact`/`JobEvent` đã có ở domain Phase 1 nhưng production chưa phát chúng.

## Không nằm trong phạm vi

- Không sửa lifecycle decision, queue order, retry budget, account rotation hoặc
  re-enqueue authority.
- Không tự sửa code, commit, push hoặc đóng Bead.
- Không gửi dữ liệu tới Sentry, OpenTelemetry hoặc dịch vụ cloud.
- Không tự tạo Bead cho warning thường, user cancel, validation input hoặc quota
  đã phân loại.
- Không nhét toàn bộ runtime log hoặc media vào Dolt/Beads.
- Không dùng parsing message mơ hồ để quyết định retry/state production.

## Kiến trúc

```text
runtime boundary / explicit severe signal
                 │
                 ▼
        RuntimeBugJournal
        sanitize + JSONL append
                 │
                 ▼
          BugClassifier
     severity + typed reason code
                 │
                 ▼
           BeadsBridge
  checkpoint + fingerprint + bd CLI
          │                  │
          ▼                  ▼
 existing Bead update     new bug Bead
          └──────────┬──────────┘
                     ▼
          Codex / Claude: bd ready
```

Runtime chỉ phụ thuộc journal/classifier thuần. `bd` subprocess chỉ chạy trong
bridge worker tách biệt; không nằm trên worker ảnh/video hoặc request handler path.

## Component boundaries

### `RuntimeBugJournal`

- Nhận immutable event dictionary đã typed/validated.
- Redact trước khi serialize.
- Append đúng một JSON object trên mỗi dòng dưới lock.
- Flush mỗi severe event; lỗi ghi journal chỉ log tối giản ra stderr rồi trả về,
  không ném ngược vào production.
- Xoay 10 segment, tối đa 10 MiB/segment, tổng xấp xỉ 100 MiB.

Storage local:

```text
.grokpipe/runtime-bugs/events.jsonl
.grokpipe/runtime-bugs/events.jsonl.1 ... .9
.grokpipe/runtime-bugs/bridge-state.json
```

Toàn bộ `.grokpipe/runtime-bugs/` phải bị Git ignore. Asset/prompt không được copy
vào đây.

### `BugClassifier`

Chỉ trả `reportable=true` cho:

- uncaught exception tại worker/thread/process boundary;
- explicit `ERROR` hoặc `CRITICAL` record có exception/source context;
- worker chết ngoài stop/cancel flow;
- retry exhausted với typed error class `SESSION_TRANSIENT`,
  `PROVIDER_TRANSIENT`, `ACCOUNT_LOST`, `PERMANENT` hoặc `UNKNOWN_OUTCOME`;
- lifecycle invariant violation từ monitor/tested assertion;
- queue stalled do monitor xác nhận worker/queue mismatch vượt threshold cấu hình.

Không report:

- `VALIDATION`, `CANCELLED`, expected stop, normal retry hoặc user action;
- `QUOTA_RATE_LIMIT` đơn lẻ đã được account policy xử lý;
- warning không có severe reason code;
- lỗi của chính bridge.

Legacy instrumentation phải truyền explicit reason code ở boundary được audit;
không suy loại lỗi bằng substring để thay đổi production behavior.

### `BeadsBridge`

- Đọc journal từ checkpoint; xử lý idempotently theo `event_id`.
- Chỉ dùng `bd` CLI qua subprocess với timeout hữu hạn.
- Không giữ database handle trong runtime process.
- Khi `bd` thiếu, timeout, exit non-zero hoặc workspace unhealthy: giữ checkpoint
  cũ, ghi bridge health và retry theo backoff; không làm mất event.
- Không tạo Bead cho lỗi do bridge sinh ra.
- Chỉ bật auto-create khi Beads foundation checks xanh và config local cho phép.

## Event schema

Mỗi dòng JSONL có schema versioned:

```json
{
  "schema_version": 1,
  "event_id": "uuid",
  "occurred_at": "RFC3339 UTC",
  "severity": "ERROR",
  "category": "unhandled_exception",
  "reason_code": "WORKER_CRASH",
  "fingerprint": "sha256",
  "job": {
    "job_id": "typed-or-legacy-id",
    "execution_id": "optional",
    "attempt_id": "optional",
    "kind": "image-or-video",
    "phase": "preparing-or-submitted-or-downloading",
    "state_from": "optional",
    "state_to": "optional",
    "retry_index": 0,
    "retry_budget": 0,
    "retry_decision": "optional"
  },
  "runtime": {
    "worker_id": "sanitized",
    "account_label": "sanitized",
    "process_start_id": "uuid",
    "git_commit": "sha"
  },
  "exception": {
    "type": "TimeoutError",
    "message": "redacted",
    "stacktrace": "repo-relative-redacted",
    "source_file": "sfboard/sfboard.py",
    "source_function": "_worker",
    "source_line": 1505
  }
}
```

Các field chưa biết dùng `null`, không dùng chuỗi giả. Schema parser bỏ qua field
mới chưa biết nhưng reject record thiếu `schema_version`, `event_id`, timestamp,
severity, category, reason code hoặc fingerprint.

## Redaction

Redactor chạy trước journal và trước Bead payload:

- Loại cookie, authorization header, bearer token, API key, DSN và password.
- Không ghi prompt, raw request/response body, base64, ảnh hoặc video.
- Đổi absolute home/project path thành repo-relative path khi nằm trong repo;
  path ngoài repo thành basename hoặc `<external>`.
- Account chỉ giữ label/id nội bộ cần điều tra; không giữ credential/profile path.
- URL bỏ query/fragment; URL phiên đăng nhập/chat riêng bị thay bằng origin + route class.
- Message và stack trace có giới hạn kích thước; original nhạy cảm không lưu chỗ khác.

Unit tests dùng canary secrets để chứng minh chúng không xuất hiện trong journal,
Bead description hoặc diagnostic endpoint.

## Fingerprint và dedupe

Fingerprint SHA-256 được tạo từ canonical tuple:

```text
exception_type
 reason_code
 job_kind
 phase
 repo_relative_source_file
 source_function
 source_line
 normalized_message_template
```

Normalizer loại UUID, job ID, attempt ID, port, timestamp và số đếm biến đổi. Nó
không loại error code, source line hoặc phase vì các giá trị đó phân biệt bug.

Quy tắc Bead:

- Một open Bead cho mỗi fingerprint.
- Event trùng cập nhật occurrence count, first/last seen, commit gần nhất và tối đa
  10 event ID gần nhất.
- Bead đã đóng mà fingerprint tái xuất hiện trên commit mới được reopen và ghi
  recurrence; không tạo task song song.
- Bead description chứa summary đã redact và đường dẫn local tới journal/event;
  full stack trace không copy hàng loạt vào Beads.

## Bead payload

Bead tự tạo có:

- type `bug`;
- title `[runtime][image|video] <Exception> tại <function>`;
- labels `runtime`, `auto-detected`, `image|video`, severity;
- fingerprint, occurrence count, first/last seen, current Git commit;
- source file/function/line và event ID gần nhất;
- acceptance checklist: reproduce, regression red, minimal fix, full gate, runtime
  evidence hoặc explicit reason nếu không thể reproduce.

Bridge không claim, assign, close hoặc đổi priority của Bead hiện có. Priority ban
đầu map từ severity/reason code theo bảng cố định; không dùng LLM trong runtime.

## Trigger và execution model

- Journal hook ở logging `ERROR/CRITICAL`, worker top-level exception boundary và
  explicit invariant/retry-exhausted reporters.
- Một daemon bridge thread có bounded wake signal; event vẫn nằm trên disk nếu
  signal bị mất hoặc process chết.
- Startup scan tiếp tục từ durable checkpoint.
- Backoff bridge giới hạn, có jitter; không busy-loop.
- Shutdown cố flush journal nhưng không chờ Dolt/`bd` vô hạn.
- Config mặc định trong verification là journal-only. Auto-create chỉ bật sau khi
  integration tests, redaction tests và `bd doctor` xanh.

## Diagnostics cho người và AI

`/api/chan-doan` bổ sung khối không nhạy cảm:

```json
{
  "bug_bridge": {
    "mode": "journal-only-or-auto-create",
    "pending": 0,
    "last_sync_at": "optional",
    "last_error": "sanitized-or-empty",
    "created": 0,
    "updated": 0
  }
}
```

Một command local đọc-only cung cấp `status`, `list`, `show <event-id>` và command
`sync` explicit. Output JSON ổn định để Codex/Claude parse; không cần đọc file lớn
bằng text editor.

## Test strategy

### Unit

- Schema validation, JSONL round-trip, rotation và truncated-tail recovery.
- Redaction mọi loại secret/path/media canary.
- Classifier report/ignore đúng reason code.
- Fingerprint ổn định khi UUID/port/timestamp đổi và khác khi phase/source đổi.
- Bead payload giới hạn kích thước và không chứa raw stack secret.

### Bridge contract

- Fake `bd` executable ghi argv/stdin để kiểm create/update/reopen.
- Cùng fingerprint 10 event chỉ create một lần và update count thành 10.
- Event khác fingerprint tạo Bead khác.
- Restart từ checkpoint không replay event đã ack.
- `bd` missing, timeout, corrupt output, non-zero: checkpoint không tiến, runtime
  không fail; lần sau sync thành công.
- Bridge error không tự sinh recursive Bead.

### Integration

- Temporary Beads workspace, không dùng database thật của người dùng.
- Journal-only smoke test trước; bật auto-create trong temp workspace và query
  lại bằng `bd show`/JSON output.
- Instrumented worker exception ghi source/trace đúng nhưng giữ nguyên state/retry
  behavior characterization hiện tại.
- `/api/chan-doan` không lộ secret và vẫn tương thích field cũ.
- Full `./test-job-lifecycle.command`; không Chrome/provider/network/credit.

## Rollout

1. Implement journal/schema/redactor và test, chưa hook production.
2. Hook severe boundaries ở journal-only; chạy characterization và fault injection.
3. Implement bridge với fake CLI và temporary Beads workspace.
4. Chạy `bd doctor`; bật auto-create local.
5. Inject một synthetic severe event không chạm provider; xác nhận đúng một Bead.
6. Restart board; xác nhận checkpoint/dedupe và diagnostics.
7. Giữ kill switch chuyển về journal-only mà không mất event.

## Failure và rollback

- Journal unavailable/full: emit bounded stderr warning, không ném vào worker.
- Dòng cuối bị cắt do crash: quarantine/skip đúng dòng, tiếp tục segment hợp lệ.
- Schema mới hơn reader: dừng bridge với health error, giữ nguyên checkpoint/data.
- Beads unhealthy: chuyển degraded, journal tiếp tục, không retry nóng.
- Dedupe sai: không tự merge/delete Bead; dừng auto-create và sửa bridge qua test.
- Rollback production hook bằng config journal-only; không xóa journal hoặc Beads.

## Điều kiện thành công

- Restart board không làm mất severe runtime evidence.
- Một fingerprint lặp tạo đúng một Bead và cập nhật idempotently.
- AI từ Bead tìm được event, stack trace, source và lifecycle context cần thiết.
- Cancel/validation/warning không tạo task rác.
- Secret/prompt/media không xuất hiện trong journal, API hoặc Beads.
- `bd`/Dolt lỗi không thay đổi job outcome, queue, retry hoặc account behavior.
- Không cloud sync; không AI tự sửa/commit/close.
- Full lifecycle gate giữ baseline 30 pass, 5 xfailed cho tới phase sửa từng bug.
