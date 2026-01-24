#!/usr/bin/env python3
"""
Chrome network log CLI.

Query and manage Chrome network request captures.

Usage:
    chrome-log start              # Start daemon
    chrome-log stop               # Stop daemon
    chrome-log status             # Show status
    chrome-log pause              # Pause capture
    chrome-log unpause            # Resume capture
    chrome-log tail [-n 20]       # Recent requests
    chrome-log list [OPTIONS]     # Filtered list
    chrome-log show ID [OPTIONS]  # Request details
    chrome-log clear [--older Nd] # Clear logs
    chrome-log doctor             # Health check
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

# Paths
CHROME_DEBUG_DIR = Path.home() / '.chrome-debug'
LOG_DIR = CHROME_DEBUG_DIR / 'logs'
LOG_FILE = LOG_DIR / 'requests.jsonl'
PAUSE_FILE = LOG_DIR / '.paused'
PID_FILE = CHROME_DEBUG_DIR / '.daemon.pid'
DAEMON_LOG = LOG_DIR / 'daemon.log'
PLIST_NAME = 'local.chrome-log'
PLIST_PATH = Path.home() / 'Library' / 'LaunchAgents' / f'{PLIST_NAME}.plist'
CDP_PORT = 9222
STATUS_PORT = 9223


def get_script_dir() -> Path:
    """Get the scripts directory."""
    return Path(__file__).parent.resolve()


def is_chrome_debug_running() -> bool:
    """Check if Chrome is running with debug port."""
    try:
        import urllib.request
        with urllib.request.urlopen(f'http://localhost:{CDP_PORT}/json/version', timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def get_daemon_pid() -> int | None:
    """Get daemon PID if running."""
    if not PID_FILE.exists():
        return None
    try:
        pid = int(PID_FILE.read_text().strip())
        # Check if process exists
        os.kill(pid, 0)
        return pid
    except (ValueError, OSError):
        return None


def is_daemon_running() -> bool:
    """Check if daemon is running."""
    return get_daemon_pid() is not None


def is_status_server_running() -> bool:
    """Check if status server is running."""
    try:
        import urllib.request
        with urllib.request.urlopen(f'http://localhost:{STATUS_PORT}/', timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def is_paused() -> bool:
    """Check if capture is paused."""
    return PAUSE_FILE.exists()


def require_chrome_debug() -> bool:
    """Check Chrome is running, print helpful error if not. Returns True if running."""
    if is_chrome_debug_running():
        return True
    print("Chrome Debug is not running.")
    print("Start it with: chrome-debug")
    return False


def require_daemon() -> bool:
    """Check daemon is running, print helpful error if not. Returns True if running."""
    if is_daemon_running():
        return True
    print("Daemon is not running.")
    print("Start it with: chrome-log start")
    return False


def get_log_stats() -> dict:
    """Get log file statistics."""
    stats = {
        'size': 0,
        'count': 0,
        'rotated_files': 0,
        'oldest': None,
        'newest': None
    }

    if LOG_FILE.exists():
        stats['size'] = LOG_FILE.stat().st_size

        # Count requests and get timestamps
        with open(LOG_FILE) as f:
            for line in f:
                stats['count'] += 1
                try:
                    req = json.loads(line)
                    ts = req.get('ts')
                    if ts:
                        if not stats['oldest'] or ts < stats['oldest']:
                            stats['oldest'] = ts
                        if not stats['newest'] or ts > stats['newest']:
                            stats['newest'] = ts
                except json.JSONDecodeError:
                    pass

    # Count rotated files
    for i in range(1, 10):
        if (LOG_DIR / f'requests.jsonl.{i}').exists():
            stats['rotated_files'] += 1
        else:
            break

    return stats


def format_size(size: int) -> str:
    """Format byte size for display."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def read_requests(limit: int = None, reverse: bool = False) -> Iterator[dict]:
    """Read requests from log file."""
    if not LOG_FILE.exists():
        return

    lines = []
    count = 0
    with open(LOG_FILE) as f:
        for line in f:
            try:
                req = json.loads(line)
                if reverse:
                    lines.append(req)
                else:
                    yield req
                    count += 1
                    if limit and count >= limit:
                        break
            except json.JSONDecodeError:
                continue

    if reverse:
        for req in reversed(lines[-limit:] if limit else lines):
            yield req


def filter_requests(
    requests: Iterator[dict],
    url_filter: str = None,
    method: str = None,
    status: str = None,
    tab_filter: str = None
) -> Iterator[dict]:
    """Filter requests by criteria."""
    for req in requests:
        if url_filter and url_filter.lower() not in req.get('url', '').lower():
            continue

        if method and req.get('method', '').upper() != method.upper():
            continue

        if status:
            req_status = req.get('status')
            if status.endswith('xx'):
                # Pattern like 4xx, 5xx
                prefix = status[0]
                if not req_status or not str(req_status).startswith(prefix):
                    continue
            else:
                if req_status != int(status):
                    continue

        if tab_filter:
            tab_url = req.get('tab', {}).get('url', '')
            if tab_filter.lower() not in tab_url.lower():
                continue

        yield req


