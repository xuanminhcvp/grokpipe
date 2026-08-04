#!/usr/bin/env python3
"""Liệt kê đạo cụ được THOẠI nhắc tới, quét toàn bộ kịch bản.

    python3 sfboard/liet-ke-dao-cu.py PIPELINE-RUTHS-HOUSE.project

Xếp theo số scene xuất hiện — món nằm ở nhiều scene là món gieo-trả, quan trọng nhất
và dễ sót nhất vì trong từng scene riêng lẻ nó không nổi bật. Đánh dấu ★ cho món gắn
với LỆNH CẤM · BÍ MẬT · THÓI QUEN nhân vật — ba dấu hiệu của vật chốt cốt truyện.

Đây là công cụ GỢI Ý, không phải quyết định: đọc lại danh sách rồi tự chốt món nào cần
`REF_PROP_`. Xem tiêu chí ở .claude/skills/skills-film/references/2-fullbody.md
"""
import json
import os
import re
import sys
from collections import defaultdict

# danh từ vật thể hay làm đạo cụ trong drama — nới rộng, để người lọc lại
NOUN = r"""photograph|photo|picture|portrait|painting|frame|drawing|sketchbook|sketch|crayon
|ring|necklace|chain|locket|watch|bracelet|apron|dress|uniform|cardigan|coat|crown
|letter|envelope|document|will|contract|checkbook|check|card|paper|note|file|report
|case|bag|suitcase|box|drawer|key|lock|pill|bottle|medication|prescription|syringe
|phone|camera|book|album|toy|doll|blanket|flower|rose|garden|piano|violin|glass|cup"""
NOUN = NOUN.replace("\n", "")
# bỏ các từ chỉ là địa điểm/bộ phận nhà, không phải đạo cụ cầm được
BO = {"garden", "drawer", "lock", "glass"}

# ba dấu hiệu của vật chốt
DAU = [
    (r"don't touch|if you touch|you're finished|never touch|stay away from", "LỆNH CẤM"),
    (r"won't let anyone see|nobody's seen|hidden|face-down|face down|secret|locked", "BÍ MẬT"),
    (r"you twist|you always|every day|still have|keeps? a|kept", "THÓI QUEN"),
]


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    path = os.path.join(sys.argv[1], "sf-board.json")
    if not os.path.exists(path):
        sys.exit(f"không thấy {path}")
    data = json.load(open(path, encoding="utf-8"))

    hit = defaultdict(lambda: {"scenes": set(), "dong": [], "dau": set()})
    for sc in data["scenes"]:
        for line in (sc.get("script") or "").split("\n"):
            low = line.lower()
            for m in set(x.lower() for x in re.findall(rf"\b(?:{NOUN})\b", low)):
                h = hit[m]
                h["scenes"].add(sc["id"])
                if len(h["dong"]) < 3:
                    h["dong"].append(f"{sc['id']}: {line.strip()[:104]}")
                for pat, ten in DAU:
                    if re.search(pat, low):
                        h["dau"].add(ten)

    for b in BO:
        hit.pop(b, None)
    xep = sorted(hit.items(), key=lambda kv: (-len(kv[1]["scenes"]), kv[0]))
    print(f"\n{len(xep)} danh từ vật thể xuất hiện trong thoại — xếp theo số scene\n")
    for tu, h in xep:
        n = len(h["scenes"])
        sao = "★" if (n >= 2 or h["dau"]) else " "
        dau = f"  [{' · '.join(sorted(h['dau']))}]" if h["dau"] else ""
        sc = ", ".join(sorted(h["scenes"], key=lambda s: (len(s), s)))
        print(f"{sao} {tu:14} {n} scene  ({sc}){dau}")
        if sao == "★":
            for d in h["dong"]:
                print(f"      {d}")
            print()

    print("─" * 70)
    print("★ = ứng viên REF_PROP_ : ở ≥2 scene, hoặc gắn lệnh cấm/bí mật/thói quen.")
    print("Vẫn phải đọc tay: một danh từ có thể là NHIỀU vật khác nhau (ba bức tranh")
    print("khác nhau của cùng một đứa trẻ) — mỗi vật một ảnh riêng.")


if __name__ == "__main__":
    main()
