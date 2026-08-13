import os, glob

# Hàm backup
def backup(f):
    if os.path.exists(f) and not os.path.exists(f+".bak"):
        os.system(f"cp {f} {f}.bak")

# nv.py: xoá 7 dòng mới ở C và ND
s_nv = open("build_altar/nv.py").read()
s_nv = s_nv.replace(' "RYAN_THUONG": "đàn ông da trắng 31 tuổi, tóc nâu chải ngược, áo polo tối màu",\n', '')
s_nv = s_nv.replace(' "RYAN_CHUANBI":"đàn ông da trắng 31 tuổi, tóc nâu chải ngược, sơ mi trắng tháo cúc, không cà vạt",\n', '')
s_nv = s_nv.replace(' "VANESSA_ROBE":  "phụ nữ da trắng 28 tuổi, tóc vàng bạch kim búi cao, áo choàng lụa satin mỏng màu ngà",\n', '')
s_nv = s_nv.replace(' "SEBASTIAN_THUONG":"đàn ông da đen 52 tuổi, đầu cạo trọc, đeo kính, sơ mi xanh nhạt mở cúc",\n', '')
s_nv = s_nv.replace(' "SEBASTIAN_KHOAC":"đàn ông da đen 52 tuổi, đầu cạo trọc, đeo kính, măng tô đen ngoài vest xám",\n', '')
s_nv = s_nv.replace(' "JULIAN_NHA": "đàn ông da đen 41 tuổi, ria mép mỏng, áo len đen cổ lọ",\n', '')
s_nv = s_nv.replace(' "JULIAN_COMLE":"đàn ông da đen 41 tuổi, ria mép mỏng, vest xám nhạt không cà vạt",\n', '')
s_nv = s_nv.replace(' "RYAN_THUONG": ["REF_RYAN_PORTRAIT", "REF_RYAN_THUONG_FULL"],\n', '')
s_nv = s_nv.replace(' "RYAN_CHUANBI":["REF_RYAN_PORTRAIT", "REF_RYAN_CHUANBI_FULL"],\n', '')
s_nv = s_nv.replace(' "VANESSA_ROBE":  ["REF_VANESSA_PORTRAIT", "REF_VANESSA_ROBE_FULL"],\n', '')
s_nv = s_nv.replace(' "SEBASTIAN_THUONG":["REF_SEBASTIAN_PORTRAIT", "REF_SEBASTIAN_THUONG_FULL"],\n', '')
s_nv = s_nv.replace(' "SEBASTIAN_KHOAC":["REF_SEBASTIAN_PORTRAIT", "REF_SEBASTIAN_KHOAC_FULL"],\n', '')
s_nv = s_nv.replace(' "JULIAN_NHA": ["REF_JULIAN_PORTRAIT", "REF_JULIAN_NHA_FULL"],\n', '')
s_nv = s_nv.replace(' "JULIAN_COMLE":["REF_JULIAN_PORTRAIT", "REF_JULIAN_COMLE_FULL"],\n', '')
open("build_altar/nv.py", "w").write(s_nv)

# ref_nv.py: xoá 7 thẻ mới
import re
s_ref = open("build_altar/ref_nv.py").read()
# Xoá khối 7 thẻ vừa thêm
s_ref = re.sub(r' \("REF_JULIAN_NHA_FULL.*?REF_VANESSA_PORTRAIT"\),\n', '', s_ref, flags=re.DOTALL)
open("build_altar/ref_nv.py", "w").write(s_ref)

# Phục hồi s07, s10, s17 (các file kia ta chưa sửa)
s07 = open("build_altar/s07.py").read()
s07 = s07.replace('JULIAN_NHA', 'JULIAN')
open("build_altar/s07.py", "w").write(s07)

s10 = open("build_altar/s10.py").read()
s10 = s10.replace('RYAN_THUONG', 'RYAN_COMLE')
open("build_altar/s10.py", "w").write(s10)

s17 = open("build_altar/s17.py").read()
s17 = s17.replace('RYAN_CHUANBI', 'RYAN_COMLE')
s17 = s17.replace('VANESSA_ROBE', 'VANESSA_NGAY')
open("build_altar/s17.py", "w").write(s17)

os.system("python3 build_altar/build.py")
print("Done")