def format_request_summary(req: dict) -> str:
    """Format request for list display."""
    method = req.get('method', '???')[:7].ljust(7)
    status = str(req.get('status', '---'))[:3].ljust(3)
    url = req.get('url', '')

    # Truncate URL
    if len(url) > 80:
        url = url[:77] + '...'

    # Color status
    if status.startswith('2'):
        status = f"\033[32m{status}\033[0m"  # Green
    elif status.startswith('4'):
        status = f"\033[33m{status}\033[0m"  # Yellow
    elif status.startswith('5'):
        status = f"\033[31m{status}\033[0m"  # Red

    req_id = req.get('id', '')[:8]
    return f"{req_id} {method} {status} {url}"


def format_request_detail(req: dict, show_headers: bool = False, show_body: bool = False) -> str:
    """Format request for detailed display."""
    lines = []

    lines.append(f"ID: {req.get('id', 'unknown')}")
    lines.append(f"Time: {req.get('ts', 'unknown')}")
    lines.append(f"Tab: {req.get('tab', {}).get('url', 'unknown')}")
    lines.append("")
    lines.append(f"{req.get('method', 'GET')} {req.get('url', '')}")
    lines.append(f"Status: {req.get('status', 'unknown')} ({req.get('mime', 'unknown')})")
    lines.append(f"Size: {format_size(req.get('size', 0))}")

    if req.get('error'):
        lines.append(f"Error: {req.get('error')}")

    if show_headers:
        lines.append("")
        lines.append("=== Request Headers ===")
        for k, v in req.get('requestHeaders', {}).items():
            lines.append(f"  {k}: {v}")

        lines.append("")
        lines.append("=== Response Headers ===")
        for k, v in req.get('responseHeaders', {}).items():
            lines.append(f"  {k}: {v}")

    if show_body:
        if req.get('requestBody'):
            lines.append("")
            lines.append("=== Request Body ===")
            lines.append(req.get('requestBody', ''))

        if req.get('responseBody'):
            lines.append("")
            lines.append("=== Response Body ===")
            body = req.get('responseBody', '')
            # Try to pretty-print JSON
            try:
                parsed = json.loads(body)
                lines.append(json.dumps(parsed, indent=2))
            except json.JSONDecodeError:
                lines.append(body)

    return '\n'.join(lines)


# Commands

def cmd_start(args):
    """Start daemon and status server."""
    if is_daemon_running():
        print("Daemon is already running")
        print(f"Status page: http://localhost:{STATUS_PORT}/")
        return 0

    if not require_chrome_debug():
        return 1

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Create launchd plist if needed
    if not PLIST_PATH.exists():
        create_launchd_plist()

    # Load and start via launchd
    subprocess.run(['launchctl', 'load', str(PLIST_PATH)], capture_output=True)
    subprocess.run(['launchctl', 'start', PLIST_NAME], capture_output=True)

    # Kill any stale server on the port
    try:
        result = subprocess.run(
            ['lsof', '-ti', f':{STATUS_PORT}'],
            capture_output=True, text=True
        )
        if result.stdout.strip():
            for pid in result.stdout.strip().split('\n'):
                try:
                    os.kill(int(pid), 9)
                except (ValueError, OSError):
                    pass
            import time
            time.sleep(0.5)
    except Exception:
        pass

    # Start status server
    server_script = get_script_dir() / 'server.py'
    subprocess.Popen(
        [sys.executable, str(server_script)],
        stdout=open(LOG_DIR / 'server.log', 'a'),
        stderr=subprocess.STDOUT,
        start_new_session=True
    )

    print("Daemon started")
    status_url = f"http://localhost:{STATUS_PORT}/"
    print(f"Status page: {status_url}")

    # Auto-open status page unless suppressed
    if not getattr(args, 'no_open', False):
        # Wait briefly for server to start
        import time
        for _ in range(10):
            if is_status_server_running():
                subprocess.run(['open', status_url], capture_output=True)
                break
            time.sleep(0.2)

    return 0


def cmd_stop(args):
    """Stop daemon and status server."""
    stopped = False

    # Stop via launchd
    if PLIST_PATH.exists():
        subprocess.run(['launchctl', 'stop', PLIST_NAME], capture_output=True)
        subprocess.run(['launchctl', 'unload', str(PLIST_PATH)], capture_output=True)
        stopped = True

    # Also kill directly if still running
    pid = get_daemon_pid()
    if pid:
        try:
            os.kill(pid, 15)  # SIGTERM
            stopped = True
        except OSError:
            pass

    # Kill status server
    try:
        result = subprocess.run(
            ['lsof', '-ti', f':{STATUS_PORT}'],
            capture_output=True, text=True
        )
        if result.stdout.strip():
            for pid in result.stdout.strip().split('\n'):
                os.kill(int(pid), 15)
    except Exception:
        pass

    if stopped:
        print("Daemon stopped")
    else:
        print("Daemon was not running")
    return 0


