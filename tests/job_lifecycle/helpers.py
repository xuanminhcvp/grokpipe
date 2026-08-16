from __future__ import annotations

import ast
import importlib
import importlib.util
import io
import json
import queue
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SFBOARD_DIR = ROOT / "sfboard"


def load_hangdoi():
    path = str(SFBOARD_DIR)
    if path not in sys.path:
        sys.path.insert(0, path)
    return importlib.import_module("hangdoi")


def load_sfboard():
    path = str(SFBOARD_DIR)
    if path not in sys.path:
        sys.path.insert(0, path)
    module_name = "_sfboard_runtime_for_tests"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, SFBOARD_DIR / "sfboard.py")
    if spec is None or spec.loader is None:
        raise AssertionError("Không tạo được import spec cho sfboard.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def reset_legacy_state(module) -> None:
    if hasattr(module, "_init_job_shadow"):
        module._init_job_shadow("legacy")
    observer_owner = getattr(module, "hangdoi", module)
    if hasattr(observer_owner, "gan_shadow_observer"):
        observer_owner.gan_shadow_observer(None)
    for name in (
        "JOBS", "VET", "DA_HUY", "DUNG_RIENG", "TAY_SF", "CHO_RIENG", "_HOAN"
    ):
        value = getattr(module, name, None)
        if value is not None:
            value.clear()
    if hasattr(module, "GEN"):
        module.GEN["dung"] = 0
    for name in ("IMG_QUEUE", "VID_QUEUE"):
        q = getattr(module, name, None)
        if q is None:
            continue
        while True:
            try:
                q.get_nowait()
                q.task_done()
            except queue.Empty:
                break


def function_source(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"Không tìm thấy function {name} trong {path}")


class CaptureHandlerMixin:
    def prepare(self, path: str, raw: bytes = b"") -> None:
        self.path = path
        self.headers = {"Content-Length": str(len(raw))}
        self.rfile = io.BytesIO(raw)
        self.captured = None

    def _json(self, obj, code=200):
        self.captured = (code, json.loads(json.dumps(obj, ensure_ascii=False)))


class FakeBoard:
    """Board giả cho test HTTP.

    Mặc định rỗng y như trước. Truyền `scenes`/`files` khi cần dựng shot có
    prompt + start frame để `/api/genvideo` và `/api/video-lo` đi hết đường
    validate mà KHÔNG chạm provider.
    """

    path = __file__

    def __init__(self, scenes=None, files=()):
        self._scenes = scenes or []
        self._files = set(files)

    def read(self):
        return {"scenes": json.loads(json.dumps(self._scenes))}

    def get_sf(self, sf_id, data=None):
        # `data` là tham số tuỳ chọn của bản thật — `/api/tao-lo` truyền vào để
        # khỏi đọc lại file board cho từng SF.
        for scene in self._scenes:
            for sf in scene.get("sfs", []):
                if sf.get("id") == sf_id:
                    return dict(sf)
        return {"id": sf_id}

    def get_shot(self, shot_id):
        for scene in self._scenes:
            for shot in scene.get("shots", []):
                if shot.get("id") == shot_id:
                    return (dict(shot), dict(scene))
        return (None, None)

    def find_file(self, asset_id):
        return f"/fake/{asset_id}.png" if asset_id in self._files else None

    def video_file(self, shot_id):
        return None


def make_handler(module, path: str, raw: bytes = b""):
    cls = type("CaptureHandler", (CaptureHandlerMixin, module.Handler), {})
    handler = object.__new__(cls)
    handler.prepare(path, raw)
    return handler
