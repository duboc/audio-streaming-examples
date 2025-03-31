#!/usr/bin/env python3
"""
Example script to transcribe audio using Gemini's multimodal capabilities
"""

import os
import argparse
from caption_generator import CaptionGenerator

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Transcribe audio with Gemini")
    parser.add_argument("input", help="Path to audio or video file, or YouTube URL")
    parser.add_argument("-o", "--output", help="Output file path (default: output/transcription.srt)")
    parser.add_argument("-f", "--format", choices=["srt", "vtt"], default="srt", 
                        help="Output format (default: srt)")
    parser.add_argument("-c", "--chunk-size", type=int, default=30,
                        help="Size of audio chunks in seconds (default: 30)")
    parser.add_argument("-p", "--project", help="Google Cloud Project ID")
    
    args = parser.parse_args()
    
    # Set default output path if not provided
    if not args.output:
        os.makedirs("output", exist_ok=True)
        args.output = os.path.join("output", "transcription.srt")
    
    print(f"Processing input: {args.input}")
    print(f"Output will be saved to: {args.output}")
    print(f"Using chunk size: {args.chunk_size} seconds")
    
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
        
        print(f"\nSuccessfully generated transcription: {output_file}")
        print(f"Audio chunks and response data are saved in the output directory.")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
