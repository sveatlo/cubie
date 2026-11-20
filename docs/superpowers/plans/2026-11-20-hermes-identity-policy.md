# Hermes identity and policy separation

## Agreed design

Separate personality from operating rules for Samwise, Laki and Laki's trader profile.
Build on `feat/laki-trader` in an isolated worktree.
Preserve existing authorization boundaries and runtime identity edits.
Laki's voice is a dry-witted friend and sparring partner: object once, then help with an informed authorized decision.
Samwise keeps his existing characterization.

Each source profile has `SOUL.md` for character, `AGENTS.md` for working instructions, and `POLICY.md` for authorization and privacy.
At runtime, seed `SOUL.md` in the profile home; refresh `workspace/AGENTS.md` and `POLICY.md` on initialization.
AGENTS requires reading the active profile's policy before acting.
SOUL includes a fallback pointer for sessions without workspace context.
Managed cron jobs explicitly select the profile workspace.

Alternatives considered: combining everything into runtime SOUL gives broader automatic delivery; embedding policy in runtime AGENTS avoids a separate read.
The owner explicitly chose separate runtime files and rejected embedding policy in AGENTS.
Hermes v0.23.3 does not automatically load POLICY: compliance depends on following the read instruction, not access enforcement.
Do not change approval modes, credentials, RBAC, running workloads or historical sessions.

## Implementation plan

- Add failing filesystem tests for managed policy/instruction refresh, restrictive permissions, preserved runtime identity, and refusal of symlinked managed destinations.
- Install the managed files before plugin initialization, using a shared helper for default and trader homes.
- Split both existing identities without dropping policy; adopt trader's files when the upstream branch supplies them.
- Include both files in each profile's ConfigMap and explicitly scope the daily review workdir.
- Fix the existing Git-ignore test's dependency on the caller's working directory so it runs inside an isolated worktree.
- Run the full Hermes unittest suite and Kustomize rendering.
- Exercise actual pinned-image context loading with synthetic, credential-free profile homes; confirm policy is not implicitly loaded and AGENTS is workspace-scoped.
- Review the diff independently; document existing-instance migration and frozen-session prompt refresh.

## Evidence

- Hermes image: `v0.23.3@sha256:3e9fe4c6ef36490f43aa0d0d80f9df64e9c92a576eee3042f1a97c8813c05355`.
- Official tag source: https://github.com/NousResearch/hermes-agent/tree/caafe5389ae585ef77387a962aee05b1bcf17029
- `agent/prompt_builder.py`: profile-home SOUL and working-directory AGENTS discovery.
- `cron/scheduler.py`: project context requires an existing explicit job workdir.
- Existing runtime SOUL is seed-only; continued sessions retain frozen prompt content.
