from playwright.sync_api import sync_playwright
import time

def hoc_buoc_1():
    # 1. Khởi động Playwright
    with sync_playwright() as p:
        # 2. Mở trình duyệt Chrome (headless=False để nhìn thấy nó thao tác)
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        # 3. Truy cập vào ChatGPT
        print("Đang mở trang ChatGPT...")
        page.goto("https://chatgpt.com/")

        # Để trống thời gian để bạn tự tay đăng nhập (nếu cần)
        print("Hãy đăng nhập. Đang đợi 15 giây...")
        time.sleep(15) 

        # 4. Tìm ô nhập chữ và gõ câu lệnh
        print("Đang gõ câu lệnh...")
        # Lệnh này tìm cái ô nhập chữ có id là "prompt-textarea"
        o_soan_thao = page.locator('#prompt-textarea')
        
        # Điền chữ vào ô
        o_soan_thao.fill("Hãy vẽ cho tôi một bức ảnh con mèo mặc đồ phi hành gia")
        
        # 5. Bấm phím Enter để gửi
        print("Đã bấm Enter gửi đi!")
        page.keyboard.press("Enter")

        # 6. Đợi 10 giây để xem kết quả trước khi đóng trình duyệt
        print("Giữ màn hình 10 giây để xem thành quả...")
        time.sleep(10)

        # Đóng trình duyệt
        browser.close()
        print("Hoàn thành bài học 1!")

if __name__ == "__main__":
    hoc_buoc_1()
