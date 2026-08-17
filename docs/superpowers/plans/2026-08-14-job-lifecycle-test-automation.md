# Hồ sơ lịch sử — lifecycle test automation

> Hoàn tất ngày 2026-08-14; gate hiện hành nằm ở root repo.

## Mục tiêu khi tạo

Tạo một lệnh local/CI cô lập để phát hiện regression lifecycle và compile lỗi.

## Kết quả

- `test-job-lifecycle.command` chạy lifecycle, runtime bug và executor suites.
- Coverage gate áp dụng cho `sfboard.jobs` với ngưỡng 80%.
- Compile gate kiểm tra các module production chính.
- Hypothesis được dùng cho queue/retry properties.

## Nguồn hiện hành

```bash
./test-job-lifecycle.command
```

Xem [verification hiện tại](../../JOB-LIFECYCLE-README.md#verification). Các
con số test/xfail trong plan gốc không còn giá trị.
