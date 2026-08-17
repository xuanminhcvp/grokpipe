# Hồ sơ thiết kế lịch sử — lifecycle test automation

> Thiết kế đã triển khai; lệnh hiện hành là `./test-job-lifecycle.command`.

## Ý định thiết kế

Có một gate tái lập được, không gọi provider, bao phủ domain/runtime/HTTP,
runtime journal, executor và compile production modules.

## Quyết định còn hiệu lực

- Test dependency được pin trong `requirements-test.txt`.
- Coverage chỉ đo `sfboard.jobs`, ngưỡng tối thiểu 80%.
- Hypothesis khóa queue/retry properties.
- Live canary nằm ngoài gate vì có thể tiêu credit.
- Không giữ xfail cho bug đã sửa; XPASS là tín hiệu cần cập nhật test trung thực.

## Tài liệu thay thế

- [Verification](../../JOB-LIFECYCLE-README.md#verification)
- `test-job-lifecycle.command`, `pytest.ini`
