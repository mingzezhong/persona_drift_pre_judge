# Legacy v1 recovery

The active branch was reset on 2026-08-24 for the conditional-trajectory v2
protocol. Nothing from v1 was treated as v2 evidence or silently discarded.

## Tracked repository snapshot

- Annotated Git tag: `pre-restart-v1-20260824`
- Commit: `447a72058bd350aec21edb9405c9720a78d561a4`
- The tag was pushed to `origin` before active-tree cleanup.

Inspect the old tree without changing the active branch:

```bash
git show pre-restart-v1-20260824:README.md
```

Create a separate recovery worktree when the complete old code tree is needed:

```bash
git worktree add ../persona_drift_pre_judge-v1 pre-restart-v1-20260824
```

## Non-Git scientific artifacts

Old ignored outputs, scheduler logs, local backups, and untracked retrospective
diagnostics are stored read-only at:

```text
legacy_artifacts/pre_restart_v1_20260824/
```

The archive is deliberately excluded from GitHub because it is about 820 MB.
It contains 974 files and 820,269,820 bytes. Its payload manifest is:

```text
legacy_artifacts/pre_restart_v1_20260824/manifest.sha256
SHA256: 0a4b47b88c36af620d9358b82755d6350588f5e04270a727ed5f846d01798702
```

Verify the payload from the repository root:

```bash
cd legacy_artifacts/pre_restart_v1_20260824
sha256sum -c manifest.sha256
```

The archive summary SHA256 is
`ce8892f7918a3d375eb2235b03d348bdfd7601cc766d9a6486a2eabc18c2cbbd`.
If the archive is copied elsewhere, copy the manifest and summary with it.

## Scientific status

V1 results are historical and exploratory for the restarted study. They may be
used for engineering checks or hypothesis generation, but not as development,
calibration, or confirmation data for v2.
