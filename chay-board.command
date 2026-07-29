#!/bin/bash
# Mở SF Board cho dự án phim 8 DOLLARS.
# Dùng đường dẫn TUYỆT ĐỐI để không bao giờ mở nhầm dự án trùng tên ở thư mục khác.
# Cổng lấy từ board.json trong thư mục dự án (8781).
ROOT="/Users/may1/Desktop/grokpipe"
PROJ="$ROOT/PIPELINE-8DOLLARS.project"
PORT=$(python3 -c "import json;print(json.load(open('$PROJ/board.json'))['port'])")

if lsof -nP -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Board đã chạy sẵn ở cổng $PORT"
else
  pkill -f "sfboard.py $PROJ" 2>/dev/null
  nohup python3 -u "$ROOT/sfboard/sfboard.py" "$PROJ" > /tmp/board-8dollars.log 2>&1 &
  disown
  sleep 3
fi
echo "→ http://localhost:$PORT"
open "http://localhost:$PORT"
