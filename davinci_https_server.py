#!/usr/bin/env python3
"""
DaVinci Resolve MCP Server - HTTPS SSE Implementation
"""

import json
import subprocess
import sys
import asyncio
from pathlib import Path
from typing import Any
import logging
import ssl

from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse
import uvicorn

# Fix encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

    def add_text_overlay(self, video: str, text: str, position: str, duration: str, output: str) -> dict:
        """Add text overlay to video"""
        video_path = self.output_dir / video if not Path(video).is_absolute() else Path(video)
        if not video_path.exists():
            return {"error": f"Video not found: {video_path}"}

        output_path = self.output_dir / output
        drawtext = f"text='{text}':fontsize=48:fontcolor=white:x={position.split(',')[0]}:y={position.split(',')[1] if ',' in position else '50'}"
        cmd = [self.ffmpeg_exe, '-y', '-i', str(video_path), '-vf', drawtext, '-c:a', 'copy', str(output_path)]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                size = output_path.stat().st_size / (1024*1024)
                return {"success": True, "output": output, "size_mb": f"{size:.2f}"}
            else:
                return {"error": result.stderr[:200]}
        except Exception as e:
            return {"error": str(e)}

    def add_fade(self, video: str, fade_type: str, duration: str, output: str) -> dict:
        """Add fade in/out effect"""
        video_path = self.output_dir / video if not Path(video).is_absolute() else Path(video)
        if not video_path.exists():
            return {"error": f"Video not found: {video_path}"}

        output_path = self.output_dir / output
        if fade_type == "in":
            fade_filter = f"fade=t=in:st=0:d={duration}"
        else:
            fade_filter = f"fade=t=out:st={duration}:d={duration}"

        cmd = [self.ffmpeg_exe, '-y', '-i', str(video_path), '-vf', fade_filter, '-c:a', 'copy', str(output_path)]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                size = output_path.stat().st_size / (1024*1024)
                return {"success": True, "output": output, "size_mb": f"{size:.2f}"}
            else:
                return {"error": result.stderr[:200]}
        except Exception as e:
            return {"error": str(e)}

    def get_video_info(self, video_file: str) -> dict:
        """Get video metadata"""
        video_path = self.output_dir / video_file if not Path(video_file).is_absolute() else Path(video_file)
        if not video_path.exists():
            return {"error": f"File not found: {video_path}"}

        cmd = [self.ffmpeg_exe, '-i', str(video_path)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            info = result.stderr
            return {"success": True, "info": info[:1000], "file": str(video_path)}
        except Exception as e:
            return {"error": str(e)}

    def extract_audio(self, video: str, output: str) -> dict:
        """Extract audio from video"""
        video_path = self.output_dir / video if not Path(video).is_absolute() else Path(video)
        if not video_path.exists():
            return {"error": f"Video not found: {video_path}"}

        output_path = self.output_dir / output
        cmd = [self.ffmpeg_exe, '-y', '-i', str(video_path), '-q:a', '0', '-map', 'a', str(output_path)]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                size = output_path.stat().st_size / (1024*1024)
                return {"success": True, "output": output, "size_mb": f"{size:.2f}"}
            else:
                return {"error": result.stderr[:200]}
        except Exception as e:
            return {"error": str(e)}

    def resize_video(self, video: str, width: int, height: int, output: str) -> dict:
        """Resize video to specified dimensions"""
        video_path = self.output_dir / video if not Path(video).is_absolute() else Path(video)
        if not video_path.exists():
            return {"error": f"Video not found: {video_path}"}

        output_path = self.output_dir / output
        scale_filter = f"scale={width}:{height}"
        cmd = [self.ffmpeg_exe, '-y', '-i', str(video_path), '-vf', scale_filter, '-c:a', 'copy', str(output_path)]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                size = output_path.stat().st_size / (1024*1024)
                return {"success": True, "output": output, "size_mb": f"{size:.2f}"}
            else:
                return {"error": result.stderr[:200]}
        except Exception as e:
            return {"error": str(e)}

    def adjust_speed(self, video: str, speed: float, output: str) -> dict:
        """Adjust video playback speed"""
        video_path = self.output_dir / video if not Path(video).is_absolute() else Path(video)
        if not video_path.exists():
            return {"error": f"Video not found: {video_path}"}

        output_path = self.output_dir / output
        setpts_filter = f"setpts={1/speed}*PTS"
        atempo_filter = f"atempo={speed}"
        cmd = [self.ffmpeg_exe, '-y', '-i', str(video_path), '-filter:v', setpts_filter, '-filter:a', atempo_filter, str(output_path)]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                size = output_path.stat().st_size / (1024*1024)
                return {"success": True, "output": output, "size_mb": f"{size:.2f}"}
            else:
                return {"error": result.stderr[:200]}
        except Exception as e:
            return {"error": str(e)}

    def cleanup_temp(self) -> dict:
        """Clean up temporary files"""
        try:
            import shutil
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)
                self.temp_dir.mkdir(exist_ok=True)
            return {"success": True, "message": "Temporary files cleaned"}
        except Exception as e:
            return {"error": str(e)}

    def get_status(self) -> dict:
        """Server status"""
        return {
            "status": "ready",
            "ffmpeg": str(self.ffmpeg_exe),
            "work_dir": str(self.work_dir),
            "temp_clips": len(list(self.temp_dir.glob("*.mp4"))),
            "output_files": len(list(self.output_dir.glob("*.mp4"))),
            "available_tools": [
                "extract_clip", "concatenate", "add_subtitles", "add_text_overlay",
                "add_fade", "get_video_info", "extract_audio", "resize_video",
                "adjust_speed", "process_config", "cleanup_temp"
            ]
        }


