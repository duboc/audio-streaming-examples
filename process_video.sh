#!/bin/bash

# process_video.sh - Process a video to generate captions and embed them
# This script ties together transcribe_audio.py and save_video_with_captions.py
# and organizes outputs in video-specific subfolders

# Default values
FORMAT="srt"
CHUNK_SIZE=30
PROJECT_ID=""
OUTPUT_DIR="output"

# Function to show usage information
function show_usage {
    echo "Usage: ./process_video.sh [options] <YouTube URL or video file path>"
    echo ""
    echo "Options:"
    echo "  -f, --format     Caption format: srt or vtt (default: srt)"
    echo "  -c, --chunk      Audio chunk size in seconds (default: 30)"
    echo "  -p, --project    Google Cloud Project ID (optional)"
    echo "  -h, --help       Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./process_video.sh https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    echo "  ./process_video.sh -f vtt -c 15 https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    echo "  ./process_video.sh /path/to/video.mp4"
    echo ""
}

# Function to extract YouTube video ID from URL
function extract_youtube_id {
    local url=$1
    local video_id=""
    
    # Handle youtu.be format
    if [[ $url == *"youtu.be"* ]]; then
        video_id=$(echo $url | sed -n 's/.*youtu\.be\/\([^?]*\).*/\1/p')
    # Handle youtube.com format
    elif [[ $url == *"youtube.com"* ]]; then
        video_id=$(echo $url | sed -n 's/.*v=\([^&]*\).*/\1/p')
    fi
    
    echo $video_id
}

# Function to get base filename without extension
function get_base_filename {
    local filepath=$1
    local filename=$(basename "$filepath")
    echo "${filename%.*}"
}

# Function to check if input is a YouTube URL
function is_youtube_url {
    local input=$1
    if [[ $input == *"youtube.com/watch"* || $input == *"youtu.be/"* ]]; then
        return 0  # true
    else
        return 1  # false
    fi
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--format)
            FORMAT="$2"
            shift 2
            ;;
        -c|--chunk)
            CHUNK_SIZE="$2"
            shift 2
            ;;
        -p|--project)
            PROJECT_ID="$2"
            shift 2
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            INPUT="$1"
            shift
            ;;
    esac
done

# Check if input is provided
if [ -z "$INPUT" ]; then
    echo "Error: No input provided."
    show_usage
    exit 1
fi

# Validate format
if [[ "$FORMAT" != "srt" && "$FORMAT" != "vtt" ]]; then
    echo "Error: Invalid format '$FORMAT'. Use 'srt' or 'vtt'."
    exit 1
fi

# Create output directory if it doesn't exist
mkdir -p "$OUTPUT_DIR"

# Determine if input is a YouTube URL or local file
if is_youtube_url "$INPUT"; then
    echo "Processing YouTube video: $INPUT"
    
    # Extract video ID
    VIDEO_ID=$(extract_youtube_id "$INPUT")
    
    if [ -z "$VIDEO_ID" ]; then
        echo "Error: Could not extract video ID from URL."
        exit 1
    fi
    
    # Create subfolder for this video
    SUBFOLDER="${OUTPUT_DIR}/youtube_${VIDEO_ID}"
    echo "Creating output directory: $SUBFOLDER"
    mkdir -p "$SUBFOLDER"
    
    # Set output filenames
    CAPTION_FILE="${SUBFOLDER}/captions.${FORMAT}"
    VIDEO_FILE="${SUBFOLDER}/video.mp4"
    FINAL_VIDEO="${SUBFOLDER}/video_with_captions.mp4"
    
    # Run transcribe_audio.py
    echo "Generating captions..."
    CMD="python transcribe_audio.py"
    [ ! -z "$PROJECT_ID" ] && CMD="$CMD -p $PROJECT_ID"
    CMD="$CMD -c $CHUNK_SIZE -f $FORMAT -o $CAPTION_FILE $INPUT"
    
    echo "Running: $CMD"
    eval $CMD
    
    if [ $? -ne 0 ]; then
        echo "Error: Failed to generate captions."
        exit 1
    fi
    
    # Run save_video_with_captions.py
    echo "Embedding captions into video..."
    CMD="python save_video_with_captions.py -c $CAPTION_FILE -o $FINAL_VIDEO $INPUT"
    
    echo "Running: $CMD"
    eval $CMD
    
    if [ $? -ne 0 ]; then
        echo "Error: Failed to embed captions into video."
        exit 1
    fi
    
    # Copy or move any generated files from output/ to the subfolder
    echo "Organizing files..."
    find "$OUTPUT_DIR" -maxdepth 1 -name "chunk_*" -exec mv {} "$SUBFOLDER/" \;
    
    echo "Success! Processing complete."
    echo "Output files are in: $SUBFOLDER"
    echo "Main caption file: $CAPTION_FILE"
    echo "Video with captions: $FINAL_VIDEO"
    
else
    # Local file
    if [ ! -f "$INPUT" ]; then
        echo "Error: Input file does not exist: $INPUT"
        exit 1
    fi
    
    echo "Processing local video file: $INPUT"
    
    # Get base filename for subfolder
    BASE_FILENAME=$(get_base_filename "$INPUT")
    
    # Create subfolder for this video
    SUBFOLDER="${OUTPUT_DIR}/${BASE_FILENAME}"
    echo "Creating output directory: $SUBFOLDER"
    mkdir -p "$SUBFOLDER"
    
    # Set output filenames
    CAPTION_FILE="${SUBFOLDER}/captions.${FORMAT}"
    FINAL_VIDEO="${SUBFOLDER}/${BASE_FILENAME}_with_captions.mp4"
    
    # Run transcribe_audio.py
    echo "Generating captions..."
    CMD="python transcribe_audio.py"
    [ ! -z "$PROJECT_ID" ] && CMD="$CMD -p $PROJECT_ID"
    CMD="$CMD -c $CHUNK_SIZE -f $FORMAT -o $CAPTION_FILE $INPUT"
    
    echo "Running: $CMD"
    eval $CMD
    
    if [ $? -ne 0 ]; then
        echo "Error: Failed to generate captions."
        exit 1
    fi
    
    # Run save_video_with_captions.py
    echo "Embedding captions into video..."
    CMD="python save_video_with_captions.py -c $CAPTION_FILE -o $FINAL_VIDEO $INPUT"
    
    echo "Running: $CMD"
    eval $CMD
    
    if [ $? -ne 0 ]; then
        echo "Error: Failed to embed captions into video."
        exit 1
    fi
    
    # Copy or move any generated files from output/ to the subfolder
    echo "Organizing files..."
    find "$OUTPUT_DIR" -maxdepth 1 -name "chunk_*" -exec mv {} "$SUBFOLDER/" \;
    
    echo "Success! Processing complete."
    echo "Output files are in: $SUBFOLDER"
    echo "Main caption file: $CAPTION_FILE"
    echo "Video with captions: $FINAL_VIDEO"
fi

exit 0
