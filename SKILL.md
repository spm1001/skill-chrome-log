# Chrome Network Logger

Capture and analyze Chrome network requests for reverse-engineering APIs.

## Triggers

- "network log", "capture API", "what requests"
- "reverse engineer", "chrome debug"
- "what API is this using", "how does this site work"

## Prerequisites

Before using this skill:

1. **Chrome Debug must be running**: `chrome-debug` (purple icon in Dock)
2. **Daemon must be started**: `chrome-log start`

Check with: `chrome-log doctor`

## Commands

```bash
# Lifecycle
chrome-log start              # Start capture daemon
chrome-log stop               # Stop daemon
chrome-log status             # Show running state + stats
chrome-log pause              # Pause capture (daemon stays up)
chrome-log unpause            # Resume capture

# Query
chrome-log tail [-n 20]       # Recent requests (summary)
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
chrome-log clear --older 7d   # Clear old rotated logs
chrome-log doctor             # Health check
```

## Claude Query Patterns

### Start with summary, drill into interesting ones

```bash
# 1. Get overview of recent traffic
chrome-log tail -n 30

# 2. Filter to relevant domain
chrome-log list --filter "api.example.com" --limit 20

# 3. Drill into specific request
chrome-log show abc123 --headers --body
```

### Find authentication endpoints

```bash
chrome-log list --filter "auth\|login\|token\|oauth" --method POST
chrome-log list --filter "Authorization" --limit 10  # Requests with auth headers
```

### Discover undocumented APIs

```bash
# Find API-like endpoints
chrome-log list --filter "/api/\|/v1/\|/v2/" --limit 30

# Find JSON responses
chrome-log list --filter ".json\|application/json" --limit 30

# Find POST requests (usually mutations)
chrome-log list --method POST --limit 20
```

### Debug errors

```bash
chrome-log list --status 4xx --limit 20   # Client errors
chrome-log list --status 5xx --limit 20   # Server errors
chrome-log list --status 401              # Auth failures
```

## Live Status Page

Open http://localhost:9223 for real-time view:
- Live request feed (configurable refresh: 2s/5s/10s/manual)
- Pause/unpause button
- Tab filter dropdown
- URL search box
- Click request to expand details

## Anti-Patterns

**Don't dump entire log** — always filter first:
```bash
# Bad: dumps everything
chrome-log list

# Good: focused query
chrome-log list --filter "api" --method POST --limit 10
```

**Don't capture sensitive sites** — pause when logging into banking, etc:
```bash
chrome-log pause
# Do sensitive browsing
chrome-log unpause
```

## Workflow: Reverse Engineer a Site

1. **Start clean**: `chrome-log clear && chrome-log start`
2. **Browse target**: Navigate to the site, perform the action you want to understand
3. **Pause**: `chrome-log pause` (prevents noise from other tabs)
4. **Analyze**:
   ```bash
   chrome-log list --filter "targetdomain.com" --limit 50
   chrome-log show <interesting-id> --headers --body
   ```
5. **Document**: Note the endpoints, auth patterns, request/response shapes

## Log Location

`~/.chrome-debug/logs/requests.jsonl` — append-only, auto-rotates at 50MB (keeps 3 files)

## Troubleshooting

```bash
chrome-log doctor    # Checks Chrome, daemon, permissions
```

| Issue | Solution |
|-------|----------|
| No requests captured | Is Chrome Debug running? (`chrome-debug`) |
| "Connection refused" | Start daemon: `chrome-log start` |
| Missing bodies | Binary responses are skipped; bodies > 100KB truncated |
| Status page blank | Check daemon is running: `chrome-log status` |
