# Google Drive Video Summary API (Undocumented)

Reverse-engineered from Chrome network capture, January 2026.

## Overview

Google Drive uses an internal GenAI API to generate video summaries. This is the "Gemini" integration that appears in Drive's video preview.

## Endpoints

Base: `https://appsgenaiserver-pa.clients6.google.com/v1/genai/`

| Endpoint | Purpose |
|----------|---------|
| `/streamGenerate` | Returns the actual summary text (streaming) |
| `/generate` | Returns suggested follow-up prompts |
| `/quotaSummary` | Returns usage quota info |

## Authentication

Uses Google's SAPISIDHASH scheme. Requires:

1. **SAPISID cookie** from an authenticated Google session
2. **Computed hash**: `SHA1(timestamp + " " + SAPISID + " " + origin)`

Header format:
```
Authorization: SAPISIDHASH {timestamp}_{hash} SAPISID1PHASH {timestamp}_{hash} SAPISID3PHASH {timestamp}_{hash}
```

### Computing SAPISIDHASH

```python
import hashlib
import time

def compute_sapisidhash(sapisid: str, origin: str = "https://drive.google.com") -> str:
    timestamp = int(time.time())
    hash_input = f"{timestamp} {sapisid} {origin}"
    hash_value = hashlib.sha1(hash_input.encode()).hexdigest()
    return f"{timestamp}_{hash_value}"
```

## Request Format

Content-Type: `application/json+protobuf`

The body is a nested array (protobuf serialized as JSON). Key structure for video summary:

```python
# Simplified structure - the actual format has many null placeholders
request_body = [
    [
        134,  # Operation type (134 for streamGenerate, 120 for generate)
        None,
        [
            24,  # Sub-operation type
            None, None, None,
            "goog_{random_negative_int}",  # Request ID
            [None, None, None, None, None, None, [0]],
            "0",  # User index
            None,
            [
                None, None, None,
                [[[
                    None, None, None, None, None, None, None,
                    [None, None, [None, None, None, [FILE_ID]]]
                ]]]
            ],
            None, None,
            [29],  # Feature flags? (29 for stream, 3 for generate)
            None,
            "en-GB",  # Locale
            # ... many more nulls ...
        ],
        None, None,
        [1],
        1
    ],
    [1, None, 1]
]
```

### Full Request Template

```python
def build_video_summary_request(file_id: str, locale: str = "en-GB") -> str:
    import random
    import json

    request_id = f"goog_{random.randint(-999999999, -1)}"

    # This is the observed structure for streamGenerate
    body = [
        [
            134,
            None,
            [
                24, None, None, None,
                request_id,
                [None, None, None, None, None, None, [0]],
                "0",
                None,
                [None, None, None, [[[None, None, None, None, None, None, None, [None, None, [None, None, None, [file_id]]]]]]],
                None, None,
                [29],
                None,
                locale,
                None, None, None, None, None,
                0,
                None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,
                0
            ],
            None, None,
            [1],
            1
        ],
        [1, None, 1]
    ]

    return json.dumps(body)
```

## Response Format

### streamGenerate Response

Streaming response with incremental JSON chunks. The text builds up progressively:

```json
// Early chunk:
[[[[[["The video is a deb",[null,null,"The video is a deb"...]]]]]]

// Later chunk (includes previous text + more):
[[[[[["The video is a debriefing meeting for...",[null,null,"..."]]]]]]
```

The response also includes:
- **Transcript snippets** with timestamps
- **File metadata** (name, MIME type, Drive URL)
- **Endpoint path**: `/drive_viewer_video/summarize_proactive_short/v1`

### Parsing Streaming Response

```python
import re

def extract_summary(response_body: str) -> str:
    """Extract the final summary text from streaming response."""
    # Find all progressive text chunks
    pattern = r'"The video[^"]*'
    matches = re.findall(pattern, response_body)

    if matches:
        # Longest match is the final complete text
        longest = max(matches, key=len).strip('"')
        # Decode unicode escapes
        return longest.encode('utf-8').decode('unicode_escape')
    return ""
```

