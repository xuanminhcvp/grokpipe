#!/bin/bash
# Quay về một bản đã lưu.
#   ./quay-lai.sh              -> liệt kê các bản đang có
#   ./quay-lai.sh 2026-07-20   -> quay về bản đó
#
# Bản HIỆN TẠI luôn được chụp lại trước khi ghi đè, nên quay lại không mất gì.
set -euo pipefail

ROOT="/Users/may1/Desktop/grokpipe"
PROJ="PIPELINE-8DOLLARS.project"
SNAP="$ROOT/$PROJ/.snapshots"
cd "$ROOT"

# ── không có tham số: liệt kê ───────────────────────────────────────────────
if [ $# -eq 0 ]; then
  echo "CÁC BẢN ĐANG GIỮ:"
  printf "  %-22s %-9s %s\n" "bản" "video" "ghi chú"
  for T in "$SNAP"/*/; do
    [ -d "$T" ] || continue
    TEN=$(basename "$T")
    SO=$(ls -1 "$T/videos" 2>/dev/null | grep -c '\.mp4$' || echo 0)
    printf "  %-22s %-9s %s\n" "$TEN" "$SO clip" "$(cat "$T/.ghi-chu" 2>/dev/null || echo '-')"
  done
  echo
  echo "Quay về:  ./quay-lai.sh <tên bản>"
  exit 0
fi

BAN="$1"
NGUON="$SNAP/$BAN"
[ -d "$NGUON" ] || { echo "✗ không có bản '$BAN'. Chạy ./quay-lai.sh để xem danh sách."; exit 1; }

echo "Sắp quay về bản: $BAN — $(cat "$NGUON/.ghi-chu" 2>/dev/null || echo '-')"
read -p "Chắc chưa? (gõ 'co' để làm) " OK
[ "$OK" = "co" ] || { echo "đã hủy."; exit 0; }

# ── 1. chụp bản hiện tại trước khi ghi đè ───────────────────────────────────
echo "· chụp bản hiện tại để phòng khi cần quay ngược..."
"$ROOT/luu-ban.sh" "tự động lưu trước khi quay về $BAN" >/dev/null
echo "  (đã lưu)"

# ── 2. khôi phục media ──────────────────────────────────────────────────────
for TH in videos assets versions; do
  if [ -d "$NGUON/$TH" ]; then
    rm -rf "$ROOT/$PROJ/$TH"
    cp -c -R "$NGUON/$TH" "$ROOT/$PROJ/$TH"
  fi
done
echo "· media: đã khôi phục"

# ── 3. khôi phục sf-board.json ──────────────────────────────────────────────
TAG="ban-$BAN"
if git rev-parse "$TAG" >/dev/null 2>&1; then
  git checkout "$TAG" -- "$PROJ/sf-board.json" 2>/dev/null && echo "· sf-board.json: lấy từ git tag $TAG"
elif [ -f "$NGUON/sf-board.json" ]; then
  cp -c "$NGUON/sf-board.json" "$ROOT/$PROJ/sf-board.json" && echo "· sf-board.json: lấy từ snapshot"
fi

echo
echo "✓ đã quay về bản $BAN"
echo "  Khởi động lại board để nạp dữ liệu mới:"
echo "  python3 -u sfboard/sfboard.py $PROJ --port 8778"
