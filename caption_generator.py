#!/usr/bin/env python3
"""
Closed Caption Generator using Gemini

This script generates closed captions from YouTube videos or local video files 
using Google's Gemini model for both speech recognition and caption enhancement.
"""

import os
import sys
import argparse
import tempfile
from pathlib import Path
from urllib.parse import urlparse
import base64
import json
from typing import List, Dict, Tuple, Optional

# Import vertex libraries
from vertex_libs.gemini_client import GeminiClient, TokenCount
from google.genai import types

# Third-party libraries for video/audio processing
try:
    import yt_dlp
    from moviepy.editor import VideoFileClip
    from pydub import AudioSegment
except ImportError:
    print("Error: Required libraries not found. Please install using:")
    print("pip install -r requirements.txt")
    sys.exit(1)


class CaptionGenerator:
    """
    A class to generate closed captions from videos using Gemini models
    for both speech recognition and caption enhancement.
    """

    def __init__(self, project_id: Optional[str] = None, chunk_size_seconds: int = 30):
        """
        Initialize the Caption Generator.
        
        Args:
            project_id: Google Cloud Project ID
            chunk_size_seconds: Size of audio chunks in seconds to process at a time
        """
        self.project_id = project_id
        self.chunk_size_seconds = chunk_size_seconds
        self.client = GeminiClient(project_id=project_id)
        
        # Create temporary directory for processing
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        
        # Supported output formats
        self.output_formats = ["srt", "vtt"]

    def __del__(self):
        """Clean up temporary directory on deletion."""
        if hasattr(self, 'temp_dir'):
            self.temp_dir.cleanup()

    def process_input(self, input_source: str, output_path: str = None, output_format: str = "srt") -> str:
        """
        Process an input video source and generate captions.
        
        Args:
            input_source: YouTube URL or path to video file
            output_path: Path to save the output caption file (if None, uses output folder)
            output_format: Format of the output captions (srt, vtt)
            
        Returns:
            Path to the generated caption file
        """
        if output_format.lower() not in self.output_formats:
            raise ValueError(f"Unsupported output format: {output_format}. Use one of {self.output_formats}")
        
        # Determine if input is a YouTube URL or local file
        if self._is_youtube_url(input_source):
            print(f"Processing YouTube video: {input_source}")
            video_path = self._download_youtube_video(input_source)
            # Extract video ID for naming the output file
            video_id = self._extract_youtube_id(input_source)
            filename_base = f"youtube_{video_id}"
        else:
            print(f"Processing local video file: {input_source}")
            video_path = input_source
            
            # Verify the file exists
            if not os.path.exists(video_path):
                raise FileNotFoundError(f"Video file not found: {video_path}")
            
            # Use basename of video file for output filename
            filename_base = os.path.basename(video_path).rsplit(".", 1)[0]
        
        # Set default output path in output folder if not provided
        if output_path is None:
            # Ensure output directory exists
            os.makedirs("output", exist_ok=True)
            output_path = os.path.join("output", f"{filename_base}.{output_format}")
        elif not output_path.startswith("output/"):
            # Ensure output is in the output directory
            os.makedirs("output", exist_ok=True)
            output_path = os.path.join("output", os.path.basename(output_path))
        
        # Extract audio from video
        audio_path = self._extract_audio(video_path)
        
        # Process audio in chunks
        print("Extracting audio and processing with Gemini...")
        transcript_segments = self._process_audio_chunks(audio_path)
        
        # Format captions
        print(f"Formatting captions as {output_format}...")
        caption_text = self._format_captions(transcript_segments, output_format)
        
        # Save captions to file
        output_file = output_path
        if not output_file.endswith(f".{output_format}"):
            output_file += f".{output_format}"
            
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(caption_text)
            
        print(f"Captions saved to: {output_file}")
        return output_file

    def _extract_youtube_id(self, url: str) -> str:
        """Extract the YouTube video ID from a URL."""
        parsed = urlparse(url)
        if parsed.netloc == 'youtu.be':
            return parsed.path.lstrip('/')
        elif parsed.netloc in ('youtube.com', 'www.youtube.com'):
            if 'v=' in parsed.query:
                return parsed.query.split('v=')[1].split('&')[0]
        # If extraction fails, return a generic name
        return "video"

    def _is_youtube_url(self, url: str) -> bool:
        """Check if the input is a YouTube URL."""
        parsed = urlparse(url)
        return (
            parsed.netloc in ('youtube.com', 'www.youtube.com', 'youtu.be') and 
            parsed.scheme in ('http', 'https')
        )

    def _download_youtube_video(self, youtube_url: str) -> str:
        """
        Download a YouTube video and return the path to the downloaded file.
        
        Args:
            youtube_url: URL of the YouTube video
            
        Returns:
            Path to the downloaded video file
        """
        output_path = self.temp_path / "video.mp4"
        
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': str(output_path),
            'quiet': False,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([youtube_url])
            
        if not output_path.exists():
            raise RuntimeError(f"Failed to download YouTube video: {youtube_url}")
            
        return str(output_path)

    def _extract_audio(self, video_path: str) -> str:
        """
        Extract audio from a video file.
        
        Args:
            video_path: Path to the video file
            
        Returns:
            Path to the extracted audio file
        """
        audio_path = self.temp_path / "audio.mp3"
        
        # Use moviepy to extract audio
        with VideoFileClip(video_path) as video:
            video.audio.write_audiofile(str(audio_path), 
                                        codec='mp3', 
                                        ffmpeg_params=["-ac", "1", "-ar", "44100"],
                                        verbose=False, 
                                        logger=None)
            
        return str(audio_path)

    def _process_audio_chunks(self, audio_path: str) -> List[Dict[str, any]]:
        """
        Split audio into chunks and process each with Gemini.
        
        Args:
            audio_path: Path to the audio file
            
        Returns:
            List of transcript segments with timing information
        """
        # Load audio file
        audio = AudioSegment.from_file(audio_path)
        duration_ms = len(audio)
        chunk_size_ms = self.chunk_size_seconds * 1000
        
        transcript_segments = []
        
        # Process audio in chunks
        for start_ms in range(0, duration_ms, chunk_size_ms):
            end_ms = min(start_ms + chunk_size_ms, duration_ms)
            chunk = audio[start_ms:end_ms]
            
            # Convert timing to seconds for captions
            start_sec = start_ms / 1000.0
            end_sec = end_ms / 1000.0
            
            # Process chunk with Gemini
            segment_transcript = self._transcribe_audio_chunk(chunk, start_sec)
            transcript_segments.extend(segment_transcript)
            
            print(f"Processed audio segment {start_sec:.2f}s - {end_sec:.2f}s")
            
        return transcript_segments

    def _transcribe_audio_chunk(self, audio_chunk: AudioSegment, start_time: float) -> List[Dict[str, any]]:
        """
        Transcribe an audio chunk using Gemini multimodal capabilities.
        
        Args:
            audio_chunk: Audio segment to transcribe
            start_time: Start time of this chunk in the original audio (seconds)
            
        Returns:
            List of transcript segments with timing information
        """
        # Export chunk to a temporary file
        chunk_path = self.temp_path / f"chunk_{start_time}.mp3"
        audio_chunk.export(str(chunk_path), format="mp3", 
                          parameters=["-ac", "1", "-ar", "44100"])  # Ensure mono audio at 44.1kHz
        
        # Save the audio chunk to the output folder for reference
        os.makedirs("output", exist_ok=True)
        output_chunk_path = os.path.join("output", f"chunk_{start_time:.2f}.mp3") 
        audio_chunk.export(output_chunk_path, format="mp3")
        
        # Get audio duration
        duration_sec = len(audio_chunk) / 1000.0
        
        # Read audio file as bytes
        with open(chunk_path, "rb") as audio_file:
            audio_bytes = audio_file.read()
        
        # Create prompt for Gemini
        prompt = f"""
        Please transcribe this audio and provide accurate timestamps.
        This audio chunk starts at {start_time:.2f} seconds in the original video and is {duration_sec:.2f} seconds long.
        
        Return the result as a JSON array with each segment containing:
        1. "text": The transcribed text
        2. "start": Start time in seconds (relative to the start of this chunk)
        3. "end": End time in seconds (relative to the start of this chunk)
        
        Format:
        [
            {{"text": "This is the first segment", "start": 0.0, "end": 2.5}},
            {{"text": "This is the next segment", "start": 2.5, "end": 5.0}}
        ]
        
        For audio content you can't understand clearly, mark it as "[unintelligible]".
        """
        
        # Calculate default segment duration for fallback cases
        segment_duration = 5.0  # seconds
        num_segments = max(1, int(duration_sec / segment_duration))
        
        try:
            # Create content with both audio and text parts using the proper Blob structure
            contents = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            inline_data=types.Blob(
                                mime_type="audio/mp3",
                                data=audio_bytes
                            )
                        ),
                        types.Part(text=prompt)
                    ]
                )
            ]
            
            print(f"Processing audio chunk at {start_time:.2f}s with Gemini multimodal...")
            
            # Process with Gemini using the model that supports multimodal input
            response = self.client.generate_content(
                contents=contents,
                model="gemini-2.0-flash-001"
            )
            
            # Handle the response which could be a string or an object with 'text' attribute
            response_text = response if isinstance(response, str) else response.text if hasattr(response, 'text') else str(response)
            
            # Save raw response for debugging
            os.makedirs("output", exist_ok=True)
            with open(os.path.join("output", f"chunk_{start_time:.2f}_response.json"), "w") as f:
                f.write(json.dumps({"text": response_text}, indent=2))
            
            # Parse response to extract transcription segments
            segments = []
            
            # Try to extract JSON from the text response
            json_data = self.client.extract_json(response_text)
            
            if not json_data or not isinstance(json_data, list):
                # Fallback: Create a single segment with the full response text
                print(f"Could not parse JSON. Using full response text as a single segment.")
                segments.append({
                    "text": response_text.strip(),
                    "start": start_time,
                    "end": start_time + duration_sec
                })
            else:
                # Process each segment from the JSON response
                for segment in json_data:
                    # Adjust timing to be relative to the entire video
                    segment_start = start_time + float(segment.get("start", 0))
                    segment_end = start_time + float(segment.get("end", segment_start + 5.0))
                    
                    segments.append({
                        "text": segment.get("text", "[Transcription error]"),
                        "start": segment_start,
                        "end": segment_end
                    })
            
            print(f"Successfully transcribed audio chunk, extracted {len(segments)} segments")
            return segments
            
        except Exception as e:
            print(f"Error processing audio with Gemini: {str(e)}")
            
            # Save error information to output folder
            os.makedirs("output", exist_ok=True)
            error_file = os.path.join("output", f"chunk_{start_time:.2f}_error.txt")
            with open(error_file, "w") as f:
                f.write(f"Error at {start_time:.2f}s: {str(e)}")
            
            # Create fallback segments with even timing
            segments = []
            
            for i in range(num_segments):
                seg_start = start_time + (i * segment_duration)
                seg_end = start_time + min((i + 1) * segment_duration, duration_sec)
                
                segments.append({
                    "text": f"[Transcription unavailable {seg_start:.2f}s - {seg_end:.2f}s]",
                    "start": seg_start,
                    "end": seg_end
                })
                
            return segments

    def _format_captions(self, transcript_segments: List[Dict[str, any]], format_type: str) -> str:
        """
        Format transcript segments into the specified caption format.
        
        Args:
            transcript_segments: List of transcript segments with timing
            format_type: Output format (srt, vtt)
            
        Returns:
            Formatted caption text
        """
        if format_type.lower() == "srt":
            return self._format_as_srt(transcript_segments)
        elif format_type.lower() == "vtt":
            return self._format_as_vtt(transcript_segments)
        else:
            raise ValueError(f"Unsupported format: {format_type}")

    def _format_as_srt(self, segments: List[Dict[str, any]]) -> str:
        """Format transcript as SubRip (SRT) format."""
        srt_content = []
        
        for i, segment in enumerate(segments, 1):
            # Format timestamps as HH:MM:SS,mmm
            start_time = self._format_srt_timestamp(segment["start"])
            end_time = self._format_srt_timestamp(segment["end"])
            
            srt_content.append(f"{i}")
            srt_content.append(f"{start_time} --> {end_time}")
            srt_content.append(f"{segment['text']}")
            srt_content.append("")  # Empty line between entries
            
        return "\n".join(srt_content)

    def _format_as_vtt(self, segments: List[Dict[str, any]]) -> str:
        """Format transcript as WebVTT format."""
        vtt_content = ["WEBVTT", ""]  # Header and blank line
        
        for segment in segments:
            # Format timestamps as HH:MM:SS.mmm
            start_time = self._format_vtt_timestamp(segment["start"])
            end_time = self._format_vtt_timestamp(segment["end"])
            
            vtt_content.append(f"{start_time} --> {end_time}")
            vtt_content.append(f"{segment['text']}")
            vtt_content.append("")  # Empty line between entries
            
        return "\n".join(vtt_content)

    def _format_srt_timestamp(self, seconds: float) -> str:
        """Format seconds as SRT timestamp: HH:MM:SS,mmm"""
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d},{int((seconds % 1) * 1000):03d}"

    def _format_vtt_timestamp(self, seconds: float) -> str:
        """Format seconds as WebVTT timestamp: HH:MM:SS.mmm"""
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}.{int((seconds % 1) * 1000):03d}"


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Generate closed captions from video using Gemini")
    parser.add_argument("input", help="YouTube URL or path to video file")
    parser.add_argument("-o", "--output", help="Output file path (default: captions.<format>)")
    parser.add_argument("-f", "--format", choices=["srt", "vtt"], default="srt", 
                        help="Output caption format (default: srt)")
    parser.add_argument("-p", "--project", help="Google Cloud Project ID")
    parser.add_argument("-c", "--chunk-size", type=int, default=30,
                        help="Size of audio chunks in seconds (default: 30)")
    
    args = parser.parse_args()
    
    # Set default output path if not provided
    if not args.output:
        args.output = f"captions.{args.format}"
    
    try:
        # Initialize the caption generator
        generator = CaptionGenerator(
            project_id=args.project,
            chunk_size_seconds=args.chunk_size
        )
        
        # Process the input and generate captions
        output_file = generator.process_input(
            input_source=args.input,
            output_path=args.output,
            output_format=args.format
        )
        
        print(f"\nSuccessfully generated captions: {output_file}")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