def cmd_status(args):
    """Show daemon status."""
    print("Chrome Log Status")
    print("=" * 40)

    # Chrome
    chrome_ok = is_chrome_debug_running()
    print(f"Chrome Debug:  {'Running' if chrome_ok else 'Not running'}")

    # Daemon
    daemon_pid = get_daemon_pid()
    if daemon_pid:
        print(f"Daemon:        Running (PID {daemon_pid})")
    else:
        print("Daemon:        Not running")

    # Status server
    server_ok = is_status_server_running()
    print(f"Status Page:   {'http://localhost:' + str(STATUS_PORT) + '/' if server_ok else 'Not running'}")

    # Pause state
    print(f"Capture:       {'Paused' if is_paused() else 'Active'}")

    # Log stats
    stats = get_log_stats()
    print("")
    print(f"Requests:      {stats['count']:,}")
    print(f"Log Size:      {format_size(stats['size'])}")
    if stats['rotated_files']:
        print(f"Rotated Files: {stats['rotated_files']}")
    if stats['oldest']:
        print(f"Oldest:        {stats['oldest']}")
    if stats['newest']:
        print(f"Newest:        {stats['newest']}")

    return 0


def cmd_pause(args):
    """Pause capture."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PAUSE_FILE.touch()
    print("Capture paused")
    return 0


def cmd_unpause(args):
    """Resume capture."""
    if PAUSE_FILE.exists():
        PAUSE_FILE.unlink()
    print("Capture resumed")
    return 0


def cmd_tail(args):
    """Show recent requests."""
    if not LOG_FILE.exists():
        if getattr(args, 'json', False):
            print('[]')
        else:
            print("No requests captured yet.")
            if not is_daemon_running():
                print("Daemon is not running. Start with: chrome-log start")
        return 0

    n = args.n or 20
    results = list(read_requests(limit=n, reverse=True))

    if getattr(args, 'json', False):
        print(json.dumps(results, indent=2, default=str))
    else:
        for req in results:
            print(format_request_summary(req))
        if not results:
            print("No requests captured yet")
    return 0


def cmd_list(args):
    """List requests with filtering."""
    limit = args.limit or 50

    requests = read_requests(reverse=True)
    requests = filter_requests(
        requests,
        url_filter=args.filter,
        method=args.method,
        status=args.status,
        tab_filter=args.tab
    )

    # Collect results up to limit
    results = []
    for req in requests:
        results.append(req)
        if len(results) >= limit:
            break

    if getattr(args, 'json', False):
        print(json.dumps(results, indent=2, default=str))
    else:
        for req in results:
            print(format_request_summary(req))
        if not results:
            print("No matching requests")
        elif len(results) >= limit:
            print(f"\n(showing {limit} of more results, use --limit to see more)")

    return 0


def cmd_show(args):
    """Show request details."""
    request_id = args.id

    for req in read_requests():
        if req.get('id', '').startswith(request_id):
            print(format_request_detail(req, args.headers, args.body))
            return 0

    print(f"Request {request_id} not found")
    return 1


def cmd_clear(args):
    """Clear log files."""
    if args.older:
        # Parse duration
        match = re.match(r'(\d+)([dhm])', args.older)
        if not match:
            print("Invalid duration format. Use: 7d, 24h, 30m")
            return 1

        value, unit = int(match.group(1)), match.group(2)
        if unit == 'd':
            delta = timedelta(days=value)
        elif unit == 'h':
            delta = timedelta(hours=value)
        else:
            delta = timedelta(minutes=value)

        cutoff = datetime.now(timezone.utc) - delta

        # Filter current log
        if LOG_FILE.exists():
            temp_file = LOG_FILE.with_suffix('.tmp')
            kept = 0
            removed = 0

            with open(LOG_FILE) as f_in, open(temp_file, 'w') as f_out:
                for line in f_in:
                    try:
                        req = json.loads(line)
                        ts = datetime.fromisoformat(req.get('ts', '').replace('Z', '+00:00'))
                        if ts >= cutoff:
                            f_out.write(line)
                            kept += 1
                        else:
                            removed += 1
                    except (json.JSONDecodeError, ValueError):
                        f_out.write(line)
                        kept += 1

            temp_file.rename(LOG_FILE)
            print(f"Removed {removed} old requests, kept {kept}")

        # Remove old rotated files
        for i in range(1, 10):
            rotated = LOG_DIR / f'requests.jsonl.{i}'
            if rotated.exists():
                rotated.unlink()
                print(f"Removed {rotated.name}")
    else:
        # Clear all
        if LOG_FILE.exists():
            LOG_FILE.unlink()
        for i in range(1, 10):
            rotated = LOG_DIR / f'requests.jsonl.{i}'
            if rotated.exists():
                rotated.unlink()
        print("Logs cleared")

    return 0


def cmd_doctor(args):
    """Health check."""
    print("Chrome Log Doctor")
    print("=" * 40)

    has_issues = False

    # Check Chrome
    if is_chrome_debug_running():
        print("[OK] Chrome running on debug port")
    else:
        print("[!!] Chrome not running in debug mode")
        print("     → Run: chrome-debug")
        has_issues = True

    # Check daemon
    if is_daemon_running():
        print("[OK] Daemon running")
    else:
        print("[!!] Daemon not running")
        print("     → Run: chrome-log start")
        has_issues = True

    # Check status server
    if is_status_server_running():
        print(f"[OK] Status page at http://localhost:{STATUS_PORT}/")
    else:
        print("[--] Status page not running")
        print("     → Will start with daemon")

    # Check log directory
    if LOG_DIR.exists():
        print(f"[OK] Log directory exists: {LOG_DIR}")
    else:
        print(f"[--] Log directory missing: {LOG_DIR}")
        print("     → Will create on first start")

    # Check log file
    if LOG_FILE.exists():
        stats = get_log_stats()
        print(f"[OK] Log file: {stats['count']} requests, {format_size(stats['size'])}")
    else:
        print("[--] No requests captured yet")

    # Check pause state
    if is_paused():
        print("[!!] Capture is PAUSED")
        print("     → Run: chrome-log unpause")
        has_issues = True

    # Check launchd plist
    if PLIST_PATH.exists():
        print("[OK] launchd plist installed")
    else:
        print("[--] launchd plist not installed")
        print("     → Will create on first start")

    print("")
    if has_issues:
        print("Fix the issues above to get started.")
        return 1
    else:
        print("All checks passed!")
        return 0


def create_launchd_plist():
    """Create launchd plist for daemon."""
    script_path = get_script_dir() / 'daemon.py'
    python_path = sys.executable

    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{PLIST_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>{script_path}</string>
    </array>
    <key>RunAtLoad</key>
    <false/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{DAEMON_LOG}</string>
    <key>StandardErrorPath</key>
    <string>{DAEMON_LOG}</string>
</dict>
</plist>
"""

    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(plist_content)


