# Local token accounting and machine comparison

## What ships in 2.3.0

Claude and Codex provider pages show a **This machine · tokens** card. It starts
collapsed with input/output totals for today and the last seven calendar days,
including today. Click to expand all details; another click collapses it.
Expansion survives data redraws in the current window. Compact K/M totals are
rounded for display; expanded totals retain exact integer counts.

Accounting reads `CLAUDE_CONFIG_DIR/projects/**/*.jsonl` (default
`~/.claude/projects`), and `CODEX_HOME/sessions/**/*.jsonl` and
`CODEX_HOME/archived_sessions/**/*.jsonl` (default `~/.codex`). Nested subagent logs
are included. Settings can disable accounting independently of quota history.

- Claude input = ordinary input + cache reads + cache creation. Repeated streaming
  blocks share a message identity and contribute only their fullest counters.
  Zeroed auxiliary blocks do not create usage or false partial-data warnings.
- Codex input already includes cache reads/writes. Modern `token_usage_record`
  entries are deduplicated by response ID and counted even when no corresponding
  UI `token_count` event was emitted. Mirrored UI events are excluded. A legacy
  prefix before a CLI upgrade and entirely legacy files still use cumulative
  counter deltas, with `last_token_usage` at the initial/reset boundary.
- Reasoning is not added to output again. It is a subset of output.
- Calendar periods use the computer's timezone (including the OS timezone's DST
  history). Future records and records outside the period are excluded.

The cache is in memory and unchanged files are not reparsed. After restarting,
statistics are reconstructed from available logs. Deleting logs removes their
usage from this view. Missing logs mean **no data**, not proof of zero activity.
Malformed records are flagged; errors with known dates outside the selected
period do not make the current period partial. No conversation content is stored
or sent, and the UI receives only aggregates, model names and coverage status.

This is available-log accounting, not a provider billing ledger. Imported sessions
can include usage from another computer. The current format assumes a session
upgrades from legacy UI counters to modern direct records; a downgrade within the
same file after direct records begin is not supported. Missing or disabled CLI
logging cannot be reconstructed from the account-wide quota endpoint.

## Cost and subscription percentages

The amount is a **standard short-context API equivalent**, not a subscription bill.
The rate table is dated September 14, 2026 and does not update automatically:
[OpenAI API pricing](https://developers.openai.com/api/docs/pricing),
[Anthropic API pricing](https://platform.claude.com/docs/en/about-claude/pricing).
Unknown models remain unpriced; a partial amount is explicitly marked.

Cost = `(uncached input * input rate + cache reads * read rate + cache writes *
write rate + output * output rate) / 1,000,000`. Claude one-hour cache writes use
separate pricing. Fast mode, long-context, regional and server-tool surcharges
are excluded. Exact request pricing would require those request attributes and
a versioned rate table, rather than a single generic token price.

There is no fixed conversion from tokens to subscription percentage here.
Account-wide quota changes can include other computers, cloud tasks, reset
boundaries and plan changes. Public token/credit rates do not by themselves
specify the included quota of a particular account.
[OpenAI documents tokens and credits separately](https://learn.chatgpt.com/docs/pricing).
An experimental percentage estimate would require a known observation interval,
activity from all machines, an unchanged quota window and explicit uncertainty.
It must not replace the provider-reported remaining limit.

## Reconciliation before release

`python scripts/audit_local_usage.py --local-logs` is an explicit, read-only audit.
It freezes a temporary metadata-only copy of the relevant logs and independently
sums unique response/message records. No conversation content or original paths
are printed. The snapshot is removed when the audit finishes.

On September 14, 2026, reconciliation covered 47 Claude files and 8 Codex files.
Input, output, cache read/write and one-hour cache-write differences were zero for
both providers, both today and seven days. Independent Decimal cost arithmetic
matched to less than one billionth of a dollar. These are arithmetic checks of
available logs, not an assertion of complete provider billing coverage.

The audit found and fixed omitted Codex responses that had direct usage records
but no UI counter update. Synthetic tests also cover legacy counters, copied
sessions, model changes, format upgrades, timezone/day boundaries, unknown prices,
cache-write durations, malformed records, cache invalidation and opt-out.

## Proposed next stage: home and work

Add a separate **Usage** page once data exchange exists, with a shared period,
provider filter and a table of machine name, input, output, cache counts,
API-equivalent cost, share of recorded usage and last update. Keep the compact
current-machine cards as shortcuts to that page.

1. Generate a random local device ID and an editable Home/Work label. Do not use
   the Windows username or hostname as the persistent identifier.
2. Store normalized UTC usage events, model/counters, source identity and schema
   version. Use an explicit user-chosen account alias to separate personal and
   work subscriptions; never synchronize credentials.
3. Start with manual aggregate export/import. An optional shared-folder transport
   can later use one atomically replaced file per device, with a single writer.
4. Import replaces the previous revision instead of adding it twice. Validate
   schema, counts and file size; show offline/stale devices and update timestamps.
5. Preserve original device provenance when sessions are copied. Historical local
   imports without provenance must be marked as unknown to avoid double counting.
6. Recompute all periods in one chosen timezone. Test duplicate imports, conflicting
   revisions, offline devices, account changes, transfers, midnight and rate changes.

A machine's share is its share of recorded token usage or API-equivalent cost,
not its share of the subscription quota. Do not show a complete cost share when
some models are unpriced. Synchronization is not part of this release.

## Weekly-only Codex limits

The primary position in a quota response does not imply five hours.
`limit_window_seconds` (with minute-field aliases) determines the window:
604800 seconds is Week, 18000 is Session (5h), and an unknown duration gets a
neutral Usage limit label. The remaining time until reset is not used to infer
the full window. Weekly-only Codex plans use the weekly tray indicator and omit
the unavailable five-hour choice. Old incorrectly labeled session history is
not mixed into the new weekly history.
