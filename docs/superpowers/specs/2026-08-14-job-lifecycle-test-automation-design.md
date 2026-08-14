# Job Lifecycle Test Automation Design

Ngày: 2026-08-14
Trạng thái: Written spec đã được người dùng duyệt

## Mục tiêu

Tự động chứng minh các thay đổi lifecycle job ảnh/video không làm hỏng behavior đã
khóa, để người dùng không phải nhớ chạy test hoặc tự đóng vai tester cơ khí.

Phase này bổ sung đúng bốn thứ:

1. `pytest` chạy toàn bộ 35 test `unittest` hiện có mà chưa cần rewrite.
2. `pytest-cov` đo coverage riêng package thuần `sfboard/jobs`.
3. Một command local duy nhất chạy test + coverage + compile gate.
4. GitHub Actions tự chạy cùng gate khi push/PR sau này.

## Không nằm trong phạm vi

- Không sửa production, lifecycle behavior hoặc năm known ambiguity.
- Không đổi 35 test từ `unittest.TestCase` sang pytest style.
- Không cài Hypothesis trước khi có `JobManager + MemoryJobStore` ở Phase 2.
- Không cài Sentry SDK hoặc gửi dữ liệu ra dịch vụ bên ngoài.
- Không thêm mutmut, OpenTelemetry, Prometheus hoặc AI testing agent.
- Không push GitHub trong task này.
- Không chạy Chrome, provider hoặc live integration có thể tiêu credit.

## Nguồn dependency được chấp nhận

Chỉ dùng package phát hành từ các project chính chủ:

- `pytest==9.1.1` từ `pytest-dev/pytest`, Python 3.10+.
- `pytest-cov==7.1.0` từ `pytest-dev/pytest-cov`, Python 3.9+.

Hai package được pin chính xác trong `requirements-test.txt` để local và CI dùng
cùng version. Không copy source repo vào dự án và không dùng package tên gần giống.

## Kiến trúc

```text
Developer / Codex / Claude
          │
          ▼
test-job-lifecycle.command
          │
          ├─ pytest: 35 lifecycle tests
          ├─ pytest-cov: sfboard/jobs >= 80%
          └─ py_compile: legacy + domain package

GitHub push / pull request
          │
          ▼
.github/workflows/job-lifecycle-tests.yml
          │
          └─ chạy cùng ba gate trên Python 3.10 và 3.14
```

Local script và CI gọi cùng command options; không có một bộ luật test riêng trong
workflow làm drift khỏi máy local.

## File thay đổi

### `requirements-test.txt`

Chỉ chứa:

```text
pytest==9.1.1
pytest-cov==7.1.0
```

Dependency test tách khỏi `grokpipe/requirements.txt` vì board runtime không cần
pytest/coverage để chạy.

### `pytest.ini`

Quy định:

- Test root: `tests/job_lifecycle`.
- Pattern: `test_*.py`.
- Strict markers/config.
- Hiển thị lý do expected failure/skip.
- Không tự thêm live test directory.

Không đặt coverage command trong `addopts`; script/CI truyền explicit để người chạy
pytest targeted test không bị ép coverage toàn package.

### `test-job-lifecycle.command`

Command chạy được từ Finder hoặc shell, luôn đổi về repo root và dùng
`./.venv/bin/python3`.

Luồng:

1. Fail với hướng dẫn rõ nếu `.venv` hoặc pytest chưa tồn tại.
2. Chạy `pytest tests/job_lifecycle` với coverage `sfboard/jobs`.
3. Fail nếu coverage dưới 80%.
4. Compile `hangdoi.py`, `sfboard.py` và `sfboard/jobs/*`.
5. Không mở board/Chrome và không truy cập network.

Expected baseline: 35 tests, 30 pass và đúng 5 expected failures/xfailed.

### `.github/workflows/job-lifecycle-tests.yml`

Triggers:

- `pull_request`.
- `push` vào `main` hoặc `codex/**`.
- `workflow_dispatch` để chạy tay.

Security và isolation:

- `permissions: contents: read`.
- Ubuntu hosted runner.
- Matrix Python `3.10` và `3.14`.
- Chỉ checkout source, cài `requirements-test.txt`, chạy test/compile.
- Không secrets, không DSN, không project phim, không Playwright/browser.
- Không upload prompt, media hoặc coverage sang dịch vụ thứ ba.

