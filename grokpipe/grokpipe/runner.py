"""Bộ chạy tuần tự: resume, kiểm tra phụ thuộc, cổng duyệt tay, retry."""
from __future__ import annotations

from dataclasses import dataclass

from .models import Task, TaskType, Status
from .state import Store
from .executors import common as C
from .executors import image_chatgpt as IMG
from .executors import video_grok as VID
from .executors import extract_frame as EXT


@dataclass
class RunOptions:
    max_retry: int = 3
    manual_image: bool = False          # ép ảnh chạy thủ công (không Playwright)
    manual_video: bool = False          # ép video Grok chạy thủ công
    auto: bool = False                   # chạy thuần: bỏ mọi cổng duyệt tay
    gate_extract: bool = False          # có cổng duyệt lại sau khi chọn frame không
    from_id: str | None = None          # bắt đầu từ task này
    only: set[str] | None = None        # chỉ chạy các id/output này
    dry_run: bool = False
    headless: bool = False
    chatgpt_url: str = "https://chatgpt.com/"
    chrome_cdp: str | None = None       # nối vào Chrome thật, vd http://localhost:9222
    stop_on_fail: bool = False          # dừng hẳn khi 1 task FAILED


class Runner:
    def __init__(self, tasks: list[Task], store: Store, logger, opts: RunOptions):
        self.tasks = tasks
        self.store = store
        self.logger = logger
        self.opts = opts
        self.session: IMG.ChatGPTSession | None = None
        self._session_tried = False
        self.grok: VID.GrokSession | None = None
        self._grok_tried = False
        # 1 Playwright/CDP dùng chung cho cả ảnh + video (tránh 2 sync_playwright/tiến trình)
        self._hub_pw = None
        self._hub_browser = None
        self._hub_ctx = None
        self._hub_tried = False

    # ---- lọc phạm vi ----
    def _in_scope(self, t: Task, started: bool) -> tuple[bool, bool]:
        """(chạy_task_này, đã_bắt_đầu)."""
        if self.opts.only is not None:
            return (t.id in self.opts.only or t.output_id in self.opts.only), started
        if self.opts.from_id and not started:
            if t.id == self.opts.from_id or t.output_id == self.opts.from_id:
                return True, True
            return False, False
        return True, True

    # ---- Kết nối CDP dùng chung (1 Playwright cho cả tiến trình) ----
    def _get_hub_ctx(self):
        """Trả context CDP dùng chung, hoặc None nếu không dùng CDP / lỗi."""
        if not self.opts.chrome_cdp:
            return None
        if self._hub_tried:
            return self._hub_ctx
        self._hub_tried = True
        try:
            from playwright.sync_api import sync_playwright
            self._hub_pw = sync_playwright().start()
            self._hub_browser = self._hub_pw.chromium.connect_over_cdp(self.opts.chrome_cdp)
            self._hub_ctx = (self._hub_browser.contexts[0]
                             if self._hub_browser.contexts
                             else self._hub_browser.new_context())
            self.logger.info(f"Nối CDP dùng chung: {self.opts.chrome_cdp}")
        except Exception as e:
            self.logger.warning(f"Không nối được CDP dùng chung ({e}).")
            self._hub_ctx = None
        return self._hub_ctx

    # ---- ChatGPT session lazy ----
    def _get_session(self) -> IMG.ChatGPTSession | None:
        if self.opts.manual_image:
            return None
        if self._session_tried:
            return self.session
        self._session_tried = True
        ctx = self._get_hub_ctx() if self.opts.chrome_cdp else None
        sess = IMG.ChatGPTSession(
            user_data_dir=self.store.dir + "/.chatgpt_profile",
            logger=self.logger, headless=self.opts.headless,
            url=self.opts.chatgpt_url,
            cdp_endpoint=(None if ctx else self.opts.chrome_cdp),
            shared_ctx=ctx)
        self.session = sess if sess.start() else None
        return self.session

    # ---- Grok session lazy (chỉ khi có --chrome-cdp) ----
    def _get_grok(self) -> VID.GrokSession | None:
        if self.opts.manual_video or not self.opts.chrome_cdp:
            return None
        if self._grok_tried:
            return self.grok
        self._grok_tried = True
        ctx = self._get_hub_ctx()
        if ctx is None:
            return None
        sess = VID.GrokSession(cdp_endpoint=None, logger=self.logger,
                               shared_ctx=ctx)
        self.grok = sess if sess.start() else None
        return self.grok

    def _deps_ok(self, t: Task) -> list[str]:
        return [d for d in t.input_ids if self.store.resolve_input(d) is None]

    def _dispatch(self, t: Task) -> str:
        if t.type == TaskType.IMAGE:
            return IMG.run_image(t, self.store, self.logger, self._get_session())
        if t.type == TaskType.VIDEO:
            sf = self.store.resolve_input(t.start_frame) if t.start_frame else None
            if not sf:
                raise C.ExecutorError(f"Thiếu START_FRAME '{t.start_frame}'.")
            return VID.run_video(t, self.store, sf, self.logger,
                                 session=self._get_grok())
        if t.type == TaskType.EXTRACT:
            sv = self.store.resolve_input(t.source_video) if t.source_video else None
            if not sv:
                raise C.ExecutorError(f"Thiếu SOURCE_VIDEO '{t.source_video}'.")
            return EXT.run_extract(t, self.store, sv, self.logger)
        raise C.ExecutorError(f"Loại task lạ: {t.type}")

    def _needs_gate(self, t: Task) -> bool:
        if self.opts.auto:                 # chạy thuần: không duyệt gì
            return False
        if t.type == TaskType.IMAGE:
            return True
        if t.type == TaskType.VIDEO:
            return True
        if t.type == TaskType.EXTRACT:
            return self.opts.gate_extract  # EXTRACT cắt cố định 7.5s, mặc định không duyệt
        return True

    def run(self) -> int:
        """Trả số task FAILED."""
        started = self.opts.from_id is None and self.opts.only is None
        failed = 0
        try:
            for t in self.tasks:
                do, started = self._in_scope(t, started)
                if not do:
                    continue

                st = self.store.get(t.id, t.output_id)
                if st.status == Status.DONE.value and self.store.asset_exists(t.output_id):
                    self.logger.info(f"{t.id} {t.output_id} — DONE, bỏ qua")
                    continue

                if self.opts.dry_run:
                    deps = ", ".join(t.input_ids) or "-"
                    self.logger.info(f"[DRY] {t.id} {t.type.value:7s} -> "
                                     f"{t.output_id}  (input: {deps})")
                    continue

                missing = self._deps_ok(t)
                if missing:
                    msg = f"thiếu input: {', '.join(missing)}"
                    self.logger.error(f"{t.id} {t.output_id} — {msg} → FAILED")
                    self.store.set_status(t.id, t.output_id, Status.FAILED, note=msg)
                    failed += 1
                    if self.opts.stop_on_fail:
                        break
                    continue

                ok = self._run_one(t)
                if not ok:
                    failed += 1
                    if self.opts.stop_on_fail:
                        break
        except C.UserQuit:
            self.logger.warning("Người dùng thoát. Trạng thái đã lưu — chạy lại để tiếp tục.")
        finally:
            if self.session:
                self.session.close()
            if self.grok:
                self.grok.close()
            # đóng hub CDP dùng chung (KHÔNG tắt Chrome của user)
            try:
                if self._hub_browser:
                    self._hub_browser.close()
            except Exception:
                pass
            try:
                if self._hub_pw:
                    self._hub_pw.stop()
            except Exception:
                pass
            self.store.save()
        return failed

    def _run_one(self, t: Task) -> bool:
        self.store.set_status(t.id, t.output_id, Status.RUNNING)
        attempts = 0
        while True:
            attempts += 1
            st = self.store.get(t.id, t.output_id)
            st.attempts = attempts
            try:
                try_path = self._dispatch(t)
            except C.UserSkip:
                self.logger.warning(f"{t.id} bị bỏ qua → FAILED (phụ thuộc sẽ dừng)")
                self.store.set_status(t.id, t.output_id, Status.FAILED, note="user skip")
                return False
            except C.ExecutorError as e:
                self.logger.error(f"{t.id} lỗi executor: {e}")
                if attempts >= self.opts.max_retry:
                    self.store.set_status(t.id, t.output_id, Status.FAILED, note=str(e))
                    return False
                continue

            # cổng duyệt tay
            decision = "ok"
            if self._needs_gate(t):
                label = f"{t.type.value} {t.output_id}"
                try:
                    decision = C.human_gate(try_path, label)
                except C.UserSkip:
                    self.store.set_status(t.id, t.output_id, Status.FAILED, note="user skip")
                    return False

            if decision == "ok":
                rel = self.store.promote(try_path, t.output_id, t.ext)
                self.store.set_status(t.id, t.output_id, Status.DONE,
                                      output_path=rel, note=f"{attempts} lần")
                self.logger.info(f"{t.id} {t.output_id} — DONE ({rel})")
                return True

            # retry
            if attempts >= self.opts.max_retry:
                self.logger.error(f"{t.id} hết {self.opts.max_retry} lần retry → FAILED")
                self.store.set_status(t.id, t.output_id, Status.FAILED,
                                      note="hết retry")
                return False
            self.logger.info(f"{t.id} retry lần {attempts + 1}...")
