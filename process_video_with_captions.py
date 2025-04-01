#!/usr/bin/env python3
"""
Process Video With Captions

This script combines caption generation and embedding in one process:
1. Download YouTube video or use local video file (only once)
2. Generate captions using Gemini
3. Embed captions as soft subtitles that can be toggled on/off
4. Store all output files in a dedicated subfolder

Eliminates redundancy in the original separate scripts.
"""

import os
import sys
import argparse
import tempfile
import subprocess
from pathlib import Path
from urllib.parse import urlparse
import base64
import json
from typing import List, Dict, Tuple, Optional
from shutil import which

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


class VideoProcessor:
    """
    A class to process videos by generating captions using Gemini models
    and embedding them as soft subtitles.
    """

    def __init__(self, project_id: Optional[str] = None, chunk_size_seconds: int = 30):
        """
        Initialize the Video Processor.
        
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
        
        # Store output directory for saving all files
        self.base_output_dir = "output"
        self.output_dir = None  # Will be set during processing
        
        # Check if ffmpeg is installed
        if not which("ffmpeg"):
            raise RuntimeError("ffmpeg is not installed. Please install ffmpeg to use this script.")

    def __del__(self):
        """Clean up temporary directory on deletion."""
        if hasattr(self, 'temp_dir'):
            self.temp_dir.cleanup()

    def process_video(self, input_source: str, output_dir: str = None, 
                     output_format: str = "srt", skip_captions: bool = False,
                     skip_embedding: bool = False) -> Dict[str, str]:
        """
        Process a video: download if needed, generate captions, embed captions.
        
        Args:
            input_source: YouTube URL or path to video file
            output_dir: Directory to save all output files (if None, creates one in output/)
            output_format: Format of the captions (srt, vtt)
            skip_captions: If True, skip caption generation (use existing caption file)
            skip_embedding: If True, skip embedding captions (just generate caption file)
            
        Returns:
            Dictionary with paths to all generated files
        """
        if output_format.lower() not in self.output_formats:
            raise ValueError(f"Unsupported output format: {output_format}. Use one of {self.output_formats}")
        
        # Determine if input is a YouTube URL or local file
        if self._is_youtube_url(input_source):
            print(f"Processing YouTube video: {input_source}")
            # Extract video ID for naming the output folder
            video_id = self._extract_youtube_id(input_source)
            output_subfolder = f"youtube_{video_id}"
        else:
            print(f"Processing local video file: {input_source}")
            # Verify the file exists
            if not os.path.exists(input_source):
                raise FileNotFoundError(f"Video file not found: {input_source}")
            
            # Use basename of video file for output folder
            output_subfolder = os.path.basename(input_source).rsplit(".", 1)[0]
        
        # Set up output directory structure
        if output_dir:
            self.output_dir = output_dir
        else:
            self.output_dir = os.path.join(self.base_output_dir, output_subfolder)
        
        # Create output directory if it doesn't exist
        os.makedirs(self.output_dir, exist_ok=True)
        
        result_files = {}
        
        # Step 1: Get video - either download or use local file
        if self._is_youtube_url(input_source):
            video_path = os.path.join(self.output_dir, "video.mp4")
            self._download_youtube_video(input_source, video_path)
        else:
            # For local files, copy to output directory to keep everything together
            video_basename = os.path.basename(input_source)
            video_path = os.path.join(self.output_dir, video_basename)
            
            # Only copy if the source and destination are different
            if os.path.abspath(input_source) != os.path.abspath(video_path):
                print(f"Copying video file to output directory...")
                with open(input_source, 'rb') as src_file, open(video_path, 'wb') as dst_file:
                    dst_file.write(src_file.read())
        
        result_files['video'] = video_path
        
        # Step 2: Generate captions if not skipped
        caption_path = os.path.join(self.output_dir, f"captions.{output_format}")
        
        if not skip_captions:
            print("Generating captions...")
            # Extract audio from video
            audio_path = self._extract_audio(video_path)
            
            # Process audio in chunks
            print("Extracting audio and processing with Gemini...")
            transcript_segments = self._process_audio_chunks(audio_path)
            
            # Format captions
            print(f"Formatting captions as {output_format}...")
            caption_text = self._format_captions(transcript_segments, output_format)
            
            # Save captions to file
            with open(caption_path, 'w', encoding='utf-8') as f:
                f.write(caption_text)
                
            print(f"Captions saved to: {caption_path}")
        else:
            print("Skipping caption generation...")
            # Verify caption file exists if skipping generation
            if not os.path.exists(caption_path):
                raise FileNotFoundError(f"Caption file not found: {caption_path}. Cannot skip caption generation.")
        
        result_files['captions'] = caption_path
        
        # Step 3: Embed captions as soft subtitles if not skipped
        if not skip_embedding:
            print("Embedding captions into video...")
            
            # Only SRT format is supported for embedding
            if output_format.lower() != "srt":
                print(f"Warning: Only SRT format is supported for subtitle embedding. Converting to SRT...")
                # You might want to add format conversion here in the future
                
            output_video_path = os.path.join(self.output_dir, "video_with_captions.mp4")
            self._add_soft_subtitles(video_path, caption_path, output_video_path)
            
            result_files['video_with_captions'] = output_video_path
        else:
            print("Skipping caption embedding...")
        
        print(f"\nAll output files saved to: {self.output_dir}/")
        return result_files

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

    def _download_youtube_video(self, youtube_url: str, output_path: str) -> str:
        """
        Download a YouTube video and save to the specified path.
        
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

    def _extract_audio(self, video_path: str) -> str:
        """
        Extract audio from a video file.
        
        Args:
            video_path: Path to the video file
            
        Returns:
            Path to the extracted audio file
        """
        audio_path = os.path.join(self.output_dir, "audio.mp3")
        
        # Use moviepy to extract audio
        with VideoFileClip(video_path) as video:
            video.audio.write_audiofile(audio_path, 
                                       codec='mp3', 
                                       ffmpeg_params=["-ac", "1", "-ar", "44100"],
                                       verbose=False, 
                                       logger=None)
            
        return audio_path

    def _detect_and_fill_gaps(self, audio: AudioSegment, segments: List[Dict[str, any]], 
                             start_time: float, end_time: float) -> List[Dict[str, any]]:
        """
        Detect and fill gaps between transcript segments.
        
        Args:
            audio: Full audio segment
            segments: List of transcript segments for the current chunk
            start_time: Start time of current chunk in seconds
            end_time: End time of current chunk in seconds
            
        Returns:
            List of transcript segments with gaps filled
        """
        # Sort segments by start time
        sorted_segments = sorted(segments, key=lambda x: x["start"])
        
        # No segments to process
        if not sorted_segments:
            return []
            
        filled_segments = []
        current_time = start_time
        
        # Check for gap at the beginning of the chunk
        if sorted_segments[0]["start"] - start_time > 1.0:  # Gap > 1 second
            # Extract audio for this gap
            gap_start_ms = int(start_time * 1000)
            gap_end_ms = int(sorted_segments[0]["start"] * 1000)
            gap_audio = audio[gap_start_ms - int(start_time * 1000):gap_end_ms - int(start_time * 1000)]
            
            # Analyze gap
            gap_segment = self._analyze_audio_gap(gap_audio, start_time, sorted_segments[0]["start"])
            if gap_segment:
                filled_segments.append(gap_segment)
        
        # Add first segment
        filled_segments.append(sorted_segments[0])
        current_time = sorted_segments[0]["end"]
        
        # Process remaining segments and check for gaps between them
        for i in range(1, len(sorted_segments)):
            current_segment = sorted_segments[i]
            
            # Check if there's a significant gap between segments
            if current_segment["start"] - current_time > 1.0:  # Gap > 1 second
                # Extract audio for this gap
                gap_start_ms = int(current_time * 1000)
                gap_end_ms = int(current_segment["start"] * 1000)
                gap_audio = audio[gap_start_ms - int(start_time * 1000):gap_end_ms - int(start_time * 1000)]
                
                # Analyze gap
                gap_segment = self._analyze_audio_gap(gap_audio, current_time, current_segment["start"])
                if gap_segment:
                    filled_segments.append(gap_segment)
            
            # Add current segment
            filled_segments.append(current_segment)
            current_time = current_segment["end"]
        
        # Check for gap at the end of the chunk
        if end_time - current_time > 1.0:  # Gap > 1 second
            # Extract audio for this gap
            gap_start_ms = int(current_time * 1000)
            gap_end_ms = int(end_time * 1000)
            gap_audio = audio[gap_start_ms - int(start_time * 1000):gap_end_ms - int(start_time * 1000)]
            
            # Analyze gap
            gap_segment = self._analyze_audio_gap(gap_audio, current_time, end_time)
            if gap_segment:
                filled_segments.append(gap_segment)
        
        return filled_segments
    
    def _analyze_audio_gap(self, gap_audio: AudioSegment, start_time: float, end_time: float) -> Dict[str, any]:
        """
        Analyze audio gap to determine if it contains important audio cues.
        
        Args:
            gap_audio: Audio segment for the gap
            start_time: Start time of the gap in seconds
            end_time: End time of the gap in seconds
            
        Returns:
            A segment dict if the gap contains meaningful audio, or None if it's just silence
        """
        # Check if the gap is mostly silence
        silence_threshold = -50  # dB
        is_silence = gap_audio.dBFS < silence_threshold
        
        # If it's meaningful silence or has significant audio, create a gap segment
        if not is_silence or end_time - start_time > 3.0:  # If not silence or gap > 3 seconds
            # Export gap audio to a temp file for analysis
            gap_path = self.temp_path / f"gap_{start_time:.2f}.mp3"
            gap_audio.export(str(gap_path), format="mp3", parameters=["-ac", "1", "-ar", "44100"])
            
            # Get audio bytes
            with open(gap_path, "rb") as audio_file:
                audio_bytes = audio_file.read()
            
            try:
                # Create prompt for gap analysis
                prompt = f"""
                Analyze this audio gap between {start_time:.2f}s and {end_time:.2f}s.
                
                Determine if it contains:
                1. Music or background score
                2. Sound effects
                3. Ambient noise
                4. Meaningful silence
                
                Only return a JSON object with:
                - "type": one of "music", "sound", "silence"
                - "text": description of what you hear, formatted as "[♪ Music description ♪]", "[Sound: sound description]", or "[Silence]"
                
                Format:
                {{"type": "music", "text": "[♪ Suspenseful music ♪]"}}
                {{"type": "sound", "text": "[Sound: footsteps approaching]"}}
                {{"type": "silence", "text": "[Tense silence]"}}
                
                If there's nothing meaningful, simply return {{"type": "silence", "text": "[Silence]"}}
                """
                
                # Create content with both audio and text parts
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
                
                # Process with Gemini
                print(f"Analyzing audio gap at {start_time:.2f}s - {end_time:.2f}s...")
                response = self.client.generate_content(
                    contents=contents,
                    model="gemini-2.0-flash-001"
                )
                
                # Parse response
                response_text = response if isinstance(response, str) else response.text if hasattr(response, 'text') else str(response)
                json_data = self.client.extract_json(response_text)
                
                if json_data and isinstance(json_data, dict) and "type" in json_data and "text" in json_data:
                    return {
                        "text": json_data["text"],
                        "start": start_time,
                        "end": end_time,
                        "type": json_data["type"]
                    }
            except Exception as e:
                print(f"Error analyzing gap: {str(e)}")
            
            # Default fallback if analysis fails
            gap_type = "silence" if is_silence else "sound"
            gap_text = "[Silence]" if is_silence else "[Background sounds]"
            
            return {
                "text": gap_text,
                "start": start_time,
                "end": end_time,
                "type": gap_type
            }
        
        return None  # Not a meaningful gap, skip it
    
    def _finalize_timing(self, transcript_segments: List[Dict[str, any]]) -> List[Dict[str, any]]:
        """
        Perform a final adjustment of caption timing for optimal viewing experience.
        
        Args:
            transcript_segments: List of transcript segments with timing information
            
        Returns:
            List of transcript segments with optimized timing
        """
        if not transcript_segments:
            return []
            
        print("Performing final timing optimization...")
        
        # Sort segments by start time
        sorted_segments = sorted(transcript_segments, key=lambda x: x["start"])
        
        # Prepare a description of each segment for the API
        segments_json = json.dumps([{
            "text": seg["text"],
            "start": seg["start"],
            "end": seg["end"],
            "type": seg.get("type", "speech")
        } for seg in sorted_segments], indent=2)
        
        # Create prompt for the final timing adjustment
        prompt = f"""
        I have a set of caption segments for a video that need timing optimization.
        The goal is to make the captions more readable and properly timed for viewers.
        
        Here are the current segments:
        {segments_json}
        
        Please analyze these segments and optimize the timing based on these rules:
        
        1. Speech segments should align with natural speech patterns and sentence breaks
        2. Music and sound segments should have appropriate durations (not too short)
        3. Combine very short segments that are part of the same sentence
        4. Ensure gaps between captions are appropriate for readability
        5. Maintain original ordering but adjust start/end times
        6. Don't change the content of the text, only the timing
        
        Return the optimized segments as a JSON array with the same structure, preserving all fields.
        """
        
        try:
            # Use text-only model for this task since we're just processing JSON
            contents = [
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(prompt)]
                )
            ]
            
            response = self.client.generate_content(
                contents=contents,
                model="gemini-2.0-flash-001",
                return_json=True
            )
            
            # Parse the response
            if isinstance(response, str):
                json_data = self.client.extract_json(response)
            else:
                json_data = response
                
            # Validate the response
            if json_data and isinstance(json_data, list) and len(json_data) > 0:
                # Ensure all required fields are present
                for segment in json_data:
                    if not all(k in segment for k in ["text", "start", "end", "type"]):
                        print("Warning: Invalid segment in response, falling back to original segments")
                        return sorted_segments
                
                print(f"Successfully optimized timing for {len(json_data)} caption segments")
                return json_data
            else:
                print("Warning: Could not parse optimized segments, using original segments")
                return sorted_segments
                
        except Exception as e:
            print(f"Error optimizing segment timing: {str(e)}")
            return sorted_segments
    
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
            
            # Detect and fill gaps between segments
            filled_transcript = self._detect_and_fill_gaps(chunk, segment_transcript, start_sec, end_sec)
            transcript_segments.extend(filled_transcript)
            
            print(f"Processed audio segment {start_sec:.2f}s - {end_sec:.2f}s")
        
        # Perform final timing optimization on all segments
        optimized_segments = self._finalize_timing(transcript_segments)
            
        return optimized_segments

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
        
        # Save the audio chunk to the output folder
        output_chunk_path = os.path.join(self.output_dir, f"chunk_{start_time:.2f}.mp3") 
        audio_chunk.export(output_chunk_path, format="mp3")
        
        # Get audio duration
        duration_sec = len(audio_chunk) / 1000.0
        
        # Read audio file as bytes
        with open(chunk_path, "rb") as audio_file:
            audio_bytes = audio_file.read()
        
        # Create enhanced prompt for Gemini
        prompt = f"""
        Please transcribe this audio for captioning TV shows, videocasts, or webnovels, with accurate timestamps.
        This audio chunk starts at {start_time:.2f} seconds in the original video and is {duration_sec:.2f} seconds long.
        
        IMPORTANT: In addition to speech, also identify:
        - Music: Describe the music style or mood and mark as "[♪ Upbeat jazz music ♪]" or similar
        - Sound effects: Describe important sounds and mark as "[Sound: door slamming]" or similar
        - Ambient noise: Note significant background sounds like "[Crowd chattering]"
        - Silence: If there's silence but contextually important, indicate as "[Silence]" or "[Tense silence]"
        
        Ensure each caption segment is self-contained and meaningful to viewers. Split long sentences at natural breaks.
        
        Return the result as a JSON array with each chunk containing:
        1. "text": The transcribed text, including speech AND non-speech elements
        2. "start": Start time in seconds (relative to the start of this chunk)
        3. "end": End time in seconds (relative to the start of this chunk)
        4. "type": "speech" for spoken dialogue, "music" for music, "sound" for sound effects, "silence" for meaningful silence
        
        Format:
        [
            {{"text": "This is the first chunk", "start": 0.0, "end": 2.5, "type": "speech"}},
            {{"text": "[♪ Upbeat music ♪]", "start": 2.5, "end": 5.0, "type": "music"}},
            {{"text": "[Sound: door slamming]", "start": 5.0, "end": 5.5, "type": "sound"}},
            {{"text": "[Tense silence]", "start": 5.5, "end": 8.0, "type": "silence"}}
        ]
        
        For audio content you can't understand clearly, mark it as "[unintelligible]".
        Make sure the timestamps are accurate and reflect the actual timing of speech and sounds.
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
            with open(os.path.join(self.output_dir, f"chunk_{start_time:.2f}_response.json"), "w") as f:
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
                    "end": start_time + duration_sec,
                    "type": "speech"  # Default type for fallback
                })
            else:
                # Process each segment from the JSON response
                for segment in json_data:
                    # Adjust timing to be relative to the entire video
                    segment_start = start_time + float(segment.get("start", 0))
                    segment_end = start_time + float(segment.get("end", segment_start + 5.0))
                    
                    # Include the segment type if available
                    segment_type = segment.get("type", "speech")
                    
                    segments.append({
                        "text": segment.get("text", "[Transcription error]"),
                        "start": segment_start,
                        "end": segment_end,
                        "type": segment_type
                    })
            
            print(f"Successfully transcribed audio chunk, extracted {len(segments)} segments")
            return segments
            
        except Exception as e:
            print(f"Error processing audio with Gemini: {str(e)}")
            
            # Save error information
            error_file = os.path.join(self.output_dir, f"chunk_{start_time:.2f}_error.txt")
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
                    "end": seg_end,
                    "type": "speech"  # Default type for fallback
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
        """Format transcript as SubRip (SRT) format with enhanced styling for different content types."""
        srt_content = []
        
        # Sort segments by start time for proper sequencing
        sorted_segments = sorted(segments, key=lambda x: x["start"])
        
        for i, segment in enumerate(sorted_segments, 1):
            # Format timestamps as HH:MM:SS,mmm
            start_time = self._format_srt_timestamp(segment["start"])
            end_time = self._format_srt_timestamp(segment["end"])
            
            # Get the segment text
            text = segment['text']
            segment_type = segment.get('type', 'speech')
            
            # Add styling based on content type (SRT doesn't support much styling,
            # but we ensure proper formatting)
            if segment_type == "music" and not text.startswith("[♪"):
                text = f"[♪ {text} ♪]"
            elif segment_type == "sound" and not text.startswith("[Sound:"):
                text = f"[Sound: {text}]"
            elif segment_type == "silence" and not text.startswith("["):
                text = f"[{text}]"
            
            srt_content.append(f"{i}")
            srt_content.append(f"{start_time} --> {end_time}")
            srt_content.append(f"{text}")
            srt_content.append("")  # Empty line between entries
            
        return "\n".join(srt_content)

    def _format_as_vtt(self, segments: List[Dict[str, any]]) -> str:
        """Format transcript as WebVTT format with enhanced styling for different content types."""
        vtt_content = ["WEBVTT", ""]  # Header and blank line
        
        # Sort segments by start time for proper sequencing
        sorted_segments = sorted(segments, key=lambda x: x["start"])
        
        for i, segment in enumerate(sorted_segments, 1):
            # Format timestamps as HH:MM:SS.mmm
            start_time = self._format_vtt_timestamp(segment["start"])
            end_time = self._format_vtt_timestamp(segment["end"])
            
            # Get the segment text
            text = segment['text']
            segment_type = segment.get('type', 'speech')
            
            # WebVTT supports more styling options
            if segment_type == "music" and not text.startswith("[♪"):
                # Italics for music
                text = f"<i>[♪ {text} ♪]</i>"
            elif segment_type == "sound" and not text.startswith("[Sound:"):
                # Bold for sound effects
                text = f"<b>[Sound: {text}]</b>"
            elif segment_type == "silence" and not text.startswith("["):
                text = f"[{text}]"
            
            # Add cue identifier
            vtt_content.append(f"cue-{i}")
            vtt_content.append(f"{start_time} --> {end_time}")
            vtt_content.append(f"{text}")
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

    def _add_soft_subtitles(self, video_path: str, subtitle_path: str, output_path: str) -> str:
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
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Process a video by generating captions and embedding them as soft subtitles"
    )
    parser.add_argument("input", help="YouTube URL or path to video file")
    parser.add_argument("-o", "--output-dir", 
                        help="Directory to save all output files (default: auto-generated in output/)")
    parser.add_argument("-f", "--format", choices=["srt", "vtt"], default="srt", 
                        help="Output caption format (default: srt)")
    parser.add_argument("-p", "--project", help="Google Cloud Project ID")
    parser.add_argument("-c", "--chunk-size", type=int, default=30,
                        help="Size of audio chunks in seconds (default: 30)")
    parser.add_argument("--skip-captions", action="store_true",
                        help="Skip caption generation (use existing caption file)")
    parser.add_argument("--skip-embedding", action="store_true",
                        help="Skip embedding captions (just generate caption file)")
    
    args = parser.parse_args()
    
    try:
        # Initialize the video processor
        processor = VideoProcessor(
            project_id=args.project,
            chunk_size_seconds=args.chunk_size
        )
        
        # Process the video
        result_files = processor.process_video(
            input_source=args.input,
            output_dir=args.output_dir,
            output_format=args.format,
            skip_captions=args.skip_captions,
            skip_embedding=args.skip_embedding
        )
        
        print("\nProcess completed successfully!")
        print("Generated files:")
        for file_type, file_path in result_files.items():
            print(f"- {file_type}: {file_path}")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
