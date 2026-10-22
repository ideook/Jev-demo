---
name: jev-explore
description: Find where a feature, rule, or behavior is implemented in a codebase. Shortlist files with ripgrep, rank their relevance with Jev, and inspect the best matches first. Use for code location questions or when the user invokes $jev-explore.
---

# Jev Explore

Locate the code with a small reading budget: local keyword search, Jev relevance ranking, then targeted reads.

Run the bundled script when locating an unknown implementation in a codebase. If the relevant files are already known, read them directly. Write the query directly in concise English from the user's intent, including when the user asks in Korean. Preserve the requested scope, exclusions, and conditions. Do not add a translation tool or API call.

Keep code identifiers, paths, and exact UI labels or quoted search text unchanged, even when they contain Korean. Provide a few code identifiers or English feature terms with repeated `--keyword`; include original-language terms when needed to find matching source. Source excerpts stay unchanged. Answer the user in their preferred language.

```powershell
python -X utf8 "<this-skill>/scripts/jev_rank.py" "Where do employees see their pay?" --root . --keyword payroll --keyword payslip --top 5
```

The script prints ranked file paths and line anchors, elapsed time, API usage, and a report marker. Read the top files with normal file tools and follow their imports or callers until the implementation answers the question. Report verified code locations, using the ranks as reading priorities.

Batching follows a request byte budget by default. `--batch-size` optionally caps files per request; `--batch-bytes`, `--max-candidates`, `--snippet-chars`, and `--top` are adjustable. The video example's batch count is not a requirement. Use `--dry-run` to inspect the shortlist without a service call.

Credentials come from `JEV_API_KEY` or `TYPESAFE_API_KEY`: process environment first, then the target root's `.env` (or `--env-file`), then Windows user environment variables. The Windows fallback also works when Codex was started before the variable was registered, and allows reuse across repositories without copying `.env` files. Pass a credential file's path, never the key value. Source excerpts are sent to the TypeSafe direct API only when this script is invoked. Ignored/generated files and credential files are excluded; common inline credentials are redacted.

If candidates are missing, broaden the keywords or target directory and rerun. A rank cannot recover a file absent from the shortlist. When the API is unavailable or a batch fails, the output explicitly distinguishes lexical suggestions and unranked files from Jev results; continue local search and state the limit. Low ranks or truncated excerpts also warrant further search.

Reading priorities are delivered directly in this script's tool output, only during exploration. No PostToolUse callback is registered for ordinary shell commands. On Windows, use the normal shell tool to invoke Python as shown above; a second PowerShell/Python hook process and its five-second deadline are unnecessary. Allow enough tool time for the requested search and API batches.
