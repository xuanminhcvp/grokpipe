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
if bd config list | rg -q '^[[:space:]]*sync\\.remote[[:space:]]*='; then
  bd config unset sync.remote
fi
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
bd hooks list
bd where
bd config get agent.profile
! bd config list | rg -q '^[[:space:]]*sync\\.remote[[:space:]]*='
bd prime
bd ready --json
```

Expected: `bd doctor` aggregate không được dùng làm gate vì Beads 1.2.1 embedded không
hỗ trợ nó. `bd where` resolve shared embedded workspace, profile hoạt động là
`conservative`, `sync.remote` absent; header Claude `profile:minimal` là managed static metadata;
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
bd create "Cancel member resolves physical LO queue identity" -t bug -p 1 --parent "$epic_id" --add-label runtime --add-label job-lifecycle --description "Current behavior: tests/job_lifecycle/test_cancel_characterization.py::CancelCharacterizationTest::test_member_only_jobs_can_resolve_physical_group_queue_identity is an expected failure because a member queued in LO:<members> cannot resolve the physical queue identity and stale work can remain. Expected behavior (D13, D23): cancellation is bound to job_id; an atomic CANCELLED transition means stale queue tokens cannot lease or revive that job. Dependency/migration phase: Phase 8 Cancel, safe stop and emergency stop, after the Phase 4 Scheduler/lease abstraction; Phase 0-1 production authority remains legacy JOBS, PriorityQueue, worker, retry and auto." --acceptance "Remove only this @unittest.expectedFailure decorator; run the targeted test without it and observe red before implementation; after the minimal fix the same targeted test is green; the full lifecycle gate is green; the xfailed baseline decreases exactly one from 5 to 4; do not add a queue/JOBS writer." --json
```

Expected: one open, unclaimed child bug.

- [ ] **Step 3: Create the auto-video duplicate child bug**

Run:

```bash
bd create "Auto-video blocks queued and running duplicates" -t bug -p 1 --parent "$epic_id" --add-label runtime --add-label job-lifecycle --description "Current behavior: tests/job_lifecycle/test_auto_characterization.py::AutoCharacterizationTest::test_auto_video_blocks_both_running_and_queued is an expected failure because auto-video can enqueue a second logical run while the shot is queued or running. Expected behavior (D07, D12): each active job has at most one queue entry/worker lease; auto is a producer, not a retry controller, and must not create a new run for an active or failed-unacknowledged asset. Dependency/migration phase: Phase 3 Producer commands and idempotency, dependent on the Phase 2 JobStore/JobManager shadow foundation; Phase 0-1 production authority remains legacy JOBS, PriorityQueue, worker, retry and auto." --acceptance "Remove only this @unittest.expectedFailure decorator; run the targeted test without it and observe red before implementation; after the minimal fix the same targeted test is green; the full lifecycle gate is green; the xfailed baseline decreases exactly one from 5 to 4; do not create a second re-enqueue authority." --json
```

- [ ] **Step 4: Create the stop-barrier race child bug**

Run:

```bash
bd create "Auto producer obeys the retry stop-generation barrier" -t bug -p 1 --parent "$epic_id" --add-label runtime --add-label job-lifecycle --description "Current behavior: tests/job_lifecycle/test_auto_characterization.py::AutoCharacterizationTest::test_auto_producer_observes_same_stop_barrier_as_retry_timer is an expected failure because an auto snapshot or retry timer can enqueue stale work after stop-all. Expected behavior (D15, D23): controlled stop blocks new producers, and queue tokens/worker leases carry an expected version so stale work is discarded without reviving a cancelled run. Dependency/migration phase: Phase 8 Cancel, safe stop and emergency stop, after the Phase 4 Scheduler/lease abstraction; Phase 0-1 production authority remains legacy JOBS, PriorityQueue, worker, retry and auto." --acceptance "Remove only this @unittest.expectedFailure decorator; run the targeted test without it and observe red before implementation; after the minimal fix the same targeted test is green; the full lifecycle gate is green; the xfailed baseline decreases exactly one from 5 to 4; terminal or cancelled jobs are not resurrected and no producer gains retry authority." --json
```

- [ ] **Step 5: Create the multi-copy identity child bug**

Run:

```bash
bd create "Multi-copy enqueue assigns distinct job identities" -t bug -p 1 --parent "$epic_id" --add-label runtime --add-label job-lifecycle --description "Current behavior: tests/job_lifecycle/test_auto_characterization.py::AutoCharacterizationTest::test_multi_copy_enqueue_uses_distinct_job_identity_per_copy is an expected failure because requested copies alias one logical identity, state and retry history. Expected behavior (D01, D03): asset_id, job_id, attempt_id and batch_id are distinct; every requested copy is an independent child job/output with its own success, failure and account history. Dependency/migration phase: Phase 3 Producer commands and idempotency, dependent on Phase 1 identity models and the Phase 2 JobStore/JobManager shadow foundation; Phase 0-1 production authority remains legacy JOBS, PriorityQueue, worker, retry and auto." --acceptance "Remove only this @unittest.expectedFailure decorator; run the targeted test without it and observe red before implementation; after the minimal fix the same targeted test is green; the full lifecycle gate is green; the xfailed baseline decreases exactly one from 5 to 4; asset_id is never reused as a Job, Execution or Attempt ID." --json
```

