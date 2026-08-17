# Audit lifecycle job hiện hành

> Phạm vi: producer, queue, state, retry, cancel/stop, account, worker,
> recovery, API/UI và compatibility. Cập nhật 2026-08-17.

## Kết luận

Kiến trúc mới đã là production authority mặc định và giải quyết các lỗi hệ
thống chính của kiến trúc cũ: state phân tán, retry chồng, account race, queue
mất sau restart, video resubmit mù và late result ghi nhầm. Legacy vẫn còn trong
repo để tương thích/rollback nhưng không được nắm authority ở mode mặc định.

Không gọi kiến trúc “không thể lỗi”: DOM/provider vẫn có thể thay đổi. Điểm khác
biệt là lỗi hiện được cô lập theo job/execution/attempt/account/phase và có
event/reason để debug.

## Authority audit

| Concern | Authority hiện tại | Lớp không được quyết định |
|---|---|---|
| create/replay intent | producer + SQLite | UI retry, direct queue writer |
| job transition | runtime/manager | DOM worker, `JOBS`, watchdog |
| execution order/lease | scheduler | thread local queue loop |
| retry/backoff/rotate | RetryPolicy + runtime | worker, auto, HTTP handler |
| account seat/health | account allocator | tab counting heuristic |
| result commit | result committer + runtime | downloader/direct file callback |
| recovery | runtime startup recovery | clear/rebuild queue script |

`sfboard.py` vẫn là integration boundary lớn, nhưng các quyết định trên được gọi
vào domain/runtime thay vì tự thực hiện ở endpoint.

## Producer và idempotency

- UI/API/auto/external client đi qua producer command.
- Intent fingerprint bao gồm payload có ý nghĩa.
- Replay giống nhau không schedule lần hai.
- Replay khác payload conflict.
- Active scope tránh hai intent sống tranh cùng asset.
- Rerun terminal tạo intent/JobId mới.

Rủi ro cần tiếp tục audit: mọi endpoint mới hoặc script mới phải gửi
`Idempotency-Key`; không được gọi thẳng `hangdoi.them`/ghi `JOBS`.

## Scheduler và concurrency

- Execution có identity bền vững, member list và state riêng.
- Lease + TTL ngăn hai worker cùng lấy một execution.
- `not_before` giữ retry backoff.
- Account seat được allocate trước execution lease và release ở mọi outcome.
- Transaction rollback reload/reset scheduler constraint.

Regression có seat race, runtime concurrency, queue properties và scheduler
retry wiring.

## Retry, partial và account

- Chỉ một RetryPolicy quyết định action.
- Validation/permanent không phạt account.
- Quota cooldown + rotate; session trước submit reconnect có kiểm soát.
- Unknown/post-submit không tự retry.
- Partial batch không hồi sinh member đã completed.
- Forced account và fallback là dữ liệu intent/execution rõ.

## Cancel và stop

- Cancel tra execution theo member, không dựa vào label hiển thị.
- Grouped REF/image execution hủy đúng toàn bộ member vật lý liên quan.
- Running image revoke result lease để chặn late commit.
- Video đã submit trả reason an toàn thay vì tuyên bố đã hủy provider.
- Stop-all có HTTP regressions cho cả queued/running và không để một nhánh chạy
  tiếp do chỉ clear queue hiển thị.

## Persistence và recovery

- SQLite nằm trong project, schema có version và transaction.
- Restart giữ intent/job/execution/attempt/event.
- Pre-submit lease được release để retry.
- Post-submit hoặc missing-attempt chuyển `needs_attention`.
- Startup authoritative thất bại thì fail rõ; không tiếp tục ở trạng thái
  diagnostics nói authoritative nhưng runtime thiếu.

## Image live path

- One-attempt request/result mapping tách khỏi retry.
- Phase callback ghi chuẩn bị/attach/submit/wait/download/save.
- REF run-all gộp theo contract; `*_FULL` từ nhân vật thứ 5 có thể vào nhóm nhân
  vật phụ nhưng identity/output không bị nhập nhằng.
- Batch partial và multi-copy có regression riêng.
- `DauVetBuoc.xong()` và tải ảnh có executor regressions.

## Video live path

- Submit budget bền vững, giới hạn 1–20 theo scope.
- Source SF và attempt identity đi xuyên provider/download/save.
- Historical Grok post được seed/ledger để post cũ không bị nhận là output mới.
- Ledger local `~/.grokpipe-grok-posts.jsonl` hạn chế quyền file.
- Download result chỉ commit qua lease hiện tại; stale/late result bị chặn.
- Đã chạy controlled canary với nhiều SF khác nhau; gate vẫn tách khỏi provider
  để không tiêu credit tự động.

## Runtime diagnostics

- `/api/chan-doan`: mode, live status, worker/account/invariant.
- `/api/jobs`: projection job phục vụ UI/compatibility.
- `.grokpipe/runtime-bugs/events.jsonl`: journal qua restart, có redaction,
  classifier, fingerprint/dedupe.
- Beads bridge/Sentry là opt-in; journal local vẫn hoạt động khi integration
  ngoài không bật.

## Test gate

```bash
./test-job-lifecycle.command
```

Phạm vi gate:

- lifecycle domain/store/runtime/HTTP/UI contracts;
- concurrency và Hypothesis properties;
- runtime bug journal/diagnostics/redaction;
- image/video executor regressions;
- coverage `sfboard.jobs` ≥ 80%;
- compile production modules.

Mốc gate gần nhất: 709 pass, không xfail; coverage `sfboard.jobs` đạt 91,19%.

## Nợ kỹ thuật còn lại

1. `sfboard.py` còn lớn; nên tách integration modules theo HTTP, projection và
   browser coordination.
2. Legacy adapter/projection còn cần soak và consumer audit trước khi xóa.
3. DOM selector/provider behavior là dependency ngoài, cần canary có budget và
   cập nhật regression khi UI thay đổi.
4. Retention/compaction event và migration schema dài hạn cần policy khi dữ liệu
   project tăng lớn.
5. Operational alerting ngoài máy là tùy chọn; journal local vẫn là nguồn chính.

Các mục này không làm thay đổi production authority hiện tại và không được giải
quyết bằng thêm writer/retry path mới.
