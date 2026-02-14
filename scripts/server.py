#!/usr/bin/env python3
"""
Chrome log status page server.

Serves a live dashboard at localhost:9224 for viewing captured requests.

Usage:
    python server.py [--port 9224]
"""

import argparse
import json
import os
import signal
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

# Paths
CHROME_DEBUG_DIR = Path.home() / '.chrome-debug'
LOG_DIR = CHROME_DEBUG_DIR / 'logs'
LOG_FILE = LOG_DIR / 'requests.jsonl'
PAUSE_FILE = LOG_DIR / '.paused'
ASSETS_DIR = Path(__file__).parent.parent / 'assets'

DEFAULT_PORT = 9224


class StatusHandler(SimpleHTTPRequestHandler):
    """HTTP handler for status page."""

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass

    def send_json(self, data: Any, status: int = 200):
        """Send JSON response."""
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, content: str, status: int = 200):
        """Send HTML response."""
        body = content.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        """Handle GET requests."""
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == '/':
            self.serve_index()
        elif path == '/api/status':
            self.serve_status()
        elif path == '/api/requests':
            self.serve_requests(query)
        elif path == '/api/request':
            self.serve_request_detail(query)
        elif path == '/api/tabs':
            self.serve_tabs()
        else:
            self.send_error(404, 'Not Found')

    def do_POST(self):
        """Handle POST requests."""
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/pause':
            self.handle_pause()
        elif path == '/api/unpause':
            self.handle_unpause()
        else:
            self.send_error(404, 'Not Found')

    def serve_index(self):
        """Serve the main status page."""
        html_file = ASSETS_DIR / 'status.html'
        if html_file.exists():
            self.send_html(html_file.read_text())
        else:
            self.send_html(self.get_fallback_html())

    def serve_status(self):
        """Serve daemon status."""
        is_paused = PAUSE_FILE.exists()

        # Count requests and get log size
        count = 0
        size = 0
        if LOG_FILE.exists():
            size = LOG_FILE.stat().st_size
            with open(LOG_FILE) as f:
                for _ in f:
                    count += 1

        self.send_json({
            'paused': is_paused,
            'requestCount': count,
            'logSize': size
        })

    def serve_requests(self, query: dict):
        """Serve request list."""
        limit = int(query.get('limit', [50])[0])
        offset = int(query.get('offset', [0])[0])
        url_filter = query.get('filter', [None])[0]
        tab_filter = query.get('tab', [None])[0]
        method_filter = query.get('method', [None])[0]

        requests = []
        if LOG_FILE.exists():
            # Read all, then reverse and filter
            all_requests = []
            with open(LOG_FILE) as f:
                for line in f:
                    try:
                        req = json.loads(line)
                        all_requests.append(req)
                    except json.JSONDecodeError:
                        continue

            # Reverse (newest first)
            all_requests.reverse()

            # Filter
            for req in all_requests:
                if url_filter and url_filter.lower() not in req.get('url', '').lower():
                    continue
                if tab_filter and tab_filter.lower() not in req.get('tab', {}).get('url', '').lower():
                    continue
                if method_filter and req.get('method', '').upper() != method_filter.upper():
                    continue
                requests.append(req)

            # Paginate
            requests = requests[offset:offset + limit]

        # Simplify for listing
        simplified = []
        for req in requests:
            simplified.append({
                'id': req.get('id'),
                'ts': req.get('ts'),
                'method': req.get('method'),
                'url': req.get('url'),
                'status': req.get('status'),
                'mime': req.get('mime'),
                'size': req.get('size'),
                'tab': req.get('tab', {}).get('url', '')
            })

        self.send_json(simplified)

    def serve_request_detail(self, query: dict):
        """Serve single request details."""
        request_id = query.get('id', [None])[0]
        if not request_id:
            self.send_json({'error': 'Missing id parameter'}, 400)
            return

        if LOG_FILE.exists():
            with open(LOG_FILE) as f:
                for line in f:
                    try:
                        req = json.loads(line)
                        if req.get('id', '').startswith(request_id):
                            self.send_json(req)
                            return
                    except json.JSONDecodeError:
                        continue

        self.send_json({'error': 'Request not found'}, 404)

    def serve_tabs(self):
        """Serve list of unique tabs."""
        tabs = {}
        if LOG_FILE.exists():
            with open(LOG_FILE) as f:
                for line in f:
                    try:
                        req = json.loads(line)
                        tab = req.get('tab', {})
                        tab_url = tab.get('url', '')
                        if tab_url and tab_url not in tabs:
                            tabs[tab_url] = tab.get('id', '')
                    except json.JSONDecodeError:
                        continue

        self.send_json([{'url': url, 'id': id} for url, id in tabs.items()])

    def handle_pause(self):
        """Handle pause request."""
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        PAUSE_FILE.touch()
        self.send_json({'paused': True})

    def handle_unpause(self):
        """Handle unpause request."""
        if PAUSE_FILE.exists():
            PAUSE_FILE.unlink()
        self.send_json({'paused': False})

    def get_fallback_html(self):
        """Fallback HTML if assets/status.html is missing."""
        return '''<!DOCTYPE html>
<html>
<head>
    <title>Chrome Log Status</title>
    <style>
        body { font-family: system-ui; padding: 20px; background: #1a1a2e; color: #eee; }
        h1 { color: #e94560; }
        .error { color: #e94560; }
    </style>
</head>
<body>
    <h1>Chrome Log Status</h1>
    <p class="error">Status page template not found.</p>
    <p>Expected at: assets/status.html</p>
</body>
</html>'''


def run_server(port: int):
    """Run the status server."""
    server = HTTPServer(('127.0.0.1', port), StatusHandler)
    print(f"Status server running at http://localhost:{port}/")

    def handle_signal(signum, frame):
        print("\nShutting down...")
        server.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description='Chrome log status server')
    parser.add_argument('--port', '-p', type=int, default=DEFAULT_PORT,
                       help=f'Port to listen on (default: {DEFAULT_PORT})')
    args = parser.parse_args()

    run_server(args.port)


if __name__ == '__main__':
    main()
