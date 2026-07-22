#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DaVinci Resolve MCP Server
Automates video editing via FFmpeg integration
"""

import json
import subprocess
import os
import sys
from pathlib import Path
from typing import Any, Optional

# Fix Windows encoding issues
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

class DaVinciMCP:
    """MCP Server for automated video editing with DaVinci/FFmpeg"""

    def __init__(self):
        self.config_path = None
        self.work_dir = Path.cwd()
        self.temp_dir = self.work_dir / "temp_clips"
        self.output_dir = self.work_dir / "output"

        # Find FFmpeg executable
        self.ffmpeg_exe = self._find_ffmpeg()

        # Create directories
        self.temp_dir.mkdir(exist_ok=True)
        self.output_dir.mkdir(exist_ok=True)

    def _find_ffmpeg(self) -> str:
        """Find FFmpeg executable in common locations"""
        paths = [
            'ffmpeg',
            r'C:\ffmpeg\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe',
            r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
            r'C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe',
        ]
        for path in paths:
            try:
                subprocess.run([path, '-version'], capture_output=True, check=True, timeout=2)
                return path
            except:
                continue
        return 'ffmpeg'  # Fallback

    def load_config(self, config_file: str) -> dict:
        """Load editing configuration from JSON"""
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def check_ffmpeg(self) -> bool:
        """Verify FFmpeg is installed"""
        try:
            # Try common installation paths on Windows
            ffmpeg_paths = [
                'ffmpeg',
                r'C:\ffmpeg\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe',
                r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
                r'C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe',
            ]

            for ffmpeg_path in ffmpeg_paths:
                try:
                    subprocess.run([ffmpeg_path, '-version'],
                                 capture_output=True,
                                 check=True,
                                 timeout=5)
                    return True
                except:
                    continue
            return False
        except:
            return False

    def extract_clip(self,
                    video_file: str,
                    start_time: str,
                    end_time: str,
                    output_file: str) -> bool:
        """Extract a clip from source video using FFmpeg"""
        cmd = [
            self.ffmpeg_exe,
            '-y',  # Overwrite output
            '-ss', start_time,
            '-to', end_time,
            '-i', video_file,
            '-c', 'copy',  # Stream copy (no re-encode)
            str(self.temp_dir / output_file)
        ]

        print(f"🎬 Extracting: {output_file} ({start_time} → {end_time})")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Error extracting clip: {e.stderr}")
            return False

    def create_title_card(self,
                         text_main: str,
                         text_secondary: str,
                         duration: float,
                         output_file: str,
                         bg_color: str = "black") -> bool:
        """Create a title card with text overlay"""
        cmd = [
            self.ffmpeg_exe,
            '-y',
            '-f', 'lavfi',
            '-i', f'color=c={bg_color}:s=1920x1080:d={duration}',
            '-vf', (
                f"drawtext="
                f"text='{text_main}\\n{text_secondary}':"
                f"fontfile='C:/Windows/Fonts/arial.ttf':"
                f"fontsize=60:"
                f"fontcolor=white:"
                f"x=(w-text_w)/2:"
                f"y=(h-text_h)/2:"
                f"line_spacing=15"
            ),
            '-c:v', 'libx264',
            '-pix_fmt', 'yuv420p',
            str(self.temp_dir / output_file)
        ]

        print(f"📝 Creating title card: {output_file}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Error creating title: {e.stderr}")
            return False

    def concatenate_clips(self, clip_list: list, output_file: str) -> bool:
        """Concatenate multiple clips"""
        # Create file list for concat demuxer
        filelist_path = self.work_dir / 'filelist.txt'
        with open(filelist_path, 'w') as f:
            for clip in clip_list:
                f.write(f"file '{self.temp_dir / clip}'\n")

        cmd = [
            self.ffmpeg_exe,
            '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', str(filelist_path),
            '-c', 'copy',
            str(self.output_dir / output_file)
        ]

        print(f"🔗 Concatenating {len(clip_list)} clips...")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            filelist_path.unlink()  # Clean up
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Error concatenating: {e.stderr}")
            return False

    def add_subtitles(self, video_file: str, srt_file: str, output_file: str) -> bool:
        """Add SRT subtitles to video"""
        input_path = self.output_dir / video_file
        output_path = self.output_dir / output_file

        cmd = [
            self.ffmpeg_exe,
            '-y',
            '-i', str(input_path),
            '-vf', (
                f"subtitles='{srt_file}':"
                f"force_style='FontName=Arial,"
                f"FontSize=32,"
                f"PrimaryColour=&HFFFFFF&,"
                f"SecondaryColour=&H00000000&,"
                f"BorderStyle=1,"
                f"Outline=2,"
                f"Shadow=0,"
                f"Alignment=2'"
            ),
            '-c:a', 'copy',
            str(output_path)
        ]

        print(f"📝 Adding subtitles...")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"⚠️  Subtitle warning (continuing): {e.stderr[:100]}")
            # Don't fail on subtitle errors
            return True

    def process_editing_config(self,
                              config_file: str,
                              source_video: str,
                              srt_file: Optional[str] = None) -> bool:
        """Process complete editing configuration"""

        print("=" * 50)
        print("🎬 DaVinci MCP Video Editor Starting...")
        print("=" * 50)

        # Verify FFmpeg
        if not self.check_ffmpeg():
            print("❌ FFmpeg not found in PATH")
            print("   Install FFmpeg: https://ffmpeg.org/download.html")
            return False

        print("✓ FFmpeg found")

        # Load config
        try:
            config = self.load_config(config_file)
        except FileNotFoundError:
            print(f"❌ Config file not found: {config_file}")
            return False

        clips_to_concat = []

        # Process each clip in config
        project = config.get('project', {})
        clips = config.get('clips', [])

        print(f"\n📋 Processing {len(clips)} clips...")
        print(f"   Target duration: {project.get('target_duration_range', 'N/A')}")

        for clip in clips:
            clip_id = f"{clip['id']:02d}"
            clip_name = clip['name'].replace(' ', '_')
            output_name = f"{clip_id}_{clip_name}.mp4"

            clip_type = clip.get('type', 'speaker_clip')

            if clip_type == 'title_screen':
                # Create title card
                success = self.create_title_card(
                    text_main=clip.get('text_main', ''),
                    text_secondary=clip.get('text_secondary', ''),
                    duration=clip.get('duration', 2.5),
                    output_file=output_name,
                    bg_color=clip.get('background_color', 'black').lstrip('#')
                )
            else:
                # Extract speaker clip
                success = self.extract_clip(
                    video_file=source_video,
                    start_time=clip.get('source_start', '00:00'),
                    end_time=clip.get('source_end', '00:10'),
                    output_file=output_name
                )

            if success:
                clips_to_concat.append(output_name)
                print(f"   ✓ {clip['name']} ({clip.get('duration', '?')}s)")
            else:
                print(f"   ✗ {clip['name']} FAILED")
                return False

        # Concatenate all clips
        if not self.concatenate_clips(clips_to_concat, 'temp_concatenated.mp4'):
            print("❌ Concatenation failed")
            return False

        # Add subtitles if available
        if srt_file and os.path.exists(srt_file):
            if not self.add_subtitles('temp_concatenated.mp4', srt_file, 'final_with_subtitles.mp4'):
                print("⚠️  Subtitle addition failed, using video without subtitles")
                final_output = 'temp_concatenated.mp4'
            else:
                final_output = 'final_with_subtitles.mp4'
        else:
            final_output = 'temp_concatenated.mp4'

        # Rename to project output
        output_file = project.get('output_video', 'project_clip_final.mp4')
        final_path = self.output_dir / output_file
        temp_path = self.output_dir / final_output

        if temp_path.exists():
            if final_path.exists():
                final_path.unlink()
            temp_path.rename(final_path)

        print("\n" + "=" * 50)
        print(f"✅ EDITING COMPLETE!")
        print(f"   Output: {final_path}")
        print(f"   Size: {final_path.stat().st_size / (1024*1024):.1f} MB")
        print("=" * 50)

        return True

    def cleanup(self):
        """Remove temporary files"""
        print("🧹 Cleaning up temporary files...")
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
        print("✓ Cleanup complete")


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description='DaVinci Resolve MCP Server - Automated Video Editing'
    )
    parser.add_argument('--config', required=True, help='Path to editing_config.json')
    parser.add_argument('--video', required=True, help='Path to source video')
    parser.add_argument('--subtitles', help='Path to SRT subtitle file')
    parser.add_argument('--cleanup', action='store_true', help='Remove temp files after editing')

    args = parser.parse_args()

    # Create server
    server = DaVinciMCP()

    # Process editing
    success = server.process_editing_config(
        config_file=args.config,
        source_video=args.video,
        srt_file=args.subtitles
    )

    if args.cleanup:
        server.cleanup()

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
