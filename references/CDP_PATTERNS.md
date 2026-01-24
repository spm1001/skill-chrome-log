# CDP Patterns Reference

Chrome DevTools Protocol patterns used in this project.

## Connection

```python
import asyncio
from cdp import open_cdp

async def connect():
    async with open_cdp("http://localhost:9222") as conn:
        # conn is the browser connection
        targets = await conn.send(target.get_targets())
```

## Network Domain

### Enable network capture

```python
from cdp import network

# Enable with options
await session.send(network.enable(
    max_total_buffer_size=10000000,  # 10MB buffer
    max_resource_buffer_size=5000000  # 5MB per resource
))
```

### Key events

```python
# Request sent
@session.listen(network.RequestWillBeSent)
async def on_request(event):
    event.request_id
    event.request.url
    event.request.method
    event.request.headers
    event.request.post_data  # POST body

# Response received
@session.listen(network.ResponseReceived)
async def on_response(event):
    event.request_id
    event.response.url
    event.response.status
    event.response.headers
    event.response.mime_type

# Loading finished (body available)
@session.listen(network.LoadingFinished)
async def on_finished(event):
    event.request_id
    event.encoded_data_length

    # Now we can get body
    body = await session.send(network.get_response_body(event.request_id))
    body.body  # The actual content
    body.base64_encoded  # True if binary
```

## Target Domain (Multi-tab)

### Auto-attach to new targets

```python
from cdp import target

# Enable auto-attach
await conn.send(target.set_auto_attach(
    auto_attach=True,
    wait_for_debugger_on_start=False,
    flatten=True  # Flat session IDs
))

# Listen for new targets
@conn.listen(target.AttachedToTarget)
async def on_attached(event):
    session_id = event.session_id
    target_info = event.target_info
    # Enable network on this new session
```

### Get all pages

```python
targets = await conn.send(target.get_targets())
pages = [t for t in targets.target_infos if t.type_ == "page"]
```

## Session Management

```python
# Create session for a target
session_id = await conn.send(target.attach_to_target(
    target_id=target_info.target_id,
    flatten=True
))

# Send command to specific session
await conn.send(network.enable(), session_id=session_id)
```

## Error Handling

```python
from cdp.exceptions import CDPError

try:
    body = await session.send(network.get_response_body(request_id))
except CDPError as e:
    if "No resource with given identifier" in str(e):
        # Response body not available (redirects, etc)
        pass
```

## Common Gotchas

1. **Response body timing**: Must wait for `LoadingFinished` before calling `get_response_body`
2. **Session scope**: Network events are per-session, not global
3. **Redirect handling**: Redirects may not have bodies available
4. **WebSocket**: Use `Fetch` domain for WebSocket interception, not `Network`
5. **Service workers**: May intercept requests; consider `Fetch` domain

## Useful CDP Domains

| Domain | Purpose |
|--------|---------|
| Network | HTTP request/response capture |
| Target | Tab/target management |
| Fetch | Request interception (modify requests) |
| Runtime | JavaScript execution |
| Page | Page lifecycle, navigation |
| DOM | DOM inspection |
