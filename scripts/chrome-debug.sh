#!/bin/bash
#
# Launch Chrome in debug mode with remote debugging enabled.
#
# This script:
# 1. Uses a separate Chrome profile (~/.chrome-debug/Default)
# 2. Enables remote debugging on port 9222
# 3. Runs Chrome in the background
# 4. Opens status page if this is a fresh launch
#
# Usage:
#   chrome-debug          # Launch Chrome
#   chrome-debug --check  # Check if already running
#

set -e

CHROME_APP="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DEBUG_PORT=9222
STATUS_PORT=9224
USER_DATA_DIR="$HOME/.chrome-debug"

# Check if Chrome is already running in debug mode
check_running() {
    if curl -s "http://localhost:$DEBUG_PORT/json/version" > /dev/null 2>&1; then
        echo "Chrome is already running in debug mode (port $DEBUG_PORT)"
        return 0
    else
        return 1
    fi
}

# Main
if [[ "$1" == "--check" ]]; then
    if check_running; then
        exit 0
    else
        echo "Chrome is not running in debug mode"
        exit 1
    fi
fi

# Check if already running
if check_running; then
    exit 0
fi

# Create user data directory if needed
mkdir -p "$USER_DATA_DIR"

# Launch Chrome
echo "Starting Chrome in debug mode..."
"$CHROME_APP" \
    --remote-debugging-port=$DEBUG_PORT \
    --user-data-dir="$USER_DATA_DIR" \
    --no-first-run \
    --no-default-browser-check \
    > /dev/null 2>&1 &

# Wait for it to be ready
for i in {1..30}; do
    if check_running; then
        echo "Chrome started on port $DEBUG_PORT"
        # Start daemon (status page can be pinned - persists across restarts)
        "$HOME/.claude/scripts/chrome-log" start --no-open 2>/dev/null &
        exit 0
    fi
    sleep 0.5
done

echo "Failed to start Chrome in debug mode"
exit 1
