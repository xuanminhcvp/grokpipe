from playwright.sync_api import sync_playwright
import time

def hoc_buoc_3():
    # Danh sách các câu lệnh chúng ta muốn vẽ liên tục
    danh_sach_yeu_cau = [
        "Vẽ một quả táo màu xanh lơ lửng giữa vũ trụ",
        "Vẽ một chú chó robot đang uống cà phê",
        "Vẽ một toà lâu đài bằng kẹo ngọt"
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        print("1. Đang mở ChatGPT và chờ 15s để bạn chuẩn bị...")
        page.goto("https://chatgpt.com/")
        time.sleep(15) 

        print(f"2. Bắt đầu vòng lặp vẽ {len(danh_sach_yeu_cau)} bức ảnh!")
        
        # --- BƯỚC 3: DÙNG VÒNG LẶP FOR ĐỂ DUYỆT QUA TỪNG YÊU CẦU ---
        for so_thu_tu, yeu_cau in enumerate(danh_sach_yeu_cau):
            print(f"\n--- Đang xử lý ảnh thứ {so_thu_tu + 1}: {yeu_cau} ---")
            
            try:
                # Gõ chữ và gửi
                page.locator('#prompt-textarea').fill(f"Hãy vẽ ảnh: {yeu_cau}")
                page.keyboard.press("Enter")

                print("   Đang chờ ChatGPT vẽ...")
                
                # Tìm ảnh ở dưới cùng (last) và đợi tối đa 60s
                bo_chon_anh = page.locator("img[alt='Generated image']").last
                bo_chon_anh.wait_for(timeout=60000) 

                # Đặt tên file theo số thứ tự để không bị ghi đè (ví dụ: ket_qua_1.png)
                ten_file = f"ket_qua_{so_thu_tu + 1}.png"
                
                # Chụp lại bức ảnh vừa vẽ
                bo_chon_anh.screenshot(path=ten_file)
                print(f"   -> Thành công! Đã lưu: {ten_file}")

                # Tạm nghỉ 3 giây trước khi bắt nó vẽ tiếp, để web khỏi báo lỗi "spam"
                time.sleep(3)

            # --- THÊM CHỐNG LỖI (Try... Except) ---
            except Exception as e:
                # Lỡ mạng đứt hoặc bot không vẽ được ảnh này, nó sẽ nhảy vào đây
                # In ra lỗi, và QUAN TRỌNG NHẤT: Vẫn chạy tiếp vòng lặp cho các bức ảnh sau!
                print(f"   -> BỊ LỖI ở bức ảnh số {so_thu_tu + 1}. Bỏ qua để vẽ bức tiếp theo.")
                print(f"   -> Chi tiết lỗi: {str(e)[:50]}...")
                
                # Phải load lại trang để xoá kẹt, nếu không lệnh sau sẽ bị dính chung
                page.goto("https://chatgpt.com/") 
                time.sleep(5)

        print("\nHoàn thành! Đã chạy xong toàn bộ danh sách.")
        browser.close()

if __name__ == "__main__":
    hoc_buoc_3()
