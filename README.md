# DaVinci Resolve MCP Server

SSE-based MCP (Model Context Protocol) server for video editing automation with FFmpeg. Enables Claude to perform professional video editing tasks including clip extraction, concatenation, and subtitle management.

## Features

✅ **Video Editing Operations**
- Extract clips from source video by timestamp
- Concatenate multiple clips in sequence
- Add SRT/ASS subtitles to videos
- Process complete editing configurations

✅ **MCP Integration**
- Server-Sent Events (SSE) endpoint for real-time communication
- HTTPS/SSL support for secure connections
- RESTful API for direct tool calls

✅ **Hebrew Support**
- Full UTF-8 support for Hebrew subtitles
- Proper text direction handling
- ASS subtitle styling with Hebrew fonts

## Quick Start

```bash
# Install
pip install -r requirements.txt

# Run
python davinci_https_server.py

# Server runs on https://localhost:8443
```

## Add to Claude

```bash
claude mcp add davinci-resolve "https://localhost:8443/sse"
```

## API Endpoints

- `GET /health` - Server status
- `POST /davinci_extract_clip` - Extract video clip
- `POST /davinci_concatenate` - Merge clips
- `POST /davinci_add_subtitles` - Add subtitles
- `POST /davinci_process_config` - Full editing pipeline
- `GET /sse` - Server-Sent Events endpoint

## Documentation

See GitHub repo for full documentation and examples.

---

**Status:** Production Ready ✅  
**Version:** 1.0.0  
**HTTPS:** Enabled  
**SSE:** Enabled
