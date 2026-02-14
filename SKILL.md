---
name: chrome-log
description: Capture and analyze Chrome network requests for reverse-engineering APIs. Use when debugging API calls, inspecting network traffic, or reverse-engineering web service endpoints via Chrome Debug's CDP connection.
---

# Chrome Network Logger

Capture and analyze Chrome network requests for reverse-engineering APIs.

## Quick Start

```bash
chrome-debug           # Start Chrome with debugging (cyan/magenta icon)
chrome-log start       # Start capture daemon (opens status page)
# Browse in Chrome Debug, then query:
chrome-log tail -n 10  # Recent requests
```

## Opening URLs (for Claude)

When you need to open a URL and see what requests it makes:

```bash
browse "https://example.com"    # Opens in Chrome Debug (traffic captured)
chrome-log tail -n 10           # See what it called
```

**Don't use** `open URL` — that goes to default browser and isn't captured.

## Triggers

Invoke this skill when the user asks about:
- "what API calls", "what endpoint", "what request"
- "show network traffic", "network log", "captured requests"
- "how does this site call", "what backend is it hitting"
- "reverse engineer this API", "discover the API"
- "chrome debug", "capture traffic"

## What Claude Should Know

| Fact | Detail |
|------|--------|
| CDP port | 9222 (Chrome Debug) |
| Status page | http://localhost:9223 |
| Log file | `~/.chrome-debug/logs/requests.jsonl` |
| Capture | Skips binary (images, fonts), truncates bodies >100KB |
| Chrome Debug | Separate profile, inverted icon (cyan/magenta) |

## Commands

```bash
# Lifecycle
chrome-log start              # Start daemon + status page
chrome-log stop               # Stop daemon
chrome-log status             # Running state + stats
chrome-log pause              # Pause capture (sensitive browsing)
chrome-log unpause            # Resume capture
chrome-log doctor             # Health check with fix commands

# Query
chrome-log tail [-n 20]       # Recent requests
chrome-log list [OPTIONS]     # Filtered list
  --filter PATTERN            # URL contains pattern
  --method GET|POST|...       # HTTP method
  --status 2xx|4xx|5xx|CODE   # Status code pattern
  --tab URL                   # Tab URL contains
  --limit N                   # Max results (default 50)
chrome-log show ID            # Full request details
  --headers                   # Include headers
  --body                      # Include response body

# Maintenance
chrome-log clear              # Clear current log
chrome-log clear --older 7d   # Clear old entries
```

## Claude Query Patterns

### Start broad, then drill down

```bash
# 1. Recent traffic overview
chrome-log tail -n 30

# 2. Filter to domain of interest
chrome-log list --filter "api.spotify.com" --limit 20

# 3. Inspect specific request
chrome-log show abc12345 --headers --body
```

### Find API endpoints

```bash
# JSON APIs
chrome-log list --filter "/api/" --method POST --limit 20

# GraphQL
chrome-log list --filter "graphql" --limit 10

# Auth endpoints
chrome-log list --filter "auth\|login\|oauth\|token" --limit 10
```

### Debug errors

```bash
chrome-log list --status 4xx --limit 10   # Client errors
chrome-log list --status 401              # Auth failures
chrome-log list --status 5xx              # Server errors
```

## Workflow: Reverse Engineer a Site

1. **Clear logs**: `chrome-log clear`
2. **Browse target**: Use Chrome Debug, perform the action
3. **Pause**: `chrome-log pause` (prevent noise from other tabs)
4. **Query**:
   ```bash
   chrome-log list --filter "targetdomain.com" --limit 50
   chrome-log show <id> --headers --body
   ```
5. **Document**: Endpoints, auth patterns, request/response shapes

## Status Page

Open http://localhost:9223 for real-time view:
- Live request feed with auto-refresh
- Pause/resume button
- Filter by URL, tab, method
- Click request to expand details
- **Tab shows recording state**: red pulse = recording, amber = paused
- **Tip**: Pin the tab in Chrome Debug - it persists across restarts

## Troubleshooting

Run `chrome-log doctor` - it shows issues with fix commands.

| Issue | Solution |
|-------|----------|
| No requests | Check Chrome Debug is running: `chrome-debug` |
| Connection refused | Start daemon: `chrome-log start` |
| Missing bodies | Binary skipped, >100KB truncated |
| Status page blank | Check daemon: `chrome-log status` |
| Missing cookies | Cookies captured via `Cookie` header and `cookies` field |

## webctl Integration (JS-Rendered Pages)

For JS-rendered pages, combine chrome-log capture with webctl browser control.

### Context Management (Critical)

Both accessibility trees (webctl snapshot) and network logs (chrome-log) can be huge. **Never dump inline without checking size first.**

| Scenario | Pattern |
|----------|---------|
| Targeted queries (buttons, forms, specific text) | Inline with filters |
| Exhaustive analysis (full DOM, all traffic) | File deposit + grep |

### Pattern 1: Targeted Queries (Inline, <50 elements)

webctl has powerful filters that return small, usable output:

```bash
webctl snapshot --count               # Check size FIRST
webctl snapshot --interactive-only    # Just buttons/links/inputs
webctl snapshot --within "role=main"  # Skip nav, footer, ads
webctl snapshot --limit 30            # First 30 elements
webctl snapshot --grep "login"        # Filter by text
```

If `--count` shows <50 elements, inline is fine. Otherwise, use deposit.

### Pattern 2: File Deposit for Large Pages

```bash
# Deposit, don't inline
webctl snapshot > /tmp/page.txt
wc -l /tmp/page.txt                   # See size
grep -i "methodName" /tmp/page.txt    # Query what you need
```

### Pattern 3: Combined webctl + chrome-log

Full workflow for reverse-engineering a JS-rendered site:

```bash
# Setup (once per session)
chrome-debug && chrome-log start
webctl start                          # Connects via CDP

# Navigate and wait for JS
webctl navigate "https://developers.google.com/apps-script/reference/slides/slide"
sleep 3

# Deposit both to files - don't inline large output
webctl snapshot > /tmp/page.txt
chrome-log tail -n 50 > /tmp/traffic.jsonl

# Query files, not inline dumps
wc -l /tmp/page.txt /tmp/traffic.jsonl   # Size check
grep -i "methodName" /tmp/page.txt        # Find specific content
jq 'select(.url | contains("api"))' /tmp/traffic.jsonl  # API calls only
```

### Setup

webctl connects to Chrome Debug via CDP endpoint configured at:
`~/Library/Application Support/webctl/config.json`

```json
{"cdp_endpoint": "http://localhost:9222"}
```

This is maintained in our webctl fork at `~/Repos/webctl`.

## Anti-Patterns

**Don't dump entire log** - always filter:
```bash
# Bad
chrome-log list

# Good
chrome-log list --filter "api" --method POST --limit 10
```

**Pause for sensitive sites** (banking, email):
```bash
chrome-log pause
# Do sensitive browsing
chrome-log unpause
```
