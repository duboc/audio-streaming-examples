#!/usr/bin/env python3
"""
Example usage of the CaptionGenerator
"""

from caption_generator import CaptionGenerator
import os

def example_youtube():
    """Generate captions from a YouTube video"""
    # Replace with your actual Google Cloud Project ID
    project_id = "your-google-cloud-project-id"
    
    generator = CaptionGenerator(project_id=project_id)
    
    # Process a YouTube video
    youtube_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Example YouTube URL
    
    # Output will be saved to the output folder by default
    output_file = generator.process_input(
        input_source=youtube_url,
        output_format="srt"
    )
    
    print(f"Generated captions for YouTube video: {output_file}")


def example_local_file():
    """Generate captions from a local video file"""
    # Replace with your actual Google Cloud Project ID
    project_id = "your-google-cloud-project-id"
    
    generator = CaptionGenerator(project_id=project_id)
    
    # Process a local video file
    video_path = "path/to/your/video.mp4"  # Replace with actual path
    
    # You can also specify a custom output path within the output directory
    output_path = os.path.join("output", "custom_filename.vtt")
    
    output_file = generator.process_input(
        input_source=video_path,
        output_path=output_path,
        output_format="vtt"
    )
    
    print(f"Generated captions for local video: {output_file}")


def example_with_longer_chunks():
    """Generate captions with longer audio chunks"""
    # Replace with your actual Google Cloud Project ID
    project_id = "your-google-cloud-project-id"
    
    # Use 60-second chunks instead of the default 30 seconds
    generator = CaptionGenerator(
        project_id=project_id,
        chunk_size_seconds=60
    )
    
    # Process a YouTube video with longer chunks
    youtube_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Example YouTube URL
    
    output_file = generator.process_input(
        input_source=youtube_url,
        output_format="srt"
    )
    
    print(f"Generated captions with longer chunks: {output_file}")


if __name__ == "__main__":
    # Ensure output directory exists
    os.makedirs("output", exist_ok=True)
    
    # Uncomment the example you want to run
    # example_youtube()
    # example_local_file()
    # example_with_longer_chunks()
    
    print("To run an example, uncomment one of the function calls above.")
    print("Make sure to set your Google Cloud Project ID and have appropriate credentials configured.")
    print("Generated caption files will be saved in the 'output' directory.")
