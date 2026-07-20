"""grokpipe — CLI chạy pipeline sản xuất video (ChatGPT tạo ảnh + Grok tạo video).

Lõi (parser, state, runner, cắt frame, cổng video thủ công) chỉ dùng thư viện
chuẩn + ffmpeg. OpenCV và Playwright là tùy chọn; thiếu thì tự xuống thủ công.
"""

__version__ = "0.1.0"
