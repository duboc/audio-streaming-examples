# Gemini Audio Transcription & Caption Generator

This application transcribes audio from YouTube videos or local media files using Gemini's multimodal capabilities. It extracts audio, processes it in chunks, and creates properly formatted caption files with timestamps.

All outputs, including audio chunks, transcription data, and caption files, are saved to the `output` folder.

## Features

- Process YouTube videos by URL
- Process local video files
- Generate captions in SRT or VTT format
- Automatically chunk audio for processing with Gemini
- Supports timing information for accurate caption synchronization

## Requirements

- Python 3.8+
- Google Cloud Project with Gemini API enabled
- Google API credentials configured

## Installation

1. Clone this repository or download the files
2. Install the required dependencies:

```bash
pip install -r requirements.txt
```

3. Set up Google Cloud credentials:

```bash
# Export your Google Cloud credentials
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/credentials.json"

# Optionally set your Google Cloud Project ID
export GCP_PROJECT="your-project-id"
```

## Usage

### Option 1: All-in-One Processing Script (Recommended)

The easiest way to use this application is with the all-in-one processing script:

```bash
# First, make the script executable
chmod +x process_video.sh

# Then run it with a YouTube URL or local video file
./process_video.sh [options] <YouTube URL or video file path>
```

Options:
- `-f, --format`: Caption format: srt or vtt (default: srt)
- `-c, --chunk`: Audio chunk size in seconds (default: 30)
- `-p, --project`: Google Cloud Project ID (optional)
- `-h, --help`: Show help message

This script:
1. Creates a dedicated subfolder for each video
2. Generates captions using Gemini
3. Embeds the captions into the video as soft subtitles
4. Organizes all output files in the subfolder

Examples:
```bash
# Process a YouTube video with default settings
./process_video.sh https://www.youtube.com/watch?v=dQw4w9WgXcQ

# Process a YouTube video with VTT format and smaller chunks
./process_video.sh -f vtt -c 15 https://www.youtube.com/watch?v=dQw4w9WgXcQ

# Process a local video file
./process_video.sh /path/to/video.mp4
```

### Option 2: Step-by-Step Processing

If you prefer more control, you can run the individual scripts manually:

#### Step 1: Generate Captions

```bash
python transcribe_audio.py [input] [options]
```

Options:
- `input`: YouTube URL or path to a local video/audio file
- `-o, --output`: Output file path (default: output/transcription.srt)
- `-f, --format`: Output format: "srt" or "vtt" (default: srt)
- `-p, --project`: Google Cloud Project ID (optional if set in environment)
- `-c, --chunk-size`: Size of audio chunks in seconds (default: 30)

#### Step 2: Save Video with Embedded Captions

```bash
python save_video_with_captions.py [input] [options]
```

Options:
- `input`: YouTube URL or path to local video file
- `-c, --captions`: Path to caption file (default: auto-detected in output folder)
- `-o, --output`: Output video file path (default: auto-generated in output directory)

This will create a video file with embedded soft subtitles that can be toggled on/off in most video players.

### Examples

#### Generating Captions

Transcribe a YouTube video:

```bash
python transcribe_audio.py https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

Transcribe a local audio or video file in VTT format:

```bash
python transcribe_audio.py /path/to/audio.mp3 -f vtt
```

Specify a custom output path:

```bash
python transcribe_audio.py /path/to/video.mp4 -o output/my_transcription.srt
```

Adjust chunk size for better handling of long files:

```bash
python transcribe_audio.py /path/to/long_video.mp4 -c 15
```

#### Embedding Captions in Videos

Save a YouTube video with auto-detected captions:

```bash
python save_video_with_captions.py https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

Save a local video with specified caption file:

```bash
python save_video_with_captions.py /path/to/video.mp4 -c output/my_captions.srt
```

Specify custom output path for the captioned video:

```bash
python save_video_with_captions.py /path/to/video.mp4 -o output/final_video.mp4
```

### Advanced: Using the CaptionGenerator Class

### Programmatic Usage

You can also use the `CaptionGenerator` class in your own Python code:

```python
from caption_generator import CaptionGenerator
import os

# Initialize the generator
generator = CaptionGenerator(project_id="your-google-cloud-project-id")

# Process a YouTube video (output saved to output/youtube_[video_id].srt)
generator.process_input(
    input_source="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    output_format="srt"
)

# Process a local video file with a custom output path
output_path = os.path.join("output", "custom_name.vtt")
generator.process_input(
    input_source="/path/to/video.mp4",
    output_path=output_path,
    output_format="vtt"
)
```

## How It Works

1. The application first processes the input source:
   - For YouTube URLs: Downloads the video using yt-dlp
   - For local files: Processes the file directly

2. Audio is extracted from the video using moviepy

3. The audio is split into manageable chunks (default: 30 seconds)

4. For each chunk:
   - Audio is exported to MP3 format and saved to the output folder
   - The chunk is processed to create timed caption segments
   - Each segment includes appropriate timestamps based on its position in the video
   - Raw responses are saved to the output directory for reference

5. Caption segments are converted to the specified caption format (SRT or VTT)

6. The formatted captions are written to the output file in the 'output' directory

## How the Transcription Works

1. The application first processes the input source:
   - For YouTube URLs: Downloads the video using yt-dlp
   - For local files: Processes the video or audio file directly

2. Audio is extracted (for video files) or processed directly (for audio files)

3. The audio is split into manageable chunks (default: 30 seconds)

4. For each chunk:
   - Audio is exported to MP3 format and saved to the output folder
   - The audio is sent to Gemini using its multimodal capabilities via inline Blob data
   - Gemini transcribes the audio content and returns text with timestamp information
   - Raw responses are saved to the output directory for reference

5. Transcription segments are converted to the specified caption format (SRT or VTT)

6. The formatted captions are written to the output file in the 'output' directory

## Multimodal Processing

The application uses Gemini's multimodal capabilities to process audio data directly:

```python
# Audio is sent to Gemini using the inline_data Blob structure
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
```

## Output Directory Contents

After processing, the output folder will contain:
- The main transcription file (.srt or .vtt)
- Audio chunk files (.mp3) for each segment of the processed media
- Response data (.json) from Gemini for each audio chunk
- Error logs (.txt) if any issues occurred during processing
- Downloaded video files (if using YouTube URLs)
- Video files with embedded captions

## Limitations

- Gemini's audio processing capabilities have limitations with certain accents or background noise
- Audio quality significantly affects transcription accuracy
- Longer audio files are processed in chunks, which may affect continuity at chunk boundaries
- API usage costs apply according to your Google Cloud pricing

## License

This project is licensed under the Apache License 2.0, following the same license as the Vertex Libs.
