#!/usr/bin/env python3
"""
DaVinci Resolve MCP Server - Claude Integration
Automates video editing via FFmpeg with MCP protocol
"""

import json
import subprocess
import os
import sys
from pathlib import Path
from typing import Any, Optional
import asyncio
import logging

# Fix Windows encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DaVinciMCPServer:
    """MCP-compatible DaVinci Resolve video editor"""

    def __init__(self, work_dir: str = "."):
        self.work_dir = Path(work_dir)
        self.temp_dir = self.work_dir / "temp_clips"
        self.output_dir = self.work_dir / "output"
        self.ffmpeg_exe = self._find_ffmpeg()

        # Create directories
        self.temp_dir.mkdir(exist_ok=True)
        self.output_dir.mkdir(exist_ok=True)

        logger.info(f"DaVinciMCP initialized: {self.work_dir}")
        logger.info(f"FFmpeg: {self.ffmpeg_exe}")

    def _find_ffmpeg(self) -> str:
        """Find FFmpeg executable"""
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
        raise FileNotFoundError("FFmpeg not found in PATH or common locations")

    # ========== MCP TOOLS ==========

    def get_status(self) -> dict:
        """MCP Tool: Get editor status"""
        return {
            "status": "ready",
            "ffmpeg": str(self.ffmpeg_exe),
            "work_dir": str(self.work_dir),
            "output_dir": str(self.output_dir),
            "temp_clips_count": len(list(self.temp_dir.glob("*.mp4")))
        }

    def list_clips(self) -> dict:
        """MCP Tool: List all clips in temp directory"""
        clips = sorted(self.temp_dir.glob("*.mp4"))
        return {
            "clips": [
                {
                    "filename": c.name,
                    "size_mb": c.stat().st_size / (1024*1024),
                    "path": str(c)
                }
                for c in clips
            ]
        }

    def extract_clip(self, video_file: str, start_time: str, end_time: str, output_name: str) -> dict:
        """MCP Tool: Extract a clip from source video"""
        if not Path(video_file).exists():
            return {"error": f"Video file not found: {video_file}"}

        output_path = self.temp_dir / output_name

        cmd = [
            self.ffmpeg_exe, '-y',
            '-ss', start_time,
            '-to', end_time,
            '-i', video_file,
            '-c', 'copy',
            str(output_path)
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                size = output_path.stat().st_size / (1024*1024)
                return {
                    "success": True,
                    "output": output_name,
                    "size_mb": f"{size:.2f}",
                    "start": start_time,
                    "end": end_time
                }
            else:
                return {
                    "error": "FFmpeg failed",
                    "details": result.stderr[:200]
                }
        except subprocess.TimeoutExpired:
            return {"error": "Operation timed out"}

    def concatenate_clips(self, clip_files: list, output_name: str) -> dict:
        """MCP Tool: Concatenate multiple clips"""
        if not clip_files:
            return {"error": "No clips provided"}

        # Create filelist
        filelist_path = self.work_dir / 'filelist.txt'
        try:
            with open(filelist_path, 'w') as f:
                for clip in clip_files:
                    clip_path = self.temp_dir / clip if not Path(clip).is_absolute() else clip
                    if not Path(clip_path).exists():
                        return {"error": f"Clip not found: {clip_path}"}
                    f.write(f"file '{clip_path}'\n")

            output_path = self.output_dir / output_name

            cmd = [
                self.ffmpeg_exe, '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', str(filelist_path),
                '-c', 'copy',
                str(output_path)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            filelist_path.unlink()

            if result.returncode == 0:
                size = output_path.stat().st_size / (1024*1024)
                return {
                    "success": True,
                    "output": output_name,
                    "size_mb": f"{size:.2f}",
                    "clips_merged": len(clip_files),
                    "path": str(output_path)
                }
            else:
                return {
                    "error": "Concatenation failed",
                    "details": result.stderr[:200]
                }
        except Exception as e:
            return {"error": str(e)}

    def add_subtitles(self, video_file: str, srt_file: str, output_name: str) -> dict:
        """MCP Tool: Add subtitles to video"""
        input_path = self.output_dir / video_file if not Path(video_file).is_absolute() else Path(video_file)
        output_path = self.output_dir / output_name

        if not input_path.exists():
            return {"error": f"Video file not found: {input_path}"}
        if not Path(srt_file).exists():
            return {"error": f"Subtitle file not found: {srt_file}"}

        cmd = [
            self.ffmpeg_exe, '-y',
            '-i', str(input_path),
            '-vf', f"subtitles='{srt_file}'",
            '-c:a', 'copy',
            str(output_path)
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                size = output_path.stat().st_size / (1024*1024)
                return {
                    "success": True,
                    "output": output_name,
                    "size_mb": f"{size:.2f}",
                    "subtitles": srt_file
                }
            else:
                return {
                    "error": "Subtitle addition failed",
                    "details": result.stderr[:200]
                }
        except Exception as e:
            return {"error": str(e)}

    def process_editing_config(self, config_file: str, source_video: str) -> dict:
        """MCP Tool: Process complete editing configuration"""
        if not Path(config_file).exists():
            return {"error": f"Config file not found: {config_file}"}
        if not Path(source_video).exists():
            return {"error": f"Source video not found: {source_video}"}

        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            return {"error": f"Failed to load config: {str(e)}"}

        clips_to_concat = []
        processed_clips = []

        # Extract each clip
        for clip in config.get('clips', []):
            if clip.get('type') == 'title_screen':
                continue  # Skip title cards

            clip_num = f"{clip['id']:02d}"
            clip_name = clip['name'].replace(' ', '_').replace('/', '_')
            output_name = f"{clip_num}_{clip_name}.mp4"

            result = self.extract_clip(
                source_video,
                clip.get('source_start', '00:00'),
                clip.get('source_end', '00:10'),
                output_name
            )

            if 'error' in result:
                logger.error(f"Failed to extract {clip['name']}: {result['error']}")
                continue

            clips_to_concat.append(output_name)
            processed_clips.append({
                "name": clip['name'],
                "duration": clip.get('duration', '?'),
                "output": output_name
            })

        # Concatenate
        if clips_to_concat:
            concat_result = self.concatenate_clips(clips_to_concat, 'project_clips_concatenated.mp4')
            if 'error' in concat_result:
                return {"error": f"Concatenation failed: {concat_result['error']}"}

            return {
                "success": True,
                "processed_clips": processed_clips,
                "concatenation": concat_result,
                "output": str(self.output_dir / 'project_clips_concatenated.mp4')
            }
        else:
            return {"error": "No clips were successfully extracted"}

    def get_output_files(self) -> dict:
        """MCP Tool: List all output files"""
        files = sorted(self.output_dir.glob("*.mp4"))
        return {
            "output_files": [
                {
                    "filename": f.name,
                    "size_mb": f"{f.stat().st_size / (1024*1024):.2f}",
                    "path": str(f)
                }
                for f in files
            ]
        }

    def cleanup(self, delete_temp: bool = False) -> dict:
        """MCP Tool: Clean up temporary files"""
        import shutil
        removed = []

        if delete_temp and self.temp_dir.exists():
            try:
                for f in self.temp_dir.glob("*.mp4"):
                    f.unlink()
                    removed.append(f.name)
                shutil.rmtree(self.temp_dir)
                removed.append(f"[Directory: temp_clips]")
            except Exception as e:
                return {"error": f"Cleanup failed: {str(e)}"}

        return {
            "success": True,
            "removed_files": removed,
            "temp_dir_deleted": delete_temp
        }


# ========== MCP PROTOCOL INTERFACE ==========

class MCPInterface:
    """Exposes DaVinciMCP as MCP tools"""

    def __init__(self):
        self.editor = DaVinciMCPServer()
        self.tools = {
            "davinci_get_status": {
                "description": "Get DaVinci Resolve MCP Server status",
                "handler": self.editor.get_status
            },
            "davinci_list_clips": {
                "description": "List all extracted video clips",
                "handler": self.editor.list_clips
            },
            "davinci_extract_clip": {
                "description": "Extract a time range from source video",
                "handler": self.editor.extract_clip,
                "params": ["video_file", "start_time", "end_time", "output_name"]
            },
            "davinci_concatenate": {
                "description": "Concatenate multiple clips into single video",
                "handler": self.editor.concatenate_clips,
                "params": ["clip_files", "output_name"]
            },
            "davinci_add_subtitles": {
                "description": "Add SRT subtitle file to video",
                "handler": self.editor.add_subtitles,
                "params": ["video_file", "srt_file", "output_name"]
            },
            "davinci_process_config": {
                "description": "Process complete editing configuration (extract all clips + concatenate)",
                "handler": self.editor.process_editing_config,
                "params": ["config_file", "source_video"]
            },
            "davinci_get_outputs": {
                "description": "List all output video files",
                "handler": self.editor.get_output_files
            },
            "davinci_cleanup": {
                "description": "Clean up temporary files",
                "handler": self.editor.cleanup,
                "params": ["delete_temp"]
            }
        }

    def list_tools(self) -> dict:
        """MCP: List available tools"""
        return {
            "tools": [
                {
                    "name": name,
                    "description": tool.get("description", ""),
                    "params": tool.get("params", [])
                }
                for name, tool in self.tools.items()
            ]
        }

    def call_tool(self, tool_name: str, **kwargs) -> dict:
        """MCP: Call a tool with arguments"""
        if tool_name not in self.tools:
            return {"error": f"Tool not found: {tool_name}"}

        handler = self.tools[tool_name]["handler"]
        try:
            return handler(**kwargs)
        except TypeError as e:
            return {"error": f"Invalid parameters: {str(e)}"}
        except Exception as e:
            return {"error": f"Tool execution failed: {str(e)}"}


# ========== CLI INTERFACE ==========

def cli():
    """Command-line interface"""
    import argparse

    parser = argparse.ArgumentParser(description='DaVinci Resolve MCP Server')
    parser.add_argument('--list-tools', action='store_true', help='List available MCP tools')
    parser.add_argument('--status', action='store_true', help='Get server status')
    parser.add_argument('--process-config', help='Process editing config file')
    parser.add_argument('--video', help='Source video file')
    parser.add_argument('--list-clips', action='store_true', help='List extracted clips')
    parser.add_argument('--list-outputs', action='store_true', help='List output files')

    args = parser.parse_args()
    mcp = MCPInterface()

    if args.list_tools:
        print(json.dumps(mcp.list_tools(), indent=2, ensure_ascii=False))
    elif args.status:
        print(json.dumps(mcp.editor.get_status(), indent=2, ensure_ascii=False))
    elif args.list_clips:
        print(json.dumps(mcp.editor.list_clips(), indent=2, ensure_ascii=False))
    elif args.list_outputs:
        print(json.dumps(mcp.editor.get_output_files(), indent=2, ensure_ascii=False))
    elif args.process_config and args.video:
        result = mcp.editor.process_editing_config(args.process_config, args.video)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("DaVinci Resolve MCP Server")
        print("Use: python davinci_mcp.py --help")


if __name__ == '__main__':
    cli()
