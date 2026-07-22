#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple Video Clip Editor - extracts and concatenates clips via FFmpeg
"""

import json
import subprocess
import os
import sys
from pathlib import Path

# Fix Windows encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def find_ffmpeg():
    """Find FFmpeg in common locations"""
    paths = [
        'ffmpeg',
        r'C:\ffmpeg\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe',
        r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
    ]
    for path in paths:
        try:
            subprocess.run([path, '-version'], capture_output=True, check=True, timeout=2)
            print(f"[OK] Found FFmpeg: {path}")
            return path
        except:
            continue
    raise FileNotFoundError("FFmpeg not found!")


def extract_clip(ffmpeg_exe, input_file, start, end, output_file):
    """Extract a clip"""
    cmd = [
        ffmpeg_exe, '-y',
        '-ss', start, '-to', end,
        '-i', input_file,
        '-c', 'copy',
        output_file
    ]
    print(f"  Extracting: {output_file} ({start} -> {end})")
    subprocess.run(cmd, capture_output=True, check=False)


def concatenate(ffmpeg_exe, clip_list, output_file):
    """Concatenate clips"""
    # Create file list
    with open('filelist.txt', 'w') as f:
        for clip in clip_list:
            f.write(f"file '{clip}'\n")

    cmd = [
        ffmpeg_exe, '-y',
        '-f', 'concat', '-safe', '0',
        '-i', 'filelist.txt',
        '-c', 'copy',
        output_file
    ]
    print(f"\n[Concatenating {len(clip_list)} clips...]")
    subprocess.run(cmd, capture_output=True, check=False)
    os.remove('filelist.txt')


def main():
    print("=" * 60)
    print("Video Clip Editor - FFmpeg")
    print("=" * 60)

    # Find FFmpeg
    ffmpeg_exe = find_ffmpeg()

    # Load config
    with open('editing_config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)

    source_video = 'original.mp4'
    output_dir = Path('output')
    output_dir.mkdir(exist_ok=True)

    # Create temp directory
    temp_dir = Path('temp_clips')
    temp_dir.mkdir(exist_ok=True)

    print(f"[Source] {source_video}")
    print(f"[Clips] Processing {len(config['clips'])} segments...\n")

    clips_to_concat = []

    # Extract each clip
    for clip in config['clips']:
        clip_num = f"{clip['id']:02d}"
        clip_name = clip['name'].replace(' ', '_').replace('/', '_')
        output_name = f"{clip_num}_{clip_name}.mp4"
        output_path = temp_dir / output_name

        if clip.get('type') == 'title_screen':
            # Skip title creation - user will add via text editor
            print(f"  [SKIP] {clip['name']} (title card - add manually)")
            continue
        else:
            # Extract from source
            extract_clip(
                ffmpeg_exe,
                source_video,
                clip.get('source_start', '00:00'),
                clip.get('source_end', '00:10'),
                str(output_path)
            )
            clips_to_concat.append(str(output_path))

    # Concatenate all clips
    final_output = output_dir / 'project_clips_concatenated.mp4'
    concatenate(ffmpeg_exe, clips_to_concat, str(final_output))

    print(f"\n" + "=" * 60)
    print(f"[DONE] Output: {final_output}")
    print(f"[Next] Open in video editor to:")
    print(f"       1. Add title/closing cards")
    print(f"       2. Add subtitle file: subtitles.srt")
    print(f"       3. Adjust timing and audio")
    print("=" * 60)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
