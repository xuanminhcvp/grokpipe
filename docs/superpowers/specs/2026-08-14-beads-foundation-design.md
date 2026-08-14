# Beads Foundation Design

Ngày: 2026-08-14
Trạng thái: Thiết kế hội thoại đã duyệt, chờ người dùng duyệt written spec

## Mục tiêu

Đưa [Beads](https://github.com/gastownhall/beads) vào `grokpipe` làm bộ nhớ và
issue graph bền vững dùng chung cho Codex và Claude Code. AI phải tìm được việc
sẵn sàng, dependency, lịch sử và quyết định cũ mà không phải đọc lại toàn bộ chat
hoặc tạo thêm Markdown TODO rời rạc.

Phase này chỉ xây nền quản lý công việc. Nó không sửa runtime, không tự bắt
exception và không tự sửa code.

## Hiện trạng

- Máy chưa có executable `bd` hoặc `beads` trong `PATH`.
- Repo chưa có `.beads` workspace hay Beads integration.
- `AGENTS.md` và `CLAUDE.md` đã chứa hướng dẫn riêng quan trọng; không được ghi đè.
- Năm ambiguity lifecycle đã có executable `expectedFailure` nhưng chưa có issue
  graph để AI claim, liên kết dependency và ghi lại tiến độ.
- Main working tree đang có thay đổi riêng của người dùng; triển khai phải dùng
  worktree cô lập và chỉ merge file đã xác định.

## Không nằm trong phạm vi

- Không cấu hình Dolt remote hoặc `bd dolt push/pull`.
- Không đồng bộ bug ra cloud hay GitHub Issues.
- Không cài Beads MCP; Codex và Claude Code đều có shell và integration chính chủ.
- Không cho AI tự commit, push, merge hoặc chạy provider.
- Không thay thế regression tests, tài liệu kiến trúc hay runtime journal.
- Không import source của repo Beads vào `grokpipe`.

## Nguồn và cách cài

Chỉ cài CLI từ project chính chủ. Trên macOS dùng Homebrew theo tài liệu Beads:

```bash
brew install beads
```

Không dùng `curl | bash` trong implementation. Sau cài đặt bắt buộc ghi lại
`bd version`, chạy `bd doctor` và xác minh executable được resolve từ Homebrew.

Beads là CLI cài một lần ở cấp máy; source repo không được clone vào project.

## Storage và authority

Khởi tạo embedded Dolt workspace local. Dữ liệu dùng chung cho Codex và Claude
trên máy hiện tại, chưa có remote sync.

Quy tắc authority:

- Beads là authority cho task/bug status, dependency, assignee và memory.
- Regression test là authority cho bug đã tái hiện hoặc đã sửa.
- Runtime journal của Phase B là authority cho event/stack trace thực tế.
- Tài liệu lifecycle hiện tại là authority cho expected behavior và migration phase.
- Bead không được dùng thay production `JOBS`, queue hoặc job state.

Agent profile bắt buộc là `conservative`. AI được đọc, tạo, claim, cập nhật và đóng
Bead sau verification; không được suy ra quyền commit/push/Dolt sync từ Beads.

## Khởi tạo có kiểm soát

Thực hiện theo thứ tự:

1. `bd init --skip-agents` để tách khởi tạo database khỏi sửa file agent.
2. `bd config set agent.profile conservative`.
3. Chụp `git status` và danh sách file Beads sinh ra.
4. `bd setup codex`, rồi kiểm diff và `bd setup codex --check`.
5. `bd setup claude`, rồi kiểm diff và `bd setup claude --check`.
6. `bd doctor` và `bd hooks list` để phát hiện setup thiếu/stale.

Setup chính chủ dùng managed marker. Chỉ section nằm giữa marker Beads được phép
cập nhật; mọi nội dung có sẵn trong `AGENTS.md` và `CLAUDE.md` phải giữ byte-for-byte
bên ngoài section đó.

Codex integration dự kiến tạo skill ở `.agents/skills/beads/`, hướng dẫn trong
`AGENTS.md` và hook trong `.codex/`. Claude integration dự kiến tạo/cập nhật
`.claude/settings.json` và section trong `CLAUDE.md`. Danh sách thực tế phải được
đối chiếu với `bd setup --list` của version vừa cài trước khi stage.

## Git và dữ liệu local

- Không commit embedded Dolt database, socket, lock, cache hoặc runtime state.
- Chỉ commit agent instructions/integration files và config/export nhỏ mà Beads
  chính thức đánh dấu là shareable.
- Không stage bằng `git add .`; stage exact path sau khi review diff.
- Không sửa hoặc bỏ thay đổi `.gitignore` hiện có của người dùng. Nếu Beads cần
  ignore rules, merge từng dòng và chứng minh không xóa rule cũ.
- Không chạy `bd dolt push`, `git push` hoặc tạo PR trong phase này.
- Trước nâng cấp Beads về sau phải `bd backup`; schema migration chỉ chạy từ một
  workspace được chỉ định.

## Agent workflow

Section chung phải hướng AI theo chuỗi:

1. Chạy `bd prime` khi bắt đầu task có nhiều bước hoặc tiếp tục bug cũ.
2. Chạy `bd ready` để chọn việc không bị block.
3. Chạy `bd show <id>` và đọc evidence/dependency trước khi sửa.
4. Claim atomically bằng `bd update <id> --claim`.
5. Với bug: systematic debugging, regression test đỏ, fix tối thiểu, full gate.
6. Ghi kết quả test, commit liên quan và quyết định vào Bead.
7. Chỉ `bd close` khi acceptance criteria thực sự đạt.

Nếu task nhỏ, không liên quan issue hiện có và không cần memory dài hạn, AI không
bắt buộc tạo Bead mới. Beads không được biến mọi câu hỏi của người dùng thành task.

## Seed lifecycle issue graph

Tạo một epic `Job lifecycle stabilization` và năm bug con tương ứng năm
`expectedFailure` hiện tại:

1. Cancel member không resolve đúng physical `LO:` queue identity.
2. Auto-video enqueue trùng khi item đã queued.
3. Auto producer không tuân cùng stop-generation barrier với retry timer.
4. Multi-copy enqueue dùng trùng logical job identity.
5. Forced-account constraint bị mất qua retry item.

Mỗi bug phải chứa:

- đường dẫn và test method đang `expectedFailure`;
- expected behavior từ `docs/JOB-LIFECYCLE-DECISIONS.md`;
- current behavior ngắn gọn;
- dependency/migration phase;
- acceptance criteria: bỏ đúng decorator, test đỏ trước fix, test xanh sau fix,
  full lifecycle gate xanh và baseline xfailed giảm đúng một;
- label `runtime`, `job-lifecycle`, loại `bug`, priority theo audit hiện tại.

Không tự claim hoặc tự đóng năm bug khi seed.

## Failure và rollback

- `bd` không chạy: không sửa tay database; giữ nguyên repo và đọc `bd doctor`.
- Setup agent làm đổi nội dung ngoài managed marker: khôi phục chỉ diff do setup và
  dừng triển khai để điều tra.
- Hook làm hỏng commit/push: dùng `bd hooks list`, gỡ hook Beads bằng command chính
  chủ; không xóa toàn bộ `.git/hooks`.
- Có thể gỡ integration bằng `bd setup codex --remove` và
  `bd setup claude --remove`; database chỉ xóa khi người dùng yêu cầu rõ.
- Không dùng `rm -rf .beads`; backup và lệnh Beads chính chủ là đường rollback.

## Verification

- `bd version` và `bd doctor` exit 0.
- `bd setup codex --check` và `bd setup claude --check` báo current.
- `bd prime` hiển thị conservative policy và memory/project context.
- `bd ready --json` parse được.
- Epic và năm bug hiển thị đúng dependency; không bug nào bị claim/closed.
- Phiên Codex/Claude mới nhận ra Beads workflow sau restart.
- Existing `AGENTS.md`/`CLAUDE.md` content ngoài managed markers không đổi.
- `./test-job-lifecycle.command` vẫn đạt 30 pass, 5 xfailed và coverage >=80%.
- Git diff không chứa production file, project media, secret hoặc embedded database.

## Điều kiện thành công

- Codex và Claude dùng chung một local Beads workspace.
- AI có một cửa vào ngắn (`bd prime`) và issue graph thay vì danh sách Markdown dài.
- Năm known lifecycle bug có executable evidence và acceptance criteria rõ.
- Git authority vẫn conservative; không có remote sync hoặc cloud data.
- Gỡ integration được mà không làm mất hướng dẫn hiện có hoặc database ngoài ý.
