#!/usr/bin/env python3
"""
DaVinci Resolve MCP Server - Proper MCP Implementation
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import mcp.types as types
from mcp.server import Server, stdio_server
import mcp.server.models as models

# Fix encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


class DaVinciEditor:
    """Video editing with FFmpeg"""

    def __init__(self):
        self.work_dir = Path.cwd()
        self.temp_dir = self.work_dir / "temp_clips"
        self.output_dir = self.work_dir / "output"
        self.temp_dir.mkdir(exist_ok=True)
        self.output_dir.mkdir(exist_ok=True)
        self.ffmpeg_exe = self._find_ffmpeg()

    def _find_ffmpeg(self) -> str:
        """Find FFmpeg"""
        paths = [
            'ffmpeg',
            r'C:\ffmpeg\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe',
            r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
        ]
        for path in paths:
            try:
                subprocess.run([path, '-version'], capture_output=True, check=True, timeout=2)
                return path
            except:
                continue
        raise FileNotFoundError("FFmpeg not found")

    def extract_clip(self, video_file: str, start: str, end: str, output: str) -> dict:
        """Extract clip"""
        if not Path(video_file).exists():
            return {"error": f"File not found: {video_file}"}

        output_path = self.temp_dir / output
        cmd = [self.ffmpeg_exe, '-y', '-ss', start, '-to', end, '-i', video_file, '-c', 'copy', str(output_path)]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                size = output_path.stat().st_size / (1024*1024)
                return {"success": True, "output": output, "size_mb": f"{size:.2f}"}
            else:
                return {"error": result.stderr[:200]}
        except Exception as e:
            return {"error": str(e)}

    def concatenate(self, clips: list, output: str) -> dict:
        """Concatenate clips"""
        filelist = self.work_dir / 'filelist.txt'
        try:
            with open(filelist, 'w') as f:
                for clip in clips:
                    clip_path = self.temp_dir / clip
                    if not clip_path.exists():
                        return {"error": f"Clip not found: {clip}"}
                    f.write(f"file '{clip_path}'\n")

            output_path = self.output_dir / output
            cmd = [self.ffmpeg_exe, '-y', '-f', 'concat', '-safe', '0', '-i', str(filelist), '-c', 'copy', str(output_path)]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            filelist.unlink()

            if result.returncode == 0:
                size = output_path.stat().st_size / (1024*1024)
                return {"success": True, "output": output, "size_mb": f"{size:.2f}", "clips": len(clips)}
            else:
                return {"error": result.stderr[:200]}
        except Exception as e:
            return {"error": str(e)}

    def add_subtitles(self, video: str, srt: str, output: str) -> dict:
        """Add subtitles"""
        video_path = self.output_dir / video if not Path(video).is_absolute() else Path(video)
        if not video_path.exists():
            return {"error": f"Video not found: {video_path}"}
        if not Path(srt).exists():
            return {"error": f"SRT not found: {srt}"}

        output_path = self.output_dir / output
        cmd = [self.ffmpeg_exe, '-y', '-i', str(video_path), '-vf', f"subtitles='{srt}'", '-c:a', 'copy', str(output_path)]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                size = output_path.stat().st_size / (1024*1024)
                return {"success": True, "output": output, "size_mb": f"{size:.2f}"}
            else:
                return {"error": result.stderr[:200]}
        except Exception as e:
            return {"error": str(e)}

    def process_config(self, config_file: str, source: str) -> dict:
        """Process editing config"""
        if not Path(config_file).exists():
            return {"error": f"Config not found: {config_file}"}
        if not Path(source).exists():
            return {"error": f"Video not found: {source}"}

        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            return {"error": f"Config load failed: {str(e)}"}

        clips_to_concat = []
        processed = []

        for clip in config.get('clips', []):
            if clip.get('type') == 'title_screen':
                continue

            clip_num = f"{clip['id']:02d}"
            clip_name = clip['name'].replace(' ', '_').replace('/', '_')
            output_name = f"{clip_num}_{clip_name}.mp4"

            result = self.extract_clip(
                source,
                clip.get('source_start', '00:00'),
                clip.get('source_end', '00:10'),
                output_name
            )

            if 'error' not in result:
                clips_to_concat.append(output_name)
                processed.append({"name": clip['name'], "output": output_name})

        if clips_to_concat:
            concat_result = self.concatenate(clips_to_concat, 'project_clips_concatenated.mp4')
            if 'error' in concat_result:
                return {"error": f"Concatenation failed: {concat_result['error']}"}

            return {
                "success": True,
                "processed": len(processed),
                "concatenated": concat_result.get('output'),
                "size_mb": concat_result.get('size_mb')
            }
        else:
            return {"error": "No clips extracted"}

    def list_clips(self) -> dict:
        """List clips"""
        clips = sorted(self.temp_dir.glob("*.mp4"))
        return {
            "clips": [
                {"name": c.name, "size_mb": f"{c.stat().st_size / (1024*1024):.2f}"}
                for c in clips
            ]
        }

    def list_outputs(self) -> dict:
        """List outputs"""
        files = sorted(self.output_dir.glob("*.mp4"))
        return {
            "files": [
                {"name": f.name, "size_mb": f"{f.stat().st_size / (1024*1024):.2f}"}
                for f in files
            ]
        }

    def get_status(self) -> dict:
        """Server status"""
        return {
            "status": "ready",
            "ffmpeg": str(self.ffmpeg_exe),
            "work_dir": str(self.work_dir),
            "temp_clips": len(list(self.temp_dir.glob("*.mp4"))),
            "output_files": len(list(self.output_dir.glob("*.mp4")))
        }


# ========== MCP SERVER ==========

server = Server("davinci-resolve")
editor = DaVinciEditor()


@server.list_tools()
async def list_tools():
    """List available tools"""
    return [
        types.Tool(
            name="davinci_get_status",
            description="Get DaVinci MCP server status",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        types.Tool(
            name="davinci_extract_clip",
            description="Extract a time range from video",
            inputSchema={
                "type": "object",
                "properties": {
                    "video_file": {"type": "string", "description": "Source video file"},
                    "start_time": {"type": "string", "description": "Start time (HH:MM:SS)"},
                    "end_time": {"type": "string", "description": "End time (HH:MM:SS)"},
                    "output_name": {"type": "string", "description": "Output filename"}
                },
                "required": ["video_file", "start_time", "end_time", "output_name"]
            }
        ),
        types.Tool(
            name="davinci_concatenate",
            description="Merge multiple clips into one video",
            inputSchema={
                "type": "object",
                "properties": {
                    "clips": {"type": "array", "items": {"type": "string"}, "description": "List of clip filenames"},
                    "output_name": {"type": "string", "description": "Output filename"}
                },
                "required": ["clips", "output_name"]
            }
        ),
        types.Tool(
            name="davinci_add_subtitles",
            description="Add SRT subtitles to video",
            inputSchema={
                "type": "object",
                "properties": {
                    "video_file": {"type": "string", "description": "Video file"},
                    "srt_file": {"type": "string", "description": "SRT subtitle file"},
                    "output_name": {"type": "string", "description": "Output filename"}
                },
                "required": ["video_file", "srt_file", "output_name"]
            }
        ),
        types.Tool(
            name="davinci_process_config",
            description="Process complete editing configuration",
            inputSchema={
                "type": "object",
                "properties": {
                    "config_file": {"type": "string", "description": "editing_config.json path"},
                    "source_video": {"type": "string", "description": "Source video file"}
                },
                "required": ["config_file", "source_video"]
            }
        ),
        types.Tool(
            name="davinci_list_clips",
            description="List all extracted clips",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        types.Tool(
            name="davinci_list_outputs",
            description="List all output videos",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> str:
    """Handle tool calls"""
    try:
        if name == "davinci_get_status":
            result = editor.get_status()
        elif name == "davinci_extract_clip":
            result = editor.extract_clip(
                arguments["video_file"],
                arguments["start_time"],
                arguments["end_time"],
                arguments["output_name"]
            )
        elif name == "davinci_concatenate":
            result = editor.concatenate(arguments["clips"], arguments["output_name"])
        elif name == "davinci_add_subtitles":
            result = editor.add_subtitles(
                arguments["video_file"],
                arguments["srt_file"],
                arguments["output_name"]
            )
        elif name == "davinci_process_config":
            result = editor.process_config(arguments["config_file"], arguments["source_video"])
        elif name == "davinci_list_clips":
            result = editor.list_clips()
        elif name == "davinci_list_outputs":
            result = editor.list_outputs()
        else:
            result = {"error": f"Unknown tool: {name}"}

        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


async def main():
    """Run MCP server"""
    async with stdio_server(server) as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            models.InitializationOptions(
                server_name="davinci-resolve",
                server_version="1.0.0",
                capabilities=models.ServerCapabilities(
                    tools=models.ToolsCapability(list_changed=False)
                ),
            ),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