### generate Response (Suggested Prompts)

```json
[
  [
    [
      [
        [null, null, null, null, null,
          [97, [null, null, "List action items"], [null, null, "in this meeting"], ...]
        ],
        [null, null, null, null, null,
          [253, [null, null, "List the meeting agenda"], [null, null, "in this video"], ...]
        ]
      ]
    ]
  ]
]
```

## Required Headers

```python
headers = {
    "Content-Type": "application/json+protobuf",
    "Authorization": f"SAPISIDHASH {sapisidhash}",
    "X-Goog-AuthUser": "0",  # Account index
    "Referer": "https://drive.google.com/",
    "Origin": "https://drive.google.com",
}
```

## API Key

Observed key (may be fixed for Drive): `AIzaSyBPoyoJwz3wa8B8XhHSI6oloJc9K16XSBk`

Append as query param: `?key=AIzaSyBPoyoJwz3wa8B8XhHSI6oloJc9K16XSBk`

## Complete Example

```python
import hashlib
import json
import random
import time
import requests

def get_video_summary(file_id: str, sapisid: str) -> str:
    """
    Get Drive video summary using the internal GenAI API.

    Args:
        file_id: Google Drive file ID
        sapisid: SAPISID cookie value from authenticated session

    Returns:
        Summary text
    """
    # Compute auth
    origin = "https://drive.google.com"
    timestamp = int(time.time())
    hash_input = f"{timestamp} {sapisid} {origin}"
    hash_value = hashlib.sha1(hash_input.encode()).hexdigest()
    sapisidhash = f"{timestamp}_{hash_value}"

    # Build request
    request_id = f"goog_{random.randint(-999999999, -1)}"
    body = [
        [134, None, [
            24, None, None, None, request_id,
            [None, None, None, None, None, None, [0]], "0", None,
            [None, None, None, [[[None, None, None, None, None, None, None,
                [None, None, [None, None, None, [file_id]]]]]]],
            None, None, [29], None, "en-GB",
            None, None, None, None, None, 0,
            None, None, None, None, None, None, None, None, None,
            None, None, None, None, None, None, None, None, None, None, None, 0
        ], None, None, [1], 1],
        [1, None, 1]
    ]

    url = "https://appsgenaiserver-pa.clients6.google.com/v1/genai/streamGenerate"
    url += "?key=AIzaSyBPoyoJwz3wa8B8XhHSI6oloJc9K16XSBk"

    headers = {
        "Content-Type": "application/json+protobuf",
        "Authorization": f"SAPISIDHASH {sapisidhash}",
        "X-Goog-AuthUser": "0",
        "Referer": "https://drive.google.com/",
        "Origin": "https://drive.google.com",
    }

    response = requests.post(url, json=body, headers=headers, stream=True)

    # Parse streaming response
    full_text = ""
    for line in response.iter_lines():
        if line:
            try:
                data = json.loads(line)
                # Extract text from nested structure
                # Structure varies, need to traverse carefully
                pass
            except json.JSONDecodeError:
                continue

    return full_text

# Usage:
# 1. Get SAPISID from browser cookies (chrome://settings/cookies)
# 2. Call: summary = get_video_summary("1Pkzue1Y6zhKYI4IhY4ME21xDAZgegeRK", "YOUR_SAPISID")
```

## Limitations

1. **Authentication**: Requires valid Google session cookies
2. **Undocumented**: May break without notice
3. **Rate limits**: Subject to quota (100 requests shown in quotaSummary)
4. **Video processing**: Only works for videos that Drive has already processed

## Getting SAPISID Cookie

From Chrome DevTools:
1. Go to drive.google.com
2. Open DevTools → Application → Cookies
3. Find `SAPISID` cookie for `.google.com`

Or programmatically via browser automation.

## See Also

- Captured via skill-chrome-log
- File: `~/.chrome-debug/logs/requests.jsonl`
