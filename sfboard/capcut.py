#!/usr/bin/env python3
"""
Xuất project draft CapCut từ danh sách video đã duyệt.

Cách làm: nhân bản một draft CapCut có sẵn làm KHUÔN (giữ nguyên mọi cấu hình
nội bộ mà CapCut cần), rồi thay toàn bộ track video bằng danh sách video của phim,
xếp nối tiếp theo đúng thứ tự kịch bản.

Dùng:
    from capcut import export_draft
    export_draft(["/path/a.mp4", "/path/b.mp4"], "TEN-PROJECT")
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import time
import uuid

DRAFT_ROOT = os.path.expanduser("~/Movies/CapCut/User Data/Projects/com.lveditor.draft")
US = 1_000_000  # micro giây


def _uid() -> str:
    return str(uuid.uuid4()).upper()


def probe(path: str) -> tuple[int, int, int]:
    """(duration_us, width, height) — cần ffprobe."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams",
             "-select_streams", "v:0", path],
            capture_output=True, text=True, timeout=30).stdout
        s = json.loads(out)["streams"][0]
        dur = int(float(s.get("duration", 10.0)) * US)
        return dur, int(s.get("width", 1280)), int(s.get("height", 720))
    except Exception:
        return 10 * US, 1280, 720


def find_template() -> str | None:
    """Chọn một draft có sẵn làm khuôn: ưu tiên draft có track video nhiều segment."""
    if not os.path.isdir(DRAFT_ROOT):
        return None
    best, best_n = None, -1
    for name in os.listdir(DRAFT_ROOT):
        d = os.path.join(DRAFT_ROOT, name)
        info = os.path.join(d, "draft_info.json")
        if not os.path.isfile(info):
            continue
        try:
            with open(info, "r", encoding="utf-8") as f:
                j = json.load(f)
            n = sum(len(t.get("segments", [])) for t in j.get("tracks", []) if t.get("type") == "video")
            if n > best_n:
                best, best_n = d, n
        except Exception:
            continue
    return best if best_n > 0 else None


def _clone_extra_materials(materials: dict, refs: list[str]) -> list[str]:
    """Nhân bản các material phụ (speed, canvas, ...) với id mới, trả về danh sách ref mới."""
    new_refs = []
    for rid in refs:
        found = None
        for key, arr in materials.items():
            if not isinstance(arr, list):
                continue
            for m in arr:
                if isinstance(m, dict) and m.get("id") == rid:
                    found = (key, m)
                    break
            if found:
                break
        if not found:
            continue
        key, m = found
        c = copy.deepcopy(m)
        c["id"] = _uid()
        materials[key].append(c)
        new_refs.append(c["id"])
    return new_refs


def export_draft(video_paths: list[str], project_name: str,
                 template: str | None = None) -> str:
    """Tạo draft mới trong thư mục CapCut. Trả về đường dẫn draft."""
    if not video_paths:
        raise RuntimeError("Không có video nào để xuất")
    tpl = template or find_template()
    if not tpl:
        raise RuntimeError("Không tìm thấy draft CapCut nào để làm khuôn. "
                           "Hãy tạo tay một project bất kỳ trong CapCut rồi thử lại.")

    dst = os.path.join(DRAFT_ROOT, project_name)
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(tpl, dst, ignore=shutil.ignore_patterns("draft_info.json.bak", "*.tmp"))

    info_path = os.path.join(dst, "draft_info.json")
    with open(info_path, "r", encoding="utf-8") as f:
        j = json.load(f)

    vtracks = [t for t in j.get("tracks", []) if t.get("type") == "video"]
    if not vtracks or not vtracks[0].get("segments"):
        raise RuntimeError("Khuôn không có track video hợp lệ")
    tpl_seg = copy.deepcopy(vtracks[0]["segments"][0])
    tpl_mat = None
    for m in j["materials"].get("videos", []):
        if m.get("id") == tpl_seg.get("material_id"):
            tpl_mat = copy.deepcopy(m)
            break
    if tpl_mat is None:
        tpl_mat = copy.deepcopy(j["materials"]["videos"][0])

    # dọn: chỉ giữ 1 track video, bỏ mọi segment cũ
    j["materials"]["videos"] = []
    new_track = copy.deepcopy(vtracks[0])
    new_track["id"] = _uid()
    new_track["segments"] = []
    j["tracks"] = [new_track]

    cursor = 0
    for i, path in enumerate(video_paths):
        path = os.path.abspath(path)
        dur, w, h = probe(path)

        mat = copy.deepcopy(tpl_mat)
        mat.update({
            "id": _uid(),
            "local_material_id": _uid(),
            "material_id": "",
            "path": path,
            "media_path": "",
            "material_name": os.path.basename(path),
            "duration": dur,
            "width": w,
            "height": h,
            "has_audio": True,
            "source_platform": 0,
            "is_ai_generate_content": False,
            "aigc_type": "none",
            "aigc_history_id": "",
            "aigc_item_id": "",
            "material_url": "",
            "request_id": "",
        })
        j["materials"]["videos"].append(mat)

        seg = copy.deepcopy(tpl_seg)
        seg["id"] = _uid()
        seg["material_id"] = mat["id"]
        seg["target_timerange"] = {"start": cursor, "duration": dur}
        seg["source_timerange"] = {"start": 0, "duration": dur}
        seg["render_index"] = 0
        seg["track_render_index"] = 0
        seg["speed"] = 1.0
        seg["volume"] = 1.0
        seg["visible"] = True
        seg["extra_material_refs"] = _clone_extra_materials(
            j["materials"], tpl_seg.get("extra_material_refs", []))
        new_track["segments"].append(seg)
        cursor += dur

    j["duration"] = cursor
    j["id"] = _uid()
    j["name"] = project_name
    now = int(time.time() * US)
    j["create_time"] = now
    j["update_time"] = now
    with open(info_path, "w", encoding="utf-8") as f:
        json.dump(j, f, ensure_ascii=False)

    # draft_meta_info.json
    meta_path = os.path.join(dst, "draft_meta_info.json")
    if os.path.isfile(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            m = json.load(f)
        m["draft_id"] = j["id"]
        m["draft_name"] = project_name
        m["draft_fold_path"] = dst
        m["draft_root_path"] = DRAFT_ROOT
        m["tm_draft_create"] = now
        m["tm_draft_modified"] = now
        m["draft_removable_storage_device"] = ""
        m["draft_timeline_materials_size_"] = 0
        if isinstance(m.get("draft_materials"), list):
            for grp in m["draft_materials"]:
                if isinstance(grp, dict):
                    grp["value"] = []
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False)

    for junk in ("draft_cover.jpg",):
        p = os.path.join(dst, junk)
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass

    return dst


if __name__ == "__main__":
    import sys
    print(export_draft(sys.argv[2:], sys.argv[1]))
