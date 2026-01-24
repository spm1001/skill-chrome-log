#!/usr/bin/env python3
"""
Chrome network request capture daemon.

Connects to Chrome DevTools Protocol on port 9222, captures all network
requests across all tabs, writes to JSONL file.

Usage:
    python daemon.py [--log-dir DIR]
"""

import argparse
import asyncio
import base64
import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import websockets

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger(__name__)

# Constants
CDP_PORT = 9222
MAX_BODY_SIZE = 100 * 1024  # 100KB
MAX_LOG_SIZE = 50 * 1024 * 1024  # 50MB
MAX_ROTATED_FILES = 3

# Skip these URL patterns (tracking noise)
SKIP_URL_PATTERNS = [
    'google-analytics.com',
    'doubleclick.net',
    'googlesyndication.com',
    'googleadservices.com',
    'play.google.com/log',
    'fonts.googleapis.com',
    'fonts.gstatic.com',
]

# Skip these MIME types (binary)
SKIP_MIME_TYPES = [
    'image/',
    'font/',
    'audio/',
    'video/',
    'application/octet-stream',
    'application/pdf',
    'application/zip',
]


class RequestStore:
    """Temporary storage for in-flight requests."""

    def __init__(self):
        self.requests: dict[str, dict] = {}

    def start_request(self, request_id: str, data: dict):
        self.requests[request_id] = {
            'id': request_id,
            'ts': datetime.now(timezone.utc).isoformat(),
            **data
        }

    def update_request(self, request_id: str, data: dict):
        if request_id in self.requests:
            self.requests[request_id].update(data)

    def complete_request(self, request_id: str) -> dict | None:
        return self.requests.pop(request_id, None)

    def get_request(self, request_id: str) -> dict | None:
        return self.requests.get(request_id)