- [ ] **Step 6: Create the forced-account retry child bug**

Run:

```bash
bd create "Forced-account constraint survives every retry item" -t bug -p 1 --parent "$epic_id" --add-label runtime --add-label job-lifecycle --description "Current behavior: tests/job_lifecycle/test_account_characterization.py::AccountCharacterizationTest::test_forced_account_constraint_is_carried_by_every_retry_item is an expected failure because a forced account can be lost when retry returns to the common queue. Expected behavior (D18): forced means every retry remains constrained to that account; when it is unavailable the job waits in RETRY_WAIT or fails, unless the user explicitly selected an allow-fallback policy. Dependency/migration phase: Phase 5 Attempt and AccountAllocator, after the Phase 4 Scheduler/lease abstraction; Phase 0-1 production authority remains legacy JOBS, PriorityQueue, worker, retry and auto." --acceptance "Remove only this @unittest.expectedFailure decorator; run the targeted test without it and observe red before implementation; after the minimal fix the same targeted test is green; the full lifecycle gate is green; the xfailed baseline decreases exactly one from 5 to 4; account rotation cannot silently override the forced assignment." --json
```

- [ ] **Step 7: Verify graph count, status and ownership**

Run:

```bash
bd show "$epic_id" --json
bd list --json > /tmp/beads-foundation-graph.json
bd ready --json
./.venv/bin/python3 - <<PY
import json

epic_id = "${epic_id}"
children = {
    "Cancel member resolves physical LO queue identity": ("D13, D23", "Phase 8", "5 to 4"),
    "Auto-video blocks queued and running duplicates": ("D07, D12", "Phase 3", "5 to 4"),
    "Auto producer obeys the retry stop-generation barrier": ("D15, D23", "Phase 8", "5 to 4"),
    "Multi-copy enqueue assigns distinct job identities": ("D01, D03", "Phase 3", "5 to 4"),
    "Forced-account constraint survives every retry item": ("D18", "Phase 5", "5 to 4"),
}
issues = json.load(open("/tmp/beads-foundation-graph.json"))
assert len([i for i in issues if i["id"] == epic_id]) == 1
selected = [i for i in issues if i.get("parent") == epic_id]
assert len(selected) == 5
for issue in selected:
    decision, phase, xfailed = children[issue["title"]]
    assert issue["status"] == "open" and issue["priority"] == 1 and issue["issue_type"] == "bug"
    assert not issue.get("assignee") and issue["parent"] == epic_id
    assert set(issue.get("labels") or []) == {"runtime", "job-lifecycle"}
    assert all(needle in issue["description"] for needle in ("Current behavior:", "Expected behavior", decision, "Dependency/migration phase:", phase, "Phase 0-1 production authority remains legacy"))
    assert all(needle in issue["acceptance_criteria"] for needle in ("Remove only this @unittest.expectedFailure decorator", "observe red before implementation", "same targeted test is green", "full lifecycle gate is green", "xfailed baseline decreases exactly one", xfailed))
PY
test "$(bd list --no-labels --json | ./.venv/bin/python3 -c 'import json,sys; print(len([i for i in json.load(sys.stdin) if i.get("parent") == "'"$epic_id"'"]))')" -eq 0
```

Expected: exactly one matching epic and five children. Every child is open, unassigned,
P1 and type bug under that epic; its label set is exactly `runtime` and `job-lifecycle`;
the required current/expected/dependency semantics and red-green/full-gate/exact-one-xfailed
acceptance phrases are asserted, rather than merely non-empty.

### Task 4: Complete the foundation verification

**Files:**
- Verify only.

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: evidence that Beads and both AI integrations work without production regression or remote sync.

- [ ] **Step 1: Run Beads health and integration checks fresh**

Run:

```bash
bd where
bd setup codex --check
bd setup claude --check
bd config get agent.profile
! bd config list | rg -q '^[[:space:]]*sync\\.remote[[:space:]]*='
bd prime
```

Expected: `bd where` resolves the shared embedded workspace; Codex check is current;
Claude stale caused only by absent `sync.remote` is an accepted Beads 1.2.1 caveat and
does not authorize rewriting the managed marker; profile is `conservative`; `bd prime`
returns context. Aggregate `bd doctor` is unsupported in embedded mode and is not a gate.

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
