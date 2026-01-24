# How to Get Google Drive Video Summaries

For Claude working with an authenticated Google Workspace MCP.

## Quick Summary

Google Drive generates AI summaries for videos via an internal GenAI API. You need:
1. **File ID** of the video
2. **SAPISID cookie** from an authenticated Google session
3. **POST request** to the streamGenerate endpoint

## The API Call

```python
import hashlib
import json
import random
import time
import requests

def get_video_summary(file_id: str, sapisid: str) -> str:
    """
    Get AI-generated summary for a Google Drive video.

    Args:
        file_id: Drive file ID (from URL: drive.google.com/file/d/{FILE_ID}/...)
        sapisid: SAPISID cookie from authenticated Google session

    Returns:
        Summary text
    """
    # 1. Compute SAPISIDHASH authentication
    origin = "https://drive.google.com"
    timestamp = int(time.time())
    hash_input = f"{timestamp} {sapisid} {origin}"
    hash_value = hashlib.sha1(hash_input.encode()).hexdigest()
    auth = f"SAPISIDHASH {timestamp}_{hash_value}"

    # 2. Build request body (protobuf as JSON array)
    request_id = f"goog_{random.randint(-999999999, -1)}"
    body = [
        [134, None, [
            24, None, None, None, request_id,
            [None, None, None, None, None, None, [0]], "0", None,
            [None, None, None, [[[None, None, None, None, None, None, None,
                [None, None, [None, None, None, [file_id]]]]]]],
            None, None, [29], None, "en-GB",
            None, None, None, None, None, 0,
            *([None] * 20), 0
        ], None, None, [1], 1],
        [1, None, 1]
    ]

    # 3. Make request
    url = "https://appsgenaiserver-pa.clients6.google.com/v1/genai/streamGenerate"
    url += "?key=AIzaSyBPoyoJwz3wa8B8XhHSI6oloJc9K16XSBk"

    headers = {
        "Content-Type": "application/json+protobuf",
        "Authorization": auth,
        "X-Goog-AuthUser": "0",
        "Referer": "https://drive.google.com/",
        "Origin": "https://drive.google.com",
    }

    response = requests.post(url, json=body, headers=headers)

    # 4. Parse streaming response - find longest summary text
    import re
    matches = re.findall(r'"The video[^"]*', response.text)
    if matches:
        longest = max(matches, key=len).strip('"')
        return longest.encode('utf-8').decode('unicode_escape')

    return ""
```

## Getting SAPISID

The SAPISID cookie is set by Google when authenticated. Options:

### Option 1: From Browser (manual)
```bash
# Chrome DevTools → Application → Cookies → .google.com → SAPISID
```

### Option 2: From MCP Cookie Store
If mcp-google-workspace stores cookies, extract SAPISID from there.

### Option 3: Via webctl
```bash
webctl start
webctl navigate "https://drive.google.com"
webctl run "document.cookie.match(/SAPISID=([^;]+)/)?.[1]"
```

## Important Notes

1. **Only works for videos Drive has already processed** - newly uploaded videos may not have summaries yet

2. **The endpoint** `/drive_viewer_video/summarize_proactive_short/v1` appears in the response metadata

3. **Response is streaming** - text builds up incrementally, take the longest match

4. **Undocumented API** - may change without notice

## Example File IDs

From a Drive URL like:
```
https://drive.google.com/file/d/1Pkzue1Y6zhKYI4IhY4ME21xDAZgegeRK/view
```
The file ID is: `1Pkzue1Y6zhKYI4IhY4ME21xDAZgegeRK`

## Response Contains

- **Summary text**: AI-generated description of video content
- **Transcript snippets**: Actual speech from the video with timestamps
- **Suggested prompts**: "List action items", "Show key topics", etc.

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| 401/403 | Bad SAPISID or expired | Get fresh cookie |
| Empty response | Video not processed | Wait for Drive to process |
| "quota exceeded" | Rate limited | Wait and retry |