class ChromeLogDaemon:
    """CDP network capture daemon."""

    def __init__(self, log_dir: Path):
        self.log_dir = log_dir
        self.log_file = log_dir / 'requests.jsonl'
        self.pause_file = log_dir / '.paused'
        self.pid_file = log_dir.parent / '.daemon.pid'
        self.store = RequestStore()
        self.sessions: dict[str, dict] = {}  # session_id -> target_info
        self.running = True
        self.msg_id = 0
        self.pending_commands: dict[int, asyncio.Future] = {}
        self.ws: websockets.WebSocketClientProtocol | None = None

    @property
    def is_paused(self) -> bool:
        return self.pause_file.exists()

    def should_skip_url(self, url: str) -> bool:
        """Check if URL should be skipped (tracking, etc)."""
        return any(pattern in url for pattern in SKIP_URL_PATTERNS)

    def should_skip_mime(self, mime: str | None) -> bool:
        """Check if MIME type should be skipped (binary)."""
        if not mime:
            return False
        return any(mime.startswith(pattern) for pattern in SKIP_MIME_TYPES)

    async def send_command(self, method: str, params: dict = None, session_id: str = None) -> dict:
        """Send CDP command and wait for response."""
        self.msg_id += 1
        msg_id = self.msg_id

        message = {
            'id': msg_id,
            'method': method,
            'params': params or {}
        }
        if session_id:
            message['sessionId'] = session_id

        future = asyncio.get_event_loop().create_future()
        self.pending_commands[msg_id] = future

        await self.ws.send(json.dumps(message))

        try:
            result = await asyncio.wait_for(future, timeout=10.0)
            return result
        except asyncio.TimeoutError:
            self.pending_commands.pop(msg_id, None)
            raise

    async def enable_network(self, session_id: str):
        """Enable network capture for a session."""
        try:
            await self.send_command('Network.enable', {
                'maxTotalBufferSize': 10000000,
                'maxResourceBufferSize': 5000000
            }, session_id)
            log.info(f"Network enabled for session {session_id[:8]}...")
        except Exception as e:
            log.error(f"Failed to enable network for {session_id[:8]}: {e}")

    async def get_response_body(self, request_id: str, session_id: str) -> str | None:
        """Get response body for a request."""
        try:
            result = await self.send_command('Network.getResponseBody', {
                'requestId': request_id
            }, session_id)

            if 'result' in result:
                body = result['result'].get('body', '')
                is_base64 = result['result'].get('base64Encoded', False)

                if is_base64:
                    # Try to decode, skip if too large or binary
                    try:
                        decoded = base64.b64decode(body)
                        if len(decoded) > MAX_BODY_SIZE:
                            return f"[truncated: {len(decoded)} bytes]"
                        # Try to decode as text
                        return decoded.decode('utf-8', errors='replace')
                    except Exception:
                        return "[binary content]"
                else:
                    if len(body) > MAX_BODY_SIZE:
                        return body[:MAX_BODY_SIZE] + f"\n[truncated: {len(body)} bytes total]"
                    return body
        except Exception as e:
            if "No resource with given identifier" not in str(e):
                log.debug(f"Failed to get body for {request_id}: {e}")
        return None

    def write_request(self, request: dict):
        """Write completed request to log file."""
        if self.is_paused:
            return

        # Rotate if needed
        if self.log_file.exists() and self.log_file.stat().st_size > MAX_LOG_SIZE:
            self.rotate_logs()

        with open(self.log_file, 'a') as f:
            f.write(json.dumps(request, default=str) + '\n')

    def rotate_logs(self):
        """Rotate log files."""
        log.info("Rotating log files...")

        # Delete oldest
        oldest = self.log_dir / f'requests.jsonl.{MAX_ROTATED_FILES}'
        if oldest.exists():
            oldest.unlink()

        # Shift existing
        for i in range(MAX_ROTATED_FILES - 1, 0, -1):
            src = self.log_dir / f'requests.jsonl.{i}'
            dst = self.log_dir / f'requests.jsonl.{i + 1}'
            if src.exists():
                src.rename(dst)

        # Rotate current
        if self.log_file.exists():
            self.log_file.rename(self.log_dir / 'requests.jsonl.1')

    def handle_request_will_be_sent(self, params: dict, session_id: str):
        """Handle Network.requestWillBeSent event."""
        request_id = params.get('requestId')
        request = params.get('request', {})
        url = request.get('url', '')

        if self.should_skip_url(url):
            return

        target_info = self.sessions.get(session_id, {})

        self.store.start_request(request_id, {
            'session_id': session_id,
            'tab': {
                'id': target_info.get('targetId', ''),
                'url': target_info.get('url', '')
            },
            'method': request.get('method'),
            'url': url,
            'requestHeaders': dict(request.get('headers', {})),
            'requestBody': request.get('postData')
        })

    def handle_response_received(self, params: dict, session_id: str):
        """Handle Network.responseReceived event."""
        request_id = params.get('requestId')
        response = params.get('response', {})
        mime = response.get('mimeType', '')

        if self.should_skip_mime(mime):
            # Remove from store, don't capture
            self.store.complete_request(request_id)
            return

        self.store.update_request(request_id, {
            'status': response.get('status'),
            'mime': mime,
            'responseHeaders': dict(response.get('headers', {}))
        })

    async def handle_loading_finished(self, params: dict, session_id: str):
        """Handle Network.loadingFinished event."""
        request_id = params.get('requestId')
        encoded_length = params.get('encodedDataLength', 0)

        request = self.store.get_request(request_id)
        if not request:
            return

        request['size'] = encoded_length

        # Try to get response body
        mime = request.get('mime', '')
        if not self.should_skip_mime(mime):
            body = await self.get_response_body(request_id, session_id)
            if body:
                request['responseBody'] = body

        # Complete and write
        completed = self.store.complete_request(request_id)
        if completed:
            # Remove internal session_id from output
            completed.pop('session_id', None)
            self.write_request(completed)

    def handle_loading_failed(self, params: dict, session_id: str):
        """Handle Network.loadingFailed event."""
        request_id = params.get('requestId')
        error = params.get('errorText', 'Unknown error')

        request = self.store.get_request(request_id)
        if request:
            request['error'] = error
            completed = self.store.complete_request(request_id)
            if completed:
                completed.pop('session_id', None)
                self.write_request(completed)

    async def handle_attached_to_target(self, params: dict):
        """Handle Target.attachedToTarget event."""
        session_id = params.get('sessionId')
        target_info = params.get('targetInfo', {})

        if target_info.get('type') != 'page':
            return

        self.sessions[session_id] = target_info
        log.info(f"Attached to: {target_info.get('url', 'unknown')[:60]}")

        await self.enable_network(session_id)

    def handle_detached_from_target(self, params: dict):
        """Handle Target.detachedFromTarget event."""
        session_id = params.get('sessionId')
        target_info = self.sessions.pop(session_id, {})
        log.info(f"Detached from: {target_info.get('url', 'unknown')[:60]}")

    def handle_target_info_changed(self, params: dict):
        """Handle Target.targetInfoChanged event (tab navigation)."""
        target_info = params.get('targetInfo', {})
        target_id = target_info.get('targetId')

        # Update session info for matching target
        for session_id, info in self.sessions.items():
            if info.get('targetId') == target_id:
                self.sessions[session_id] = target_info
                log.debug(f"Target navigated to: {target_info.get('url', '')[:60]}")
                break

    async def handle_message(self, message: str):
        """Handle incoming CDP message."""
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return

        # Handle command responses
        if 'id' in data:
            msg_id = data['id']
            if msg_id in self.pending_commands:
                future = self.pending_commands.pop(msg_id)
                if not future.done():
                    future.set_result(data)
            return

        # Handle events
        method = data.get('method', '')
        params = data.get('params', {})
        session_id = data.get('sessionId', '')

        if method == 'Network.requestWillBeSent':
            self.handle_request_will_be_sent(params, session_id)
        elif method == 'Network.responseReceived':
            self.handle_response_received(params, session_id)
        elif method == 'Network.loadingFinished':
            await self.handle_loading_finished(params, session_id)
        elif method == 'Network.loadingFailed':
            self.handle_loading_failed(params, session_id)
        elif method == 'Target.attachedToTarget':
            await self.handle_attached_to_target(params)
        elif method == 'Target.detachedFromTarget':
            self.handle_detached_from_target(params)
        elif method == 'Target.targetInfoChanged':
            self.handle_target_info_changed(params)

    async def connect(self):
        """Connect to Chrome and start capturing."""
        # Get browser websocket URL
        import urllib.request
        try:
            with urllib.request.urlopen(f'http://localhost:{CDP_PORT}/json/version', timeout=5) as resp:
                version_info = json.loads(resp.read())
                ws_url = version_info.get('webSocketDebuggerUrl')
        except Exception as e:
            log.error(f"Cannot connect to Chrome on port {CDP_PORT}: {e}")
            log.error("Start Chrome with: chrome-debug")
            return

        log.info(f"Connecting to {ws_url}")

        async with websockets.connect(ws_url, max_size=50 * 1024 * 1024) as ws:
            self.ws = ws

            # Enable auto-attach for new targets
            await self.send_command('Target.setAutoAttach', {
                'autoAttach': True,
                'waitForDebuggerOnStart': False,
                'flatten': True
            })

            # Enable target discovery
            await self.send_command('Target.setDiscoverTargets', {
                'discover': True
            })

            # Get existing targets
            result = await self.send_command('Target.getTargets')
            targets = result.get('result', {}).get('targetInfos', [])

            for target in targets:
                if target.get('type') == 'page':
                    try:
                        attach_result = await self.send_command('Target.attachToTarget', {
                            'targetId': target['targetId'],
                            'flatten': True
                        })
                        session_id = attach_result.get('result', {}).get('sessionId')
                        if session_id:
                            self.sessions[session_id] = target
                            await self.enable_network(session_id)
                    except Exception as e:
                        log.warning(f"Failed to attach to {target.get('url', '')[:40]}: {e}")

            log.info(f"Attached to {len(self.sessions)} tabs, capturing...")

            # Message loop
            while self.running:
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    await self.handle_message(message)
                except asyncio.TimeoutError:
                    continue
                except websockets.ConnectionClosed:
                    log.warning("Chrome disconnected")
                    break

    def write_pid(self):
        """Write PID file."""
        self.pid_file.write_text(str(os.getpid()))

    def remove_pid(self):
        """Remove PID file."""
        if self.pid_file.exists():
            self.pid_file.unlink()

    def handle_signal(self, signum, frame):
        """Handle shutdown signals."""
        log.info(f"Received signal {signum}, shutting down...")
        self.running = False

    async def run(self):
        """Main daemon loop."""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.write_pid()

        signal.signal(signal.SIGTERM, self.handle_signal)
        signal.signal(signal.SIGINT, self.handle_signal)

        try:
            while self.running:
                try:
                    await self.connect()
                except Exception as e:
                    log.error(f"Connection error: {e}")

                if self.running:
                    log.info("Reconnecting in 5 seconds...")
                    await asyncio.sleep(5)
        finally:
            self.remove_pid()
            log.info("Daemon stopped")


def main():
    parser = argparse.ArgumentParser(description='Chrome network capture daemon')
    parser.add_argument('--log-dir', type=Path,
                       default=Path.home() / '.chrome-debug' / 'logs',
                       help='Directory for log files')
    args = parser.parse_args()

    daemon = ChromeLogDaemon(args.log_dir)
    asyncio.run(daemon.run())


if __name__ == '__main__':
    main()
