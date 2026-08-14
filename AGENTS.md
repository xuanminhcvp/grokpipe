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
