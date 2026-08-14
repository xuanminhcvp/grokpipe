# Beads Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cài Beads và ast-grep chính chủ, tạo local embedded workspace dùng chung cho Codex/Claude và seed năm lifecycle bug hiện có mà không sửa production runtime.

**Architecture:** Beads CLI được cài cấp máy bằng Homebrew; repo dùng embedded Dolt local, conservative agent policy và integration chính chủ cho Codex/Claude. Versioned instruction files được chuẩn bị trong worktree cô lập; database và issue data giữ local, không Dolt remote hoặc cloud sync.

**Tech Stack:** Beads CLI/Homebrew, ast-grep 0.45.1, embedded Dolt, Codex skill/hooks, Claude Code hooks, Git, existing pytest lifecycle gate.

## Global Constraints

- Cài Homebrew formula chính chủ `beads`; expected stable tại thời điểm lập plan là `1.2.1`.
- Cài Homebrew formula chính chủ `ast-grep`; expected stable là `0.45.1`.
- Không clone source repo Beads vào `grokpipe` và không dùng `curl | bash`.
- ast-grep search-only; cấm `--rewrite`, `-r` hoặc interactive rewrite trong Phase A.
- Storage local embedded dùng chung ở checkout canonical `main` và linked worktrees;
  không `bd dolt push/pull`, `bd sync`, remote sync hoặc GitHub Issues. `sync.remote`
  phải absent.
- `agent.profile=conservative`; AI không tự commit, push, merge hoặc chạy provider.
- Giữ byte-for-byte mọi nội dung hiện có ngoài managed marker trong `AGENTS.md` và `CLAUDE.md`.
- Không commit embedded Dolt database, socket, lock, cache hoặc runtime state.
- Không sửa production file và không thay baseline 30 pass, 5 xfailed.
- Không stage bằng `git add .`; mọi lần stage dùng exact path.
- Main có thay đổi riêng của người dùng; implementation phải bắt đầu bằng
  `superpowers:using-git-worktrees`. Linked worktree được phép resolve workspace local
  chung ở main nhưng không được sửa tracked user changes hoặc ép database riêng.
- Không xóa worktree sau merge cho tới khi workspace local chung ở main đã được
  khởi tạo/seed và `bd show` xác minh đủ epic cùng năm child bug.
- Commit message của repo là `update`.

---

## File Map

- Modify: `AGENTS.md` — managed Beads Codex section, giữ nguyên lifecycle rules.
- Modify: `CLAUDE.md` — managed Beads Claude section, giữ nguyên film/runtime rules.
- Create: `.agents/skills/beads/` — skill do `bd setup codex` sinh.
- Create/modify: `.codex/` — hook/config do `bd setup codex` sinh nếu version 1.2.1 yêu cầu.
- Create/modify: `.claude/settings.json` — Claude SessionStart hook do `bd setup claude` sinh.
- Local only: `.beads/` ở checkout canonical — embedded Dolt workspace, config, issue
  graph và checkpoint dùng chung với linked worktrees; không stage database.
- Local-only ignore: exact Beads database patterns do `bd init` sinh phải được merge vào ignore configuration mà không xóa rule có sẵn của người dùng.

### Task 1: Install and verify the official Beads and ast-grep CLIs

**Files:**
- System install only; no repo file.

**Interfaces:**
- Consumes: Homebrew formula metadata for `gastownhall/beads`.
- Produces: executable `bd` version `1.2.1` and `ast-grep` version `0.45.1` on `PATH`, no project initialization yet.

- [ ] **Step 1: Prove the CLI is absent**

Run:

```bash
command -v bd
command -v ast-grep
```

Expected before install: both absent. If either path exists, compare its version with Homebrew metadata; do not overwrite a newer compatible version.

- [ ] **Step 2: Confirm the Homebrew formula source**

Run:

```bash
brew info beads
brew info ast-grep
```

Expected: Beads points to `gastownhall/beads` at stable `1.2.1`; ast-grep points to `ast-grep/ast-grep` at stable `0.45.1`; both MIT.

- [ ] **Step 3: Install the official formula**

Run:

```bash
brew install beads
brew install ast-grep
```

Expected: Homebrew installs both CLIs and declared dependencies without modifying repo files.

- [ ] **Step 4: Verify binary identity and version**

Run:

```bash
command -v bd
command -v ast-grep
brew list --versions beads
brew list --versions ast-grep
bd version
ast-grep --version
```

