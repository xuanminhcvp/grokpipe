"""Đọc file pipeline .txt -> danh sách Task theo thứ tự."""
from __future__ import annotations

import re

from .models import Task, TaskType

# === [T001] IMAGE -> REF_ANDREA_PORTRAIT | chân dung Andrea ===
_HEADER = re.compile(
    r"^===\s*\[(?P<id>T\d+)\]\s+(?P<type>IMAGE|VIDEO|EXTRACT)\s*->\s*"
    r"(?P<out>\S+)\s*\|\s*(?P<name>.*?)\s*===\s*$"
)
_PROMPT_START = "--- PROMPT ---"
_PROMPT_END = "--- HẾT PROMPT ---"

# tên trường hợp lệ (chữ HOA, có thể chứa dấu tiếng Việt), không khoảng trắng
_FIELD = re.compile(r"^(?P<key>[^\s:]+)\s*:\s*(?P<val>.*)$")


def _is_none(v: str) -> bool:
    return not v or v.strip().upper() == "NONE"


def _split_list(v: str) -> list[str]:
    if _is_none(v):
        return []
    return [x.strip() for x in v.split(",") if x.strip() and x.strip().upper() != "NONE"]


def _parse_duration(v: str) -> float:
    if _is_none(v):
        return 10.0
    m = re.search(r"(\d+(?:\.\d+)?)", v)
    return float(m.group(1)) if m else 10.0


class ParseError(Exception):
    pass


def parse_pipeline(path: str) -> list[Task]:
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    tasks: list[Task] = []
    cur: Task | None = None
    in_prompt = False
    prompt_lines: list[str] = []
    seen_ids: set[str] = set()
    seen_out: set[str] = set()

    for lineno, raw in enumerate(lines, 1):
        line = raw.rstrip("\n")

        # --- đang trong khối prompt ---
        if in_prompt:
            if line.strip() == _PROMPT_END:
                if cur is not None:
                    cur.prompt = "\n".join(prompt_lines).strip("\n")
                in_prompt = False
                prompt_lines = []
            else:
                prompt_lines.append(line)
            continue

        # --- header task mới ---
        m = _HEADER.match(line)
        if m:
            cur = Task(
                id=m.group("id"),
                type=TaskType(m.group("type")),
                output_id=m.group("out"),
                name=m.group("name").strip(),
            )
            if cur.id in seen_ids:
                raise ParseError(f"Dòng {lineno}: TASK_ID trùng: {cur.id}")
            if cur.output_id in seen_out:
                raise ParseError(f"Dòng {lineno}: OUTPUT_ID trùng: {cur.output_id}")
            seen_ids.add(cur.id)
            seen_out.add(cur.output_id)
            tasks.append(cur)
            continue

        if cur is None:
            continue  # banner / mục lục ngoài mọi block -> bỏ qua

        if line.strip() == _PROMPT_START:
            in_prompt = True
            prompt_lines = []
            continue

        # --- dòng KEY : value ---
        fm = _FIELD.match(line.strip())
        if not fm:
            continue
        key = fm.group("key").strip()
        val = fm.group("val").strip()
        if key != key.upper():   # chỉ nhận key viết HOA
            continue
        cur.raw_fields[key] = val

        if key == "BASE_IMAGE":
            cur.base_image = None if _is_none(val) else val
        elif key == "REF_IMAGES":
            cur.ref_images = _split_list(val)
        elif key == "START_FRAME":
            cur.start_frame = None if _is_none(val) else val
        elif key == "DURATION":
            cur.duration_s = _parse_duration(val)
        elif key == "SRT_RANGE":
            cur.srt_range = None if _is_none(val) else val
        elif key == "SOURCE_VIDEO":
            cur.source_video = None if _is_none(val) else val
        elif key.startswith("FRAME_"):   # FRAME_CẦN_CÓ (có dấu)
            cur.frame_need = None if _is_none(val) else val

    if in_prompt and cur is not None:
        cur.prompt = "\n".join(prompt_lines).strip("\n")

    if not tasks:
        raise ParseError("Không tìm thấy task nào (không có dòng '=== [Txxx] ... ===').")

    _validate_refs(tasks)
    return tasks


def _validate_refs(tasks: list[Task]) -> None:
    """Cảnh báo sớm: mọi input_id phải là output_id của một task đứng TRƯỚC."""
    produced: dict[str, int] = {}
    order = {t.id: i for i, t in enumerate(tasks)}
    for i, t in enumerate(tasks):
        for dep in t.input_ids:
            if dep not in {tt.output_id for tt in tasks}:
                raise ParseError(
                    f"{t.id}: input '{dep}' không do task nào tạo ra."
                )
        produced[t.output_id] = i
    # kiểm tra thứ tự (input phải xuất hiện trước)
    out_index = {t.output_id: i for i, t in enumerate(tasks)}
    for i, t in enumerate(tasks):
        for dep in t.input_ids:
            if out_index[dep] > i:
                raise ParseError(
                    f"{t.id} cần '{dep}' nhưng nó được tạo sau (sai thứ tự tuần tự)."
                )
