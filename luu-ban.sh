#!/bin/bash
# Lưu một bản của dự án phim.
#   ./luu-ban.sh                 -> bản tự động (chạy theo lịch mỗi tối)
#   ./luu-ban.sh "ghi chú"       -> bản gõ tay, nên dùng TRƯỚC khi thử hướng mới
#
# Chữ (prompt/kịch bản) -> git commit + tag.  Media -> APFS clone, gần như không tốn đĩa.
set -euo pipefail

ROOT="/Users/may1/Desktop/grokpipe"
PROJ="PIPELINE-8DOLLARS.project"
SNAP="$ROOT/$PROJ/.snapshots"
GIU_NGAY=30
NGAY=$(date +%Y-%m-%d)
GIO=$(date +%H%M)
GHICHU="${1:-bản tự động}"

cd "$ROOT"

# ── 1. phần chữ vào git ─────────────────────────────────────────────────────
git add -A "$PROJ"/*.json "$PROJ"/*.md .claude/skills sfboard/*.py sfboard/*.md .gitignore 2>/dev/null || true

if git diff --cached --quiet 2>/dev/null; then
  echo "· chữ: không có gì đổi từ lần lưu trước"
  CO_COMMIT=0
else
  git commit -q -m "bản $NGAY $GIO — $GHICHU"
  echo "· chữ: đã commit ($(git diff --name-only HEAD~1 HEAD 2>/dev/null | wc -l | tr -d ' ') file đổi)"
  CO_COMMIT=1
fi

# tag: mỗi ngày một tag; gõ tay nhiều lần trong ngày thì thêm giờ
TAG="ban-$NGAY"
if git rev-parse "$TAG" >/dev/null 2>&1; then
  TAG="ban-$NGAY-$GIO"
fi
git tag -f "$TAG" -m "$GHICHU" >/dev/null 2>&1 || true
echo "· tag: $TAG"

# ── 2. media clone (copy-on-write, tức thì, không tốn đĩa) ───────────────────
DICH="$SNAP/$NGAY"
[ -d "$DICH" ] && DICH="$SNAP/$NGAY-$GIO"
mkdir -p "$DICH"
for TH in videos assets versions; do
  [ -d "$ROOT/$PROJ/$TH" ] && cp -c -R "$ROOT/$PROJ/$TH" "$DICH/$TH" 2>/dev/null || true
done
cp -c "$ROOT/$PROJ/sf-board.json" "$DICH/sf-board.json" 2>/dev/null || true
echo "$GHICHU" > "$DICH/.ghi-chu"
echo "· media: đã chụp -> .snapshots/$(basename "$DICH")"

# ── 3. dọn snapshot quá hạn ─────────────────────────────────────────────────
XOA=0
for CU in "$SNAP"/*/; do
  [ -d "$CU" ] || continue
  TEN=$(basename "$CU")
  NGAYCU=$(echo "$TEN" | cut -d'-' -f1-3)
  TUOI=$(( ( $(date +%s) - $(date -j -f "%Y-%m-%d" "$NGAYCU" +%s 2>/dev/null || date +%s) ) / 86400 ))
  if [ "$TUOI" -gt "$GIU_NGAY" ]; then
    rm -rf "$CU"; XOA=$((XOA+1))
  fi
done
[ "$XOA" -gt 0 ] && echo "· dọn: xóa $XOA bản quá $GIU_NGAY ngày"

SO=$(ls -1d "$SNAP"/*/ 2>/dev/null | wc -l | tr -d ' ')
echo "✓ xong — đang giữ $SO bản · đĩa trống $(df -h "$ROOT" | tail -1 | awk '{print $4}')"