def main():
    parser = argparse.ArgumentParser(
        description='Chrome network log CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # start
    start_parser = subparsers.add_parser('start', help='Start daemon and status server')
    start_parser.add_argument('--no-open', action='store_true', help='Don\'t open status page in browser')

    # stop
    subparsers.add_parser('stop', help='Stop daemon')

    # status
    subparsers.add_parser('status', help='Show status')

    # pause
    subparsers.add_parser('pause', help='Pause capture')

    # unpause
    subparsers.add_parser('unpause', help='Resume capture')

    # tail
    tail_parser = subparsers.add_parser('tail', help='Show recent requests')
    tail_parser.add_argument('-n', type=int, default=20, help='Number of requests')
    tail_parser.add_argument('--json', '-j', action='store_true', help='JSON output')

    # list
    list_parser = subparsers.add_parser('list', help='List requests')
    list_parser.add_argument('--filter', '-f', help='Filter by URL pattern')
    list_parser.add_argument('--method', '-m', help='Filter by HTTP method')
    list_parser.add_argument('--status', '-s', help='Filter by status (200, 4xx, 5xx)')
    list_parser.add_argument('--tab', '-t', help='Filter by tab URL')
    list_parser.add_argument('--limit', '-l', type=int, default=50, help='Max results')
    list_parser.add_argument('--json', '-j', action='store_true', help='JSON output')

    # show
    show_parser = subparsers.add_parser('show', help='Show request details')
    show_parser.add_argument('id', help='Request ID (or prefix)')
    show_parser.add_argument('--headers', '-H', action='store_true', help='Show headers')
    show_parser.add_argument('--body', '-b', action='store_true', help='Show body')

    # clear
    clear_parser = subparsers.add_parser('clear', help='Clear logs')
    clear_parser.add_argument('--older', help='Clear older than (7d, 24h, 30m)')

    # doctor
    subparsers.add_parser('doctor', help='Health check')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    commands = {
        'start': cmd_start,
        'stop': cmd_stop,
        'status': cmd_status,
        'pause': cmd_pause,
        'unpause': cmd_unpause,
        'tail': cmd_tail,
        'list': cmd_list,
        'show': cmd_show,
        'clear': cmd_clear,
        'doctor': cmd_doctor,
    }

    return commands[args.command](args)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted")
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
