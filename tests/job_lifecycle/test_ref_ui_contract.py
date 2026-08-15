"""Contract nguồn cho phân nhóm và điều hướng REF.

Không mở browser/provider. Visual QA được làm riêng sau khi syntax và lifecycle
đã xanh; file này khóa các affordance dễ bị mất khi refactor giao diện.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
JS = (ROOT / "sfboard/ui/board.js").read_text(encoding="utf-8")
CSS = (ROOT / "sfboard/ui/board.css").read_text(encoding="utf-8")


def test_ref_co_ba_section_va_sidebar_con():
    assert "function chiaRef(" in JS
    assert "startsWith('REF_PROP_')" in JS
    assert "_(PORTRAIT|FULL)" in JS
    for anchor in ("ref-nhan-vat", "ref-dao-cu", "ref-boi-canh"):
        assert anchor in JS
    assert 'class="refsub"' in JS
    assert 'type="button"' in JS
    assert "aria-label=" in JS
    assert "onkeydown=" in JS


def test_ref_sidebar_co_focus_va_ton_trong_reduced_motion():
    assert "#snav .refsub:focus-visible" in CSS
    assert "prefers-reduced-motion: reduce" in JS


def test_ngan_hang_doi_dang_dong_khong_tao_cuon_ngang_responsive():
    assert "#qdrawer:not(.on) {\n  display: none" in CSS


def test_header_ref_duoc_xuong_hang_duoi_breakpoint_sidebar():
    assert "  .scene-h {\n    flex-wrap: wrap" in CSS
    assert "  .scene-h>span[style]" in CSS
