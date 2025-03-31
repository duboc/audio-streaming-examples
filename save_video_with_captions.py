#!/usr/bin/env python3
"""
Save Video with Captions

This script downloads a YouTube video or uses a local video file,
and embeds captions as soft subtitles that can be toggled on/off.
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path
import urllib.parse
from shutil import which

# Try to import yt_dlp for YouTube downloads
try:
    import yt_dlp
except ImportError:
    print("Error: yt_dlp library not found. Please install using:")
    print("pip install -r requirements.txt")
    sys.exit(1)

def extract_youtube_id(url):
    """Extract the YouTube video ID from a URL."""
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc == 'youtu.be':
        return parsed.path.lstrip('/')
    elif parsed.netloc in ('youtube.com', 'www.youtube.com'):
        if 'v=' in parsed.query:
            return parsed.query.split('v=')[1].split('&')[0]
    # If extraction fails, return a generic name
    return "video"

def is_youtube_url(url):
    """Check if the input is a YouTube URL."""
    parsed = urllib.parse.urlparse(url)
    return (
        parsed.netloc in ('youtube.com', 'www.youtube.com', 'youtu.be') and 
        parsed.scheme in ('http', 'https')
    )

def download_youtube_video(youtube_url, output_path):
    """
    Download a YouTube video to the specified output path.
    
    Args:
        youtube_url: URL of the YouTube video
        output_path: Path where the video will be saved
        
    Returns:
        Path to the downloaded video file
    """
    print(f"Downloading YouTube video: {youtube_url}")
    print(f"This may take a while depending on the video size...")
    
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_path,
        'quiet': False,
        'no_warnings': True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([youtube_url])
        
    if not os.path.exists(output_path):
        raise RuntimeError(f"Failed to download YouTube video: {youtube_url}")
        
    print(f"Successfully downloaded video to: {output_path}")
    return output_path

def add_soft_subtitles(video_path, subtitle_path, output_path):
    """
    Add soft subtitles to a video file using ffmpeg.
    
    Args:
        video_path: Path to the input video file
        subtitle_path: Path to the subtitle file (.srt)
        output_path: Path where the output video will be saved
        
    Returns:
        Path to the output video file
    """
    print(f"Adding subtitles to video...")
    
    # Check if ffmpeg is installed
    if not which("ffmpeg"):
        raise RuntimeError("ffmpeg is not installed. Please install ffmpeg to use this script.")
    
    # Command to add soft subtitles without re-encoding
    cmd = [
        "ffmpeg", 
        "-i", video_path, 
        "-i", subtitle_path, 
        "-c:v", "copy",  # Copy video stream (no re-encoding)
        "-c:a", "copy",  # Copy audio stream (no re-encoding)
        "-c:s", "mov_text",  # Use mov_text codec for subtitles (compatible with MP4)
        "-metadata:s:s:0", "language=eng",  # Set subtitle language to English
        "-y",  # Overwrite output file if it exists
        output_path
    ]
    
    try:
        subprocess.run(cmd, check=True, text=True, capture_output=True)
        print(f"Successfully created video with subtitles: {output_path}")
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"Error adding subtitles: {e}")
        print(f"ffmpeg stdout: {e.stdout}")
        print(f"ffmpeg stderr: {e.stderr}")
        raise RuntimeError("Failed to add subtitles to video.")

def main():
    parser = argparse.ArgumentParser(description="Save video with embedded soft subtitles")
    parser.add_argument("input", help="YouTube URL or path to local video file")
    parser.add_argument("-c", "--captions", help="Path to caption file (default: output/youtube_captions.srt)")
    parser.add_argument("-o", "--output", help="Output video file path (default: auto-generated in output directory)")
    
    args = parser.parse_args()
    
    # Ensure output directory exists
    os.makedirs("output", exist_ok=True)
    
    # Determine input type and get video path
    if is_youtube_url(args.input):
        # For YouTube, download video to output directory
        video_id = extract_youtube_id(args.input)
        video_filename = f"youtube_{video_id}.mp4"
        video_path = os.path.join("output", video_filename)
        download_youtube_video(args.input, video_path)
    else:
        # For local file, just use the provided path
        if not os.path.exists(args.input):
            print(f"Error: Input video file not found: {args.input}")
            sys.exit(1)
        video_path = args.input
    
    # Determine caption file path
    if args.captions:
        caption_path = args.captions
    else:
        # Try to find caption file in output directory
        if is_youtube_url(args.input):
            video_id = extract_youtube_id(args.input)
            default_caption_path = os.path.join("output", f"youtube_{video_id}.srt")
            if os.path.exists(default_caption_path):
                caption_path = default_caption_path
            else:
                # Fallback to common caption filename
                caption_path = os.path.join("output", "youtube_captions.srt")
        else:
            # For local file, try to find matching caption file
            video_basename = os.path.splitext(os.path.basename(video_path))[0]
            possible_caption_path = os.path.join("output", f"{video_basename}.srt")
            if os.path.exists(possible_caption_path):
                caption_path = possible_caption_path
            else:
                # Fallback to common caption filename
                caption_path = os.path.join("output", "captions.srt")
    
    # Verify caption file exists
    if not os.path.exists(caption_path):
        print(f"Error: Caption file not found: {caption_path}")
        sys.exit(1)
    
    # Determine output video path
    if args.output:
        output_path = args.output
        # If output path doesn't start with 'output/', put it in the output directory
        if not output_path.startswith("output/"):
            output_path = os.path.join("output", os.path.basename(output_path))
    else:
        # Auto-generate output filename based on input
        if is_youtube_url(args.input):
            video_id = extract_youtube_id(args.input)
            output_path = os.path.join("output", f"youtube_{video_id}_with_captions.mp4")
        else:
            video_basename = os.path.splitext(os.path.basename(video_path))[0]
            output_path = os.path.join("output", f"{video_basename}_with_captions.mp4")
    
    # Add captions to video
    try:
        output_file = add_soft_subtitles(video_path, caption_path, output_path)
        print("\nProcess completed successfully!")
        print(f"Video with captions saved to: {output_file}")
        print("The captions are embedded as soft subtitles and can be toggled on/off in most video players.")
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