# ========== FASTAPI SERVER ==========

app = FastAPI(title="DaVinci Resolve MCP Server HTTPS")
editor = DaVinciEditor()

@app.get("/health")
async def health():
    return {"status": "healthy", "version": "1.0.0", "ssl": "enabled"}

@app.get("/davinci_status")
async def davinci_status():
    return editor.get_status()

@app.post("/davinci_extract_clip")
async def davinci_extract_clip(video_file: str, start_time: str, end_time: str, output_name: str):
    result = editor.extract_clip(video_file, start_time, end_time, output_name)
    return result

@app.post("/davinci_concatenate")
async def davinci_concatenate(clips: list, output_name: str):
    result = editor.concatenate(clips, output_name)
    return result

@app.post("/davinci_add_subtitles")
async def davinci_add_subtitles(video_file: str, srt_file: str, output_name: str):
    result = editor.add_subtitles(video_file, srt_file, output_name)
    return result

@app.post("/davinci_process_config")
async def davinci_process_config(config_file: str, source_video: str):
    result = editor.process_config(config_file, source_video)
    return result

@app.get("/davinci_list_clips")
async def davinci_list_clips():
    return editor.list_clips()

@app.get("/davinci_list_outputs")
async def davinci_list_outputs():
    return editor.list_outputs()

@app.post("/davinci_add_text_overlay")
async def davinci_add_text_overlay(video_file: str, text: str, position: str, duration: str, output_name: str):
    result = editor.add_text_overlay(video_file, text, position, duration, output_name)
    return result

@app.post("/davinci_add_fade")
async def davinci_add_fade(video_file: str, fade_type: str, duration: str, output_name: str):
    result = editor.add_fade(video_file, fade_type, duration, output_name)
    return result

@app.get("/davinci_get_video_info")
async def davinci_get_video_info(video_file: str):
    result = editor.get_video_info(video_file)
    return result

@app.post("/davinci_extract_audio")
async def davinci_extract_audio(video_file: str, output_name: str):
    result = editor.extract_audio(video_file, output_name)
    return result

@app.post("/davinci_resize_video")
async def davinci_resize_video(video_file: str, width: int, height: int, output_name: str):
    result = editor.resize_video(video_file, width, height, output_name)
    return result

@app.post("/davinci_adjust_speed")
async def davinci_adjust_speed(video_file: str, speed: float, output_name: str):
    result = editor.adjust_speed(video_file, speed, output_name)
    return result

@app.post("/davinci_cleanup_temp")
async def davinci_cleanup_temp():
    result = editor.cleanup_temp()
    return result

@app.get("/sse")
async def sse_endpoint(request_type: str = None):
    """SSE endpoint for MCP communication"""
    async def event_generator():
        try:
            if request_type == "status":
                result = editor.get_status()
            elif request_type == "list_clips":
                result = editor.list_clips()
            elif request_type == "list_outputs":
                result = editor.list_outputs()
            else:
                result = {"error": "Unknown request type"}

            yield f"data: {json.dumps(result, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

def generate_self_signed_cert():
    """Generate self-signed SSL certificate"""
    cert_file = Path("server.crt")
    key_file = Path("server.key")

    if cert_file.exists() and key_file.exists():
        return str(cert_file), str(key_file)

    try:
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:4096",
            "-keyout", str(key_file), "-out", str(cert_file),
            "-days", "365", "-nodes",
            "-subj", "/CN=localhost"
        ], check=True, capture_output=True)
        print(f"✅ SSL Certificate generated: {cert_file} & {key_file}")
        return str(cert_file), str(key_file)
    except Exception as e:
        print(f"⚠️  Could not generate SSL cert: {e}")
        return None, None

if __name__ == "__main__":
    port = 8443
    cert_file, key_file = generate_self_signed_cert()

    print(f"🚀 DaVinci Resolve MCP Server starting on https://localhost:{port}")
    print(f"📊 SSE Endpoint: https://localhost:{port}/sse")
    print(f"🎬 API Docs: https://localhost:{port}/docs")
    print(f"🔐 SSL: {cert_file}")

    if cert_file and key_file:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=port,
            log_level="info",
            ssl_certfile=cert_file,
            ssl_keyfile=key_file
        )
    else:
        print("⚠️  Running without SSL (install openssl to enable HTTPS)")
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
