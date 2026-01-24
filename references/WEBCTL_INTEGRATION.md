# webctl + chrome-log Integration

Combining browser automation (webctl) with traffic capture (chrome-log) to read JS-rendered documentation.

## Why This Exists

Google's Apps Script documentation (and many other modern docs) are JS-rendered. `curl` gets empty shells. `WebFetch` gets summaries. You need a real browser to see the actual content.

**The combo:**
- **Chrome Debug** — Browser instance with CDP port exposed (9222)
- **chrome-log** — Captures all network traffic from Chrome Debug
- **webctl** — Drives the browser: navigate, click, snapshot DOM

Together: navigate to a page, get the rendered DOM, see what API calls it made.

## Setup (One-Time)

### 1. Configure webctl to use Chrome Debug

```bash
cat > "/Users/modha/Library/Application Support/webctl/config.json" << 'EOF'
{"cdp_endpoint": "http://localhost:9222"}
EOF
```

This tells webctl to connect to an existing Chrome Debug instance instead of launching its own browser.

### 2. Verify the tools exist

```bash
command -v chrome-debug && echo "OK" || echo "MISSING: chrome-debug"
command -v chrome-log && echo "OK" || echo "MISSING: chrome-log"
command -v webctl && echo "OK" || echo "MISSING: webctl"
```

## The Workflow

**Order matters.** Chrome Debug first, chrome-log second (to attach), webctl last.

```bash
# 1. Start Chrome Debug (if not running)
chrome-debug

# 2. Start traffic capture
chrome-log start

# 3. Connect webctl to Chrome Debug
webctl start

# 4. Navigate to target page
webctl navigate "https://developers.google.com/apps-script/reference/slides/slide"

# 5. Wait for JS to render (important!)
sleep 3

# 6. Get rendered DOM
webctl snapshot > /tmp/page-snapshot.txt

# 7. Query the snapshot (not inline — saves context)
grep -i "getBackground\|setPicture\|insertImage" /tmp/page-snapshot.txt

# 8. Check what API calls the page made (optional)
chrome-log list --filter "developers.google.com" --limit 10

# 9. Clean up when done
webctl stop --daemon
```

## The "Deposit and Grep" Pattern

**Problem:** `webctl snapshot` outputs 100+ lines of accessibility tree nodes. Dumping this inline burns context fast.

**Solution:** Write to file, grep for what you need.

```bash
# BAD — floods context
webctl snapshot

# GOOD — deposit, then query
webctl snapshot > /tmp/snapshot.txt
grep -i "methodName" /tmp/snapshot.txt | head -20
```

### Useful grep patterns for Google docs

```bash
# Find method signatures
grep -E "^\s+[a-z]+\(" /tmp/snapshot.txt

# Find class names
grep -i "class.*{" /tmp/snapshot.txt

# Find specific API methods
grep -i "setPictureFill\|insertImage\|getBackground" /tmp/snapshot.txt
```

## What Each Tool Provides

| Tool | Capability | Key Commands |
|------|-----------|--------------|
| **chrome-debug** | Browser with CDP exposed | Just `chrome-debug` to launch |
| **chrome-log** | Traffic capture + query | `start`, `tail`, `list --filter`, `show` |
| **webctl** | Browser automation | `navigate`, `snapshot`, `click`, `type` |

### webctl commands for reading docs

```bash
webctl navigate URL          # Go to page
webctl snapshot              # Get accessibility tree (rendered DOM)
webctl click "role=button"   # Click elements
webctl scroll down           # Scroll for lazy-loaded content
webctl pages                 # List open tabs
```

### chrome-log queries after navigation

```bash
# What XHR/fetch calls did the page make?
chrome-log list --filter "api" --method POST --limit 10

# Full details of a request
chrome-log show <request-id> --headers --body
```

## Use Cases

### Reading Google Apps Script Reference

```bash
chrome-debug && chrome-log start
webctl start
webctl navigate "https://developers.google.com/apps-script/reference/slides/slide"
sleep 3
webctl snapshot > /tmp/slides-api.txt
grep -i "method\|function" /tmp/slides-api.txt | head -50
```

### Comparing SlidesApp vs REST API

```bash
# Page 1: SlidesApp (Apps Script)
webctl navigate "https://developers.google.com/apps-script/reference/slides/slide"
sleep 3
webctl snapshot > /tmp/slidesapp.txt

# Page 2: REST API
webctl navigate "https://developers.google.com/slides/api/reference/rest/v1/presentations/batchUpdate"
sleep 3
webctl snapshot > /tmp/rest-api.txt

# Compare method names
diff <(grep -oE '[a-z]+\(' /tmp/slidesapp.txt | sort -u) \
     <(grep -oE '[a-z]+\(' /tmp/rest-api.txt | sort -u)
```

### Finding undocumented API endpoints

```bash
chrome-log clear
webctl navigate "https://some-app.google.com"
# Interact with the app...
chrome-log list --filter "api\|rpc\|batch" --limit 30
```

## Fragility Warning

**The cdp_endpoint config is a local modification to webctl.** It was added by editing the uv-installed package directly:

```
/Users/modha/.local/share/uv/tools/webctl/.../webctl/config.py
/Users/modha/.local/share/uv/tools/webctl/.../webctl/daemon/session_manager.py
```

**This will be lost on `uv tool upgrade webctl`.**

### Before upgrading webctl

1. Check if the fork exists: `ls ~/Repos/webctl`
2. If not, create it first (bead `itv-slides-formatter-fs4` tracks this)
3. Then upgrade: `uv tool install ~/Repos/webctl`

### The modification (for reference)

In `config.py`:
```python
cdp_endpoint: str | None = None
```

In `session_manager.py` `create_session()`:
```python
if self.config.cdp_endpoint:
    browser = await playwright.chromium.connect_over_cdp(self.config.cdp_endpoint)
    context = browser.contexts[0]  # Use existing context
else:
    # ... normal launch
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `webctl start` launches new browser | cdp_endpoint not configured | Create config.json per setup |
| "Connection refused" on webctl start | Chrome Debug not running | Run `chrome-debug` first |
| Empty snapshot | Page still loading | Add `sleep 3` before snapshot |
| No traffic in chrome-log | chrome-log started after navigation | Start chrome-log before webctl |
| Snapshot floods context | Not using deposit pattern | Write to file, grep for relevant bits |

## Session Cleanup

```bash
webctl stop --daemon    # Disconnect from Chrome Debug
chrome-log stop         # Stop capture daemon (optional)
# Chrome Debug can stay running
```

Don't stop Chrome Debug between navigations — it's your persistent browser session with cookies/auth.
