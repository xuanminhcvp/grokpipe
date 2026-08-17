# Hồ sơ migration lifecycle job

> Trạng thái: **Phase 0–12 đã hoàn tất; production đã cutover**.
> File này là bản tóm tắt lịch sử, không phải danh sách TODO đang chờ.

## Trạng thái hiện tại

- Production mặc định: `authoritative + live`.
- Repository SQLite bền vững theo project.
- Producer, scheduler, attempt, account, retry, result và recovery đã đi qua
  lifecycle runtime.
- Image/video DOM worker đã nằm sau one-attempt boundary và phase callbacks.
- API/UI cũ được giữ qua compatibility projection.
- Legacy vẫn tồn tại như rollback/soak boundary, không còn là production
  authority mặc định.

## Các phase đã hoàn tất

| Phase | Kết quả |
|---|---|
| 0 | Characterization test khóa queue, cancel, retry, account, auto, HTTP |
| 1 | Typed identity, model bất biến, state và error taxonomy |
| 2 | In-memory store/manager + shadow projection |
| 3 | Producer commands, fingerprint, idempotency, active scope |
| 4 | Scheduler, execution identity, lease, `not_before` |
| 5 | Attempt, account allocator, seat/health/cooldown |
| 6 | Image executor adapter, batch/partial result |
| 7 | Video executor, submit/credit boundary |
| 8 | Cancel, stop-one, stop-all và stale result protection |
| 9 | Một RetryPolicy, loại retry authorities trùng |
| 10 | SQLite authoritative, transaction và startup recovery |
| 11 | Auto producer, invariant monitor, external client compatibility |
| 12 | API/UI projection, live DOM worker cutover, canary và default switch |

Chi tiết kế hoạch gốc đã được rút gọn trong `docs/superpowers/plans/` và Git
history. Không copy lệnh/checklist cũ để tiếp tục triển khai vì assumption về
authority khi đó không còn đúng.

## Gate cutover đã dùng

- characterization/HTTP contracts giữ tương thích;
- property tests cho queue/retry/concurrency;
- SQLite replay/conflict/rollback/recovery;
- account seat race và lease cleanup;
- image partial/multi-copy/REF batch;
- video phase, post identity, download/save và stale result;
- invariant monitor bằng 0;
- controlled live image/video canary có budget.

Mốc gate gần nhất: 709 test pass, không xfail; coverage `sfboard.jobs` đạt
91,19%.

## Rollback hiện hành

Rollback chỉ khi không còn execution authoritative active:

```bash
GROKPIPE_JOB_MODE=legacy GROKPIPE_LIVE_EXECUTOR=0 \
  ./chay-board.command <PROJECT>.project
```

Rollback không được kèm xoá database. Giữ:

- `.grokpipe/job-lifecycle.sqlite3`;
- `.grokpipe/runtime-bugs/events.jsonl`;
- board log;
- account/live-budget state.

Sau rollback phải tạo incident/regression test và sửa forward.

## Công việc sau migration

Đây là bảo trì/soak, không phải phase migration còn thiếu:

- tiếp tục quan sát live workload và invariant;
- loại legacy code theo consumer audit từng phần;
- tách `sfboard.py` lớn thành module nhỏ mà không đổi authority;
- thêm migration schema khi data model đổi;
- giữ canary có credit cap cho provider/DOM thay đổi.

## Điều kiện xóa legacy

Chỉ xóa một compatibility path khi:

1. không còn caller/consumer production;
2. API/UI contract đã có replacement;
3. soak log không có fallback sử dụng;
4. regression suite khóa hành vi thay thế;
5. rollback không còn phụ thuộc path đó hoặc đã có rollback khác;
6. full gate và inert startup smoke pass.

Không xóa hàng loạt chỉ để giảm số dòng; tách từng authority-free slice để diff
và rollback rõ.
