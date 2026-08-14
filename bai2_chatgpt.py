from playwright.sync_api import sync_playwright
import time

def hoc_buoc_2():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        print("1. Đang mở ChatGPT...")
        page.goto("https://chatgpt.com/")
        print("Hãy đăng nhập. Đang đợi 15 giây...")
        time.sleep(15) 

        print("2. Đang gửi yêu cầu vẽ ảnh...")
        page.locator('#prompt-textarea').fill("Hãy vẽ cho tôi một bức ảnh con mèo mặc đồ phi hành gia, phong cách hoạt hình")
        page.keyboard.press("Enter")

        # --- PHẦN MỚI CỦA BƯỚC 2 BẮT ĐẦU TỪ ĐÂY ---
        
        print("3. Đang chờ ChatGPT vẽ (Có thể mất 20-30 giây)...")
        # Thay vì chờ cứng time.sleep(), ta bảo bot: 
        # "Hãy căng mắt ra chờ đến khi nào cái ảnh có chữ 'Generated image' xuất hiện"
        # Nếu quá 60 giây không thấy thì bot sẽ tự báo lỗi Timeout.
        bo_chon_anh = page.locator("img[alt='Generated image']").last
        bo_chon_anh.wait_for(timeout=60000) 

        print("4. Đã vẽ xong! Đang tìm cách tải về...")
        # Cách 1: Trích xuất đường link URL của ảnh (để biết nó nằm ở đâu trên mạng)
        link_anh = bo_chon_anh.get_attribute("src")
        print(f"-> Đường link của ảnh là: {link_anh[:50]}...") # Chỉ in 50 ký tự cho đỡ dài

        # Cách 2: Cách ĐƠN GIẢN NHẤT để lưu ảnh về máy: Chụp ảnh màn hình đúng cái bức ảnh đó!
        # Cách này tuyệt vời ở chỗ bạn không cần quan tâm đến lỗi mạng hay cookie chặn tải ảnh.
        ten_file = "meo_phi_hanh_gia.png"
        bo_chon_anh.screenshot(path=ten_file)
        print(f"-> Đã lưu thành công ảnh vào file: {ten_file}")

        print("Hoàn thành bài học 2! Trình duyệt sẽ đóng sau 5 giây.")
        time.sleep(5)
        browser.close()

if __name__ == "__main__":
    hoc_buoc_2()