CI không dùng `test-job-lifecycle.command` trực tiếp vì script local yêu cầu `.venv`;
workflow gọi cùng pytest/compile arguments bằng interpreter của matrix.

### `docs/JOB-LIFECYCLE-README.md`

Verification section đổi từ `unittest discover` sang command chuẩn:

```bash
./test-job-lifecycle.command
```

Giữ lệnh chi tiết bên dưới để debug khi gate fail và thêm lệnh cài dependency:

```bash
./.venv/bin/python3 -m pip install -r requirements-test.txt
```

README tiếp tục nói rõ năm expected failures là known ambiguity, không phải test
noise được phép tăng tùy ý.

## Coverage policy

Coverage chỉ đo:

```text
sfboard/jobs/__init__.py
sfboard/jobs/models.py
sfboard/jobs/errors.py
```

Không đo `sfboard.py`/`hangdoi.py` ở Phase A vì phần lớn test hiện là
characterization/source contract; một phần trăm tổng thấp sẽ không phản ánh chất
lượng state core và dễ khuyến khích test giả chỉ để tăng số.

Ngưỡng bắt buộc: **80% line coverage** cho `sfboard/jobs`.

Nếu baseline thấp hơn 80%, implementation phải thêm test domain có assertion thật;
không được hạ ngưỡng và không dùng blanket `# pragma: no cover`.

Coverage không chứng minh behavior đúng. Gate vẫn bắt buộc regression tests và năm
known bug vẫn phải có executable expected failure.

## Expected-failure policy

- Baseline phải báo đúng năm expected failures/xfailed.
- Không được thêm expected failure mới để làm CI xanh.
- Khi sửa một known bug: chứng minh red → green, bỏ decorator đúng test và giảm
  baseline count từ 5 xuống 4.
- Unexpected success phải được điều tra, không bỏ qua im lặng.

Phase A không viết plugin để parse cứng số `5` từ terminal output. Số baseline được
ghi trong README và review checklist; Phase 2 sẽ thay expected failures bằng state
machine tests thường khi từng bug được xử lý.

## Failure behavior

Gate fail nếu:

- Bất kỳ test thường nào fail/error.
- Coverage `sfboard/jobs` dưới 80%.
- Compile lỗi.
- Dependency test không cài hoặc version resolution lỗi.

Gate không chạy live integration. Lỗi chỉ xuất hiện khi mở browser/provider vẫn cần
runtime event journal/invariant monitor của Phase 2 và Sentry opt-in về sau.

## Deferred tools

### Hypothesis

Được thêm trong spec riêng sau khi `JobManager` và `MemoryJobStore` có API thuần.
Mục tiêu khi đó là sinh chuỗi enqueue/run/fail/retry/cancel/stop và kiểm invariant.

### Sentry

Không thêm dependency ở Phase A. Chỉ xem xét sau khi người dùng chọn cloud opt-in,
có `before_send` scrubber và cấm prompt/media/path/account credential.

## Kiểm tra triển khai

1. Chạy suite cũ bằng `unittest` trước khi cài package để giữ baseline.
2. Cài đúng `requirements-test.txt` trong `.venv`.
3. Chạy pytest targeted và xác nhận 35 test/5 xfailed.
4. Chạy coverage, đạt tối thiểu 80% cho `sfboard/jobs`.
5. Chạy compile gate.
6. Validate workflow YAML và kiểm không có secret/network/live command.
7. Chạy `test-job-lifecycle.command` từ repo root và một thư mục khác.
8. `git diff --name-only` chỉ gồm file test tooling, workflow và README; không có
   production file.

## Điều kiện thành công

- Một command local tự chạy toàn bộ gate.
- GitHub Actions định nghĩa cùng gate trên Python 3.10 và 3.14.
- 35 test cũ chạy được dưới pytest mà không rewrite.
- Đúng năm expected failures được giữ.
- Coverage `sfboard/jobs` đạt ít nhất 80%.
- Không có live provider/network behavior trong tests.
- Production dependencies và behavior không đổi.
- Hypothesis/Sentry vẫn deferred, không được cài gián tiếp.
