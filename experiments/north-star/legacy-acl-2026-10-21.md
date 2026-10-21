# Existing Windows conversation ACL recovery

2026-10-21. Restore automatic North Star maintenance in existing Windows
conversations whose state directories were created with protected DACLs.

## Change and global application

Python's Windows `mkdir(mode=0o700)` had disabled ACL inheritance. New-directory
creation was already fixed, but older ledgers still blocked sandboxed maintenance.
Store initialization now repairs protected state paths before reading a ledger,
including on native SessionStart after resume. The installer also migrates all
existing North Star ledgers. Neither path requires a user command or goal reset.

The repair enables inheritance from the existing managed parent. It preserves
ownership and explicit ACEs, adds no account-specific grant, and backs up every
original protected descriptor under private `north-star/acl-backups/` before
changing permissions. Preflight rejects junctions/reparse points and unreadable
subtrees. State/source content, original reference offsets/hashes, goal versions,
call budgets, cooldowns and recovery markers are not rewritten by migration.
The Windows inheritance API and propagation rules are documented by
[Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setnamedsecurityinfow).

Actual global installation with `--preserve-config` repaired **47 directories**.
SHA-256 comparisons preserved **117 existing state, source, history and audit
files**. Live byte-lock files were excluded from content comparison. Config and
hooks JSON were byte-identical. Installed code/manifest hashes matched, all six
North Star hooks remained enabled/trusted, and no protected state paths remained
after verification. Existing unrelated hook settings were retained.

## Native existing-conversation verification

Two previously recorded synthetic employee-filter conversations were resumed
through the real Codex app-server using their **original thread IDs, fixtures,
goals and source journals**. Before each resume, the driver restored that
thread's actual original protected DACL from its migration backup and introduced
the same local filter regression. The driver did not repair permissions, invoke
hook handlers, supply a goal patch, alter transcripts/journals/tests, or steer
the agent after starting the turn. Native hooks and installed skill maintenance
handled the rest. These were synthetic conversations, not messages sent to the
user's other project chats.

Each run used one ordinary continuation request, zero subsequent interventions,
approval policy `never`, a 480-second deadline and a 12-call North Star watchdog.
Global consented limits remain 24 calls/thread/hour. API payload scope, model
`jev-1.14.0` and installed hook definitions were unchanged during both runs.

- **Existing normal conversation, 153.1 seconds, five North Star calls:** native
  ACL repair, original goal references/source bytes preserved, sandboxed CLI
  maintenance succeeded, and all three unchanged original tests passed.
- **Existing pending recovery, 154.8 seconds, six North Star calls:** resumed
  the unfinished recovery left by an earlier native injected-drift experiment.
  Native startup repaired the old protected ACL. Codex corrected the filter,
  executed the original tests through `verify-execution` with real child exit
  code zero, and retained the original goal/source references. With Jev abstaining
  during intermediate checks, Codex compared original scope and actual effects,
  then closed recovery as **`agent_reviewed_execution`** through the versioned
  CLI. No pending recovery remained. Independent final execution confirmed all
  three tests passed and their original SHA-256 was unchanged.

The second result is a Codex review backed by actual execution, not a Jev claim
that recovery succeeded. Final verification also matched the recorded receipt
nonce and command flags against an actual successful native command event;
merely reading documentation containing `verify-execution` is insufficient.

The first resume was initially configured to inject a fresh fault, but the
resumed model did not perform that injection. Its strict fault-test verdict was
therefore **false** and is retained unchanged. Its independently checked normal
continuation observations support ACL/goal preservation only. This follow-up
does not claim a new drift-detection pass from that run. The second run verifies
resumption and closure of an actual previously pending injected-drift recovery;
fresh native detection was verified in the [preceding experiment](unattended-2026-10-21.md).

## Offline checks and evidence

- Full Python suite: **216 run, 213 passed, 3 skipped** for existing Windows
  symlink/POSIX conditions. Run outside the agent sandbox so the junction test
  could create and reject a real Windows junction.
- Eight new offline ACL tests: protected directories and source files,
  ownership/explicit-ACE and byte preservation, backups, idempotence, installer
  sweep/config preservation, junction refusal, failure propagation, protected
  parents and the non-Windows no-op path.
- Installed automatic-handler/CLI checks: **28 passed**.
- Existing Belay adapter: **25 passed**. Python compilation and
  `git diff --check` passed.

Commands, private raw events and receipts are under the ignored
`.runtime/experiments/north-star-acl-20261021/`: `migration-verification.json`,
`installation.json`, both `resume-*/result.json`, native events/driver input,
`final-verification.json`, `root-tests-final.txt`, `installed-tests.txt`,
`belay-tests.txt` and `native-catalog.jsonl`. No private logs, ACL descriptors,
credentials or original conversation text are committed.

## Limits

This verifies automatic repair of the legacy generated Windows ACLs and native
continuity in two existing synthetic conversations. It does not establish
universal drift-detection accuracy or remove deliberate explicit deny rules.
macOS execution remains unverified; its existing permission behavior is retained
and the non-Windows migration path makes no permission changes.
