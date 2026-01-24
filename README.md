# skill-chrome-log

Chrome network request logger for reverse-engineering APIs. Background daemon captures requests; CLI queries efficiently; browser status page provides live view.

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/spm1001/skill-chrome-log
cd skill-chrome-log
./scripts/install.sh

# 2. Source shell config (or restart terminal)
source ~/.zshrc

# 3. Verify installation
chrome-log doctor
```

## Usage

### Start Chrome in Debug Mode

```bash
chrome-debug          # Opens Chrome with debug port enabled
```

This launches Chrome with `--remote-debugging-port=9222` and a separate profile so it doesn't interfere with your regular Chrome.

### Capture Requests

```bash
chrome-log start      # Start daemon (captures in background)
# Browse websites...
chrome-log status     # Check capture status
chrome-log stop       # Stop daemon
```

### Query Logs

```bash
chrome-log tail -n 20                        # Recent requests
chrome-log list --filter "api"               # Filter by URL pattern
chrome-log list --method POST                # Filter by method
chrome-log list --status 4xx                 # Filter by status code
chrome-log list --tab "drive.google.com"     # Filter by tab
chrome-log show <request-id> --headers       # Full request details
chrome-log show <request-id> --body          # Include response body
```

### Live View

Open http://localhost:9223 for a live dashboard with:
- Real-time request feed
- Pause/unpause capture
- Tab filtering
- URL search

### Manage Logs

```bash
chrome-log pause      # Pause capture (daemon keeps running)
chrome-log unpause    # Resume capture
chrome-log clear      # Clear current log
chrome-log clear --older 7d  # Clear logs older than 7 days
```

## How It Works

1. **Chrome Debug Mode**: Chrome runs with remote debugging enabled on port 9222
2. **Daemon**: Connects via Chrome DevTools Protocol (CDP), captures Network events
3. **JSONL Log**: Requests written to `~/.chrome-debug/logs/requests.jsonl`
4. **CLI/Status Page**: Query the log file for analysis

## Requirements

- macOS (uses launchd for daemon management)
- Python 3.11+
- Google Chrome
- ImageMagick (for icon generation during install)

## File Locations

| Path | Purpose |
|------|---------|
| `~/.chrome-debug/` | Chrome debug profile + logs |
| `~/.chrome-debug/logs/requests.jsonl` | Captured requests |
| `~/Applications/Chrome Debug.app` | Debug Chrome launcher (Dock icon) |
| `~/Library/LaunchAgents/local.chrome-log.plist` | Daemon config |

## Troubleshooting

```bash
chrome-log doctor     # Health check with diagnostics
```

Common issues:
- **"Chrome not running in debug mode"**: Launch with `chrome-debug`, not regular Chrome
- **"Cannot connect to port 9222"**: Check if another process is using the port
- **"No requests captured"**: Ensure daemon is running (`chrome-log status`)

## License

MIT
