#!/usr/bin/env python3
"""
DaVinci Resolve MCP Server - official MCP protocol (SSE transport)
Video editing tools backed by FFmpeg.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# Fix encoding on Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from mcp.server.fastmcp import FastMCP


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
        paths = [
            'ffmpeg',
            r'C:\ffmpeg\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe',
            r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
        ]
        for path in paths:
            try:
                subprocess.run([path, '-version'], capture_output=True, check=True, timeout=5)
                return path
            except Exception:
                continue
        raise FileNotFoundError("FFmpeg not found")

    def _resolve(self, video: str) -> Path:
        p = Path(video)
        if p.is_absolute():
            return p
        for base in (self.output_dir, self.temp_dir, self.work_dir):
            candidate = base / video
            if candidate.exists():
                return candidate
        return self.output_dir / video

    def _run(self, cmd: list, timeout: int = 300) -> dict:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if result.returncode == 0:
                return {"success": True}
            return {"error": result.stderr[-500:]}
        except Exception as e:
            return {"error": str(e)}


editor = DaVinciEditor()

port = int(os.environ.get("PORT", "8443"))
mcp = FastMCP("DaVinci Resolve", host="0.0.0.0", port=port, stateless_http=True)


@mcp.tool()
def davinci_status() -> str:
    """Get server status, FFmpeg availability and list of clips/outputs."""
    return json.dumps({
        "status": "ready",
        "ffmpeg": str(editor.ffmpeg_exe),
        "work_dir": str(editor.work_dir),
        "temp_clips": [c.name for c in sorted(editor.temp_dir.glob("*.mp4"))],
        "output_files": [f.name for f in sorted(editor.output_dir.glob("*.mp4"))],
    }, ensure_ascii=False)


@mcp.tool()
def extract_clip(video_file: str, start_time: str, end_time: str, output_name: str) -> str:
    """Extract a clip from a video between start_time and end_time (HH:MM:SS)."""
    if not Path(video_file).exists():
        return json.dumps({"error": f"File not found: {video_file}"})
    output_path = editor.temp_dir / output_name
    r = editor._run([editor.ffmpeg_exe, '-y', '-ss', start_time, '-to', end_time,
                     '-i', video_file, '-c', 'copy', str(output_path)])
    if r.get("success"):
        size = output_path.stat().st_size / (1024 * 1024)
        return json.dumps({"success": True, "output": output_name, "size_mb": f"{size:.2f}"})
    return json.dumps(r)


@mcp.tool()
def concatenate(clips: list[str], output_name: str) -> str:
    """Concatenate clips (from temp_clips dir) into one video in output dir."""
    filelist = editor.work_dir / 'filelist.txt'
    try:
        with open(filelist, 'w') as f:
            for clip in clips:
                clip_path = editor.temp_dir / clip
                if not clip_path.exists():
                    return json.dumps({"error": f"Clip not found: {clip}"})
                f.write(f"file '{clip_path}'\n")
        output_path = editor.output_dir / output_name
        r = editor._run([editor.ffmpeg_exe, '-y', '-f', 'concat', '-safe', '0',
                         '-i', str(filelist), '-c', 'copy', str(output_path)])
        filelist.unlink(missing_ok=True)
        if r.get("success"):
            size = output_path.stat().st_size / (1024 * 1024)
            return json.dumps({"success": True, "output": output_name,
                               "size_mb": f"{size:.2f}", "clips": len(clips)})
        return json.dumps(r)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def add_subtitles(video_file: str, srt_file: str, output_name: str) -> str:
    """Burn subtitles (SRT/ASS file) into a video."""
    video_path = editor._resolve(video_file)
    if not video_path.exists():
        return json.dumps({"error": f"Video not found: {video_path}"})
    if not Path(srt_file).exists():
        return json.dumps({"error": f"Subtitle file not found: {srt_file}"})
    output_path = editor.output_dir / output_name
    srt_escaped = str(srt_file).replace('\\', '/').replace(':', '\\:')
    r = editor._run([editor.ffmpeg_exe, '-y', '-i', str(video_path),
                     '-vf', f"subtitles='{srt_escaped}'", '-c:a', 'copy', str(output_path)])
    if r.get("success"):
        size = output_path.stat().st_size / (1024 * 1024)
        return json.dumps({"success": True, "output": output_name, "size_mb": f"{size:.2f}"})
    return json.dumps(r)


@mcp.tool()
def add_text_overlay(video_file: str, text: str, x: str, y: str, output_name: str,
                     fontsize: int = 48, fontcolor: str = "white") -> str:
    """Add a text overlay at position x,y (e.g. x='(w-text_w)/2', y='50')."""
    video_path = editor._resolve(video_file)
    if not video_path.exists():
        return json.dumps({"error": f"Video not found: {video_path}"})
    output_path = editor.output_dir / output_name
    drawtext = f"drawtext=text='{text}':fontsize={fontsize}:fontcolor={fontcolor}:x={x}:y={y}"
    r = editor._run([editor.ffmpeg_exe, '-y', '-i', str(video_path),
                     '-vf', drawtext, '-c:a', 'copy', str(output_path)])
    if r.get("success"):
        size = output_path.stat().st_size / (1024 * 1024)
        return json.dumps({"success": True, "output": output_name, "size_mb": f"{size:.2f}"})
    return json.dumps(r)


@mcp.tool()
def add_fade(video_file: str, fade_type: str, start_seconds: float, duration_seconds: float,
             output_name: str) -> str:
    """Add fade effect. fade_type is 'in' or 'out'."""
    video_path = editor._resolve(video_file)
    if not video_path.exists():
        return json.dumps({"error": f"Video not found: {video_path}"})
    output_path = editor.output_dir / output_name
    fade_filter = f"fade=t={'in' if fade_type == 'in' else 'out'}:st={start_seconds}:d={duration_seconds}"
    r = editor._run([editor.ffmpeg_exe, '-y', '-i', str(video_path),
                     '-vf', fade_filter, '-c:a', 'copy', str(output_path)])
    if r.get("success"):
        size = output_path.stat().st_size / (1024 * 1024)
        return json.dumps({"success": True, "output": output_name, "size_mb": f"{size:.2f}"})
    return json.dumps(r)


@mcp.tool()
def get_video_info(video_file: str) -> str:
    """Get video metadata (duration, resolution, codecs)."""
    video_path = editor._resolve(video_file)
    if not video_path.exists():
        return json.dumps({"error": f"File not found: {video_path}"})
    try:
        result = subprocess.run([editor.ffmpeg_exe, '-i', str(video_path)],
                                capture_output=True, text=True, timeout=15)
        return json.dumps({"success": True, "info": result.stderr[-1500:], "file": str(video_path)},
                          ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def extract_audio(video_file: str, output_name: str) -> str:
    """Extract audio track from a video (e.g. to MP3)."""
    video_path = editor._resolve(video_file)
    if not video_path.exists():
        return json.dumps({"error": f"Video not found: {video_path}"})
    output_path = editor.output_dir / output_name
    r = editor._run([editor.ffmpeg_exe, '-y', '-i', str(video_path),
                     '-q:a', '0', '-map', 'a', str(output_path)])
    if r.get("success"):
        size = output_path.stat().st_size / (1024 * 1024)
        return json.dumps({"success": True, "output": output_name, "size_mb": f"{size:.2f}"})
    return json.dumps(r)


@mcp.tool()
def resize_video(video_file: str, width: int, height: int, output_name: str) -> str:
    """Resize/scale a video to width x height."""
    video_path = editor._resolve(video_file)
    if not video_path.exists():
        return json.dumps({"error": f"Video not found: {video_path}"})
    output_path = editor.output_dir / output_name
    r = editor._run([editor.ffmpeg_exe, '-y', '-i', str(video_path),
                     '-vf', f"scale={width}:{height}", '-c:a', 'copy', str(output_path)])
    if r.get("success"):
        size = output_path.stat().st_size / (1024 * 1024)
        return json.dumps({"success": True, "output": output_name, "size_mb": f"{size:.2f}"})
    return json.dumps(r)


@mcp.tool()
def adjust_speed(video_file: str, speed: float, output_name: str) -> str:
    """Change playback speed (e.g. 1.5 = 50% faster, 0.5 = half speed)."""
    video_path = editor._resolve(video_file)
    if not video_path.exists():
        return json.dumps({"error": f"Video not found: {video_path}"})
    output_path = editor.output_dir / output_name
    r = editor._run([editor.ffmpeg_exe, '-y', '-i', str(video_path),
                     '-filter:v', f"setpts={1/speed}*PTS", '-filter:a', f"atempo={speed}",
                     str(output_path)])
    if r.get("success"):
        size = output_path.stat().st_size / (1024 * 1024)
        return json.dumps({"success": True, "output": output_name, "size_mb": f"{size:.2f}"})
    return json.dumps(r)


@mcp.tool()
def process_config(config_file: str, source_video: str) -> str:
    """Process an editing config JSON: extract all defined clips and concatenate them."""
    if not Path(config_file).exists():
        return json.dumps({"error": f"Config not found: {config_file}"})
    if not Path(source_video).exists():
        return json.dumps({"error": f"Video not found: {source_video}"})
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        return json.dumps({"error": f"Config load failed: {e}"})

    clips_to_concat = []
    for clip in config.get('clips', []):
        if clip.get('type') == 'title_screen':
            continue
        output_name = f"{clip['id']:02d}_{clip['name'].replace(' ', '_').replace('/', '_')}.mp4"
        r = json.loads(extract_clip(source_video, clip.get('source_start', '00:00'),
                                    clip.get('source_end', '00:10'), output_name))
        if r.get("success"):
            clips_to_concat.append(output_name)

    if not clips_to_concat:
        return json.dumps({"error": "No clips extracted"})
    return concatenate(clips_to_concat, 'project_clips_concatenated.mp4')


@mcp.tool()
def cleanup_temp() -> str:
    """Delete all temporary clips."""
    try:
        import shutil
        if editor.temp_dir.exists():
            shutil.rmtree(editor.temp_dir)
            editor.temp_dir.mkdir(exist_ok=True)
        return json.dumps({"success": True, "message": "Temporary files cleaned"})
    except Exception as e:
        return json.dumps({"error": str(e)})


if __name__ == "__main__":
    print(f"🚀 DaVinci Resolve MCP Server (Streamable HTTP) on 0.0.0.0:{port}")
    print(f"📊 MCP endpoint: /mcp")
    mcp.run(transport="streamable-http")