Expected: both resolve inside the Homebrew prefix; versions are `1.2.1` and `0.45.1`.

- [ ] **Step 5: Prove ast-grep structural search is read-only and useful**

Run:

```bash
git status --short > /tmp/grokpipe-status-before-ast-grep.txt
ast-grep --lang python --pattern '$OBJ[$KEY] = $VALUE' sfboard
ast-grep --lang python --pattern '$QUEUE.put($ITEM)' sfboard
git status --short > /tmp/grokpipe-status-after-ast-grep.txt
diff -u /tmp/grokpipe-status-before-ast-grep.txt /tmp/grokpipe-status-after-ast-grep.txt
```

Expected: structural matches include state/queue writers; final diff exits 0, proving no rewrite.

### Task 2: Initialize the local workspace and install agent integrations

**Files:**
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`
- Create: `.agents/skills/beads/`
- Create/modify: `.codex/`
- Create/modify: `.claude/settings.json`
- Local only: `.beads/`

**Interfaces:**
- Consumes: `bd` 1.2.1 and existing AI instructions.
- Produces: healthy embedded workspace, conservative policy, current Codex/Claude setup.

- [ ] **Step 1: Create or verify the isolated feature worktree**

Use `superpowers:using-git-worktrees` with branch:

```text
codex/beads-foundation
```

Expected: worktree starts from current `main` và sạch. Tracked user changes tại
`/Users/may1/Desktop/grokpipe` vẫn untouched; Beads 1.2.1 có thể resolve local database
chung ở đó và đó là hành vi được phê duyệt.

Create the ignored Python environment needed by JSON checks and the lifecycle gate:

```bash
python3 -m venv .venv
./.venv/bin/python3 -m pip install -r requirements-test.txt
```

Expected: `.venv/` remains ignored and pytest dependencies install successfully.

- [ ] **Step 2: Capture pre-setup instruction files**

Run in the worktree:

```bash
git show HEAD:AGENTS.md > /tmp/grokpipe-agents-before-beads.md
git show HEAD:CLAUDE.md > /tmp/grokpipe-claude-before-beads.md
```

Expected: snapshots contain the Vietnamese language rule, lifecycle routing and existing film/runtime rules.

- [ ] **Step 3: Initialize embedded Beads without automatic agent edits**

Run:

```bash
bd init --quiet --skip-agents
bd config set agent.profile conservative
bd config get sync.remote
# Nếu key tồn tại:
bd config unset sync.remote
```

Expected: linked worktree resolve embedded `.beads/` local chung ở checkout canonical
`main`; không ép DB riêng hoặc reinit. `sync.remote` absent, không có lệnh remote chạy
và agent files vẫn unchanged. Với 1.2.1, không dùng `bd dolt set mode embedded` vì mode
embedded hiện hữu không hỗ trợ setter này.

- [ ] **Step 4: Install Codex integration and inspect its exact scope**

Run:

```bash
bd setup codex
bd setup codex --check
git status --short
git diff -- AGENTS.md .agents .codex
```

Expected: check reports current; `AGENTS.md` only gains a `BEGIN/END BEADS CODEX SETUP` managed block; generated skill/hooks point agents to `bd prime`.

- [ ] **Step 5: Install Claude integration and inspect its exact scope**

Run:

```bash
bd setup claude
bd setup claude --check
git status --short
git diff -- CLAUDE.md .claude/settings.json
```

Expected: `CLAUDE.md` only gains its managed Beads block; `.claude/settings.json` has a
SessionStart hook invoking `bd prime --hook-json` exactly once. Với `sync.remote` absent,
Beads 1.2.1 có thể báo `CLAUDE.md` stale dù file/managed block unchanged; không chạy setup
để rewrite marker chỉ nhằm suppress warning đó.

- [ ] **Step 6: Verify existing instructions still exist outside managed blocks**

Run:

```bash
rg -n 'Luôn trả lời người dùng bằng tiếng Việt|JOB-LIFECYCLE-README|Không tự ý sửa skill' AGENTS.md CLAUDE.md
rg -n 'BEGIN BEADS|END BEADS|bd prime' AGENTS.md CLAUDE.md
```

Expected: all three existing rules and both managed marker pairs are present.

Add one concise managed-project instruction outside Beads-owned markers only if the
generated integrations do not mention structural search:

```text
Code navigation: Serena for symbols/references, ast-grep for structural assignments
and calls, rg for text/docs. ast-grep is search-only unless an approved TDD plan
explicitly authorizes rewrite.
```

Thêm ngoài Beads-owned markers trong `AGENTS.md` policy rõ rằng ví dụ `bd prime` chứa
Dolt/Git pull, push, sync hoặc provider chỉ là documentation, không phải authorization;
AI chỉ chạy chúng sau khi user phê duyệt rõ đúng action. Không thêm policy này vào
`CLAUDE.md`: generated marker hash của Beads 1.2.1 bao gồm preamble và sẽ báo stale dù
managed block không đổi; `AGENTS.md` là repository policy authority cho cả integration.

- [ ] **Step 7: Verify workspace health and no remote**

Run:

```bash
bd version
ast-grep --version
bd doctor
bd hooks list
bd config get agent.profile
bd prime
bd ready --json
```

Expected: doctor có thể yêu cầu embedded-compatible checks thay aggregate doctor; profile
hoạt động là `conservative`; header Claude `profile:minimal` là managed static metadata;
prime in workflow context và có thể chứa upstream remote examples, nhưng policy ngoài
marker phủ định chúng; ready returns parseable JSON. `sync.remote` phải absent. Nếu Claude
check báo stale chỉ vì key này absent dù managed block unchanged, giữ nguyên marker và xác
minh hook JSON thay vì rewrite generated content.

- [ ] **Step 8: Audit generated storage before staging**

Run:

```bash
git status --short
bd where
find /Users/may1/Desktop/grokpipe/.beads -maxdepth 3 -type f -print | sort
git -C /Users/may1/Desktop/grokpipe check-ignore -v .beads/embeddeddolt 2>/dev/null || true
```

Expected: embedded database/cache/lock files ở canonical workspace ignored hoặc strictly
local. Nếu cần exclude local, thêm exact pattern vào `.git/info/exclude`, không sửa
`.gitignore` có thay đổi của user. Nếu database file appears stageable, dừng và thêm
chỉ official ignore pattern, giữ nguyên mọi rule có sẵn.

- [ ] **Step 9: Commit only shareable integration files**

Stage only paths generated by the two setup recipes after diff review:

```bash
git add AGENTS.md CLAUDE.md .agents/skills/beads .codex .claude/settings.json
git diff --cached --check
git diff --cached --stat
git commit -m "update"
```

Expected: commit contains no `.beads/embeddeddolt`, media, production Python/JS/CSS or secret.

### Task 3: Seed the lifecycle issue graph

**Files:**
- Local Beads database only; no production or Markdown task list.

**Interfaces:**
- Consumes: healthy local workspace and five existing `expectedFailure` tests.
- Produces: one unclaimed epic with five unclaimed child bug Beads.

- [ ] **Step 1: Create the epic and capture its generated ID**

Run:

```bash
epic_json="$(bd create "Job lifecycle stabilization" -t epic -p 1 --description "Resolve the five audited lifecycle ambiguities one phase at a time. Architecture and expected behavior live in docs/JOB-LIFECYCLE-README.md and docs/JOB-LIFECYCLE-DECISIONS.md. Production authority remains legacy until its migration phase." --acceptance "All five child bugs are fixed through red-green regression tests; lifecycle gate passes; xfailed baseline reaches zero only through verified fixes." --json)"
epic_id="$(printf '%s' "$epic_json" | ./.venv/bin/python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["id"] if isinstance(d,dict) else d[0]["id"])')"
printf '%s\n' "$epic_id"
```

Expected: a non-empty Beads ID such as `grokpipe-a1b2`.

- [ ] **Step 2: Create the cancel-identity child bug**

Run:

```bash
bd create "Cancel member resolves physical LO queue identity" -t bug -p 1 --parent "$epic_id" --description "Current expected failure: tests/job_lifecycle/test_cancel_characterization.py::CancelCharacterizationTest::test_member_only_jobs_can_resolve_physical_group_queue_identity. A member job may be queued physically as LO:<members>; cancel must resolve and invalidate that queue identity without reviving remaining work incorrectly." --acceptance "Remove only this expectedFailure decorator; observe red before implementation; targeted test and full lifecycle gate pass; xfailed count decreases from 5 to 4; no new queue/JOBS writer." --json
```

Expected: one open, unclaimed child bug.

- [ ] **Step 3: Create the auto-video duplicate child bug**

Run:

```bash
bd create "Auto-video blocks queued and running duplicates" -t bug -p 1 --parent "$epic_id" --description "Current expected failure: tests/job_lifecycle/test_auto_characterization.py::AutoCharacterizationTest::test_auto_video_blocks_both_running_and_queued. Auto-video must not enqueue a second logical run while the shot is already queued or running." --acceptance "Remove only this expectedFailure decorator; prove red then green; full gate passes; xfailed count decreases by one; no second re-enqueue authority." --json
```

- [ ] **Step 4: Create the stop-barrier race child bug**

Run:

```bash
bd create "Auto producer obeys the retry stop-generation barrier" -t bug -p 1 --parent "$epic_id" --description "Current expected failure: tests/job_lifecycle/test_auto_characterization.py::AutoCharacterizationTest::test_auto_producer_observes_same_stop_barrier_as_retry_timer. Stop-all must prevent both retry timers and auto producers from enqueueing stale work." --acceptance "Remove only this expectedFailure decorator; reproduce the race deterministically; targeted and full gates pass; terminal/cancelled jobs are not resurrected." --json
```

- [ ] **Step 5: Create the multi-copy identity child bug**

Run:

```bash
bd create "Multi-copy enqueue assigns distinct job identities" -t bug -p 1 --parent "$epic_id" --description "Current expected failure: tests/job_lifecycle/test_auto_characterization.py::AutoCharacterizationTest::test_multi_copy_enqueue_uses_distinct_job_identity_per_copy. Every requested copy needs distinct logical job/execution identity instead of aliasing state and retry history." --acceptance "Remove only this expectedFailure decorator; prove identity collision red then green; full gate passes; asset ID is not reused as Job/Execution/Attempt ID." --json
```

- [ ] **Step 6: Create the forced-account retry child bug**

Run:

```bash
bd create "Forced-account constraint survives every retry item" -t bug -p 1 --parent "$epic_id" --description "Current expected failure: tests/job_lifecycle/test_account_characterization.py::AccountCharacterizationTest::test_forced_account_constraint_is_carried_by_every_retry_item. A forced account must remain a job constraint across retries unless explicit fallback policy allows otherwise." --acceptance "Remove only this expectedFailure decorator; prove retry loses the constraint before fix; targeted and full gates pass; account rotation cannot silently override forced assignment." --json
```

- [ ] **Step 7: Verify graph count, status and ownership**

Run:

```bash
bd show "$epic_id" --json
bd list --json
bd ready --json
```

Expected: exactly one matching epic and five matching children; every child is open and unclaimed; descriptions and acceptance criteria are non-empty.

### Task 4: Complete the foundation verification

**Files:**
- Verify only.

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: evidence that Beads and both AI integrations work without production regression or remote sync.

- [ ] **Step 1: Run Beads health and integration checks fresh**

Run:

```bash
bd doctor
bd setup codex --check
bd setup claude --check
bd config get agent.profile
bd prime
```

Expected: all checks current/healthy, ast-grep `0.45.1` and profile `conservative`.

- [ ] **Step 2: Prove JSON commands are machine-readable**

Run:

```bash
bd ready --json | ./.venv/bin/python3 -m json.tool >/dev/null
bd list --json | ./.venv/bin/python3 -m json.tool >/dev/null
```

Expected: both exit 0.

- [ ] **Step 3: Run the full lifecycle gate**

Run:

```bash
./test-job-lifecycle.command
```

Expected: `30 passed, 5 xfailed`, coverage at least 80%, compile pass.

- [ ] **Step 4: Audit Git scope and secrets**

Run:

```bash
git status --short
git diff main...HEAD --name-only
git diff main...HEAD --check
git grep -n -E 'BEGIN BEADS|bd prime' -- AGENTS.md CLAUDE.md .agents .codex .claude/settings.json
ast-grep --lang python --pattern '$OBJ[$KEY] = $VALUE' sfboard >/dev/null
ast-grep --lang python --pattern '$QUEUE.put($ITEM)' sfboard >/dev/null
```

Expected: branch contains only approved agent integration/plan files; no production file, media, credential, embedded database or runtime log.

- [ ] **Step 5: Record handoff facts**

Final report must state installed `bd`/ast-grep versions, workspace mode, conservative policy, health checks, integration file scope, seeded epic/child IDs, lifecycle test output, structural-search smoke result, local-only/no-remote status and any generated file deliberately left untracked.

Khi người dùng chọn merge local ở `finishing-a-development-branch`, trước cleanup
worktree phải khởi tạo embedded workspace tại `/Users/may1/Desktop/grokpipe`, chạy
lại Task 3 trên database main, rồi xác minh `bd show`/`bd list` và lifecycle gate.
