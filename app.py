#!/usr/bin/env python3
"""
Web Interface for Video Captioning

This script provides a web interface for the video captioning system,
allowing users to paste YouTube URLs or upload video files, then view
the processed video with captions.
"""

import os
import uuid
import threading
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, jsonify
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import StringField, SubmitField, SelectField
from wtforms.validators import DataRequired, Optional, URL
from werkzeug.utils import secure_filename
from process_video_with_captions import VideoProcessor

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'development-key')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB limit

# Create uploads directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Dictionary to track job status and results
jobs = {}

class ProcessVideoForm(FlaskForm):
    """Form for processing videos"""
    youtube_url = StringField('YouTube URL', validators=[Optional(), URL()])
    video_file = FileField('Upload Video', validators=[
        Optional(),
        FileAllowed(['mp4', 'mov', 'avi', 'mkv'], 'Videos only!')
    ])
    caption_format = SelectField(
        'Caption Format',
        choices=[('srt', 'SRT'), ('vtt', 'WebVTT')],
        default='srt'
    )
    submit = SubmitField('Process Video')

    def validate(self, **kwargs):
        """Custom validator to ensure either YouTube URL or file upload is provided"""
        if not super().validate():
            return False
        if not self.youtube_url.data and not self.video_file.data:
            flash('Please provide either a YouTube URL or upload a video file.')
            return False
        if self.youtube_url.data and self.video_file.data:
            flash('Please provide either a YouTube URL or upload a video file, not both.')
            return False
        return True

def process_video_task(job_id, input_source, output_format, project_id=None):
    """Background task to process a video"""
    try:
        jobs[job_id]['status'] = 'processing'
        
        # Initialize the processor
        processor = VideoProcessor(project_id=project_id)
        
        # Process the video
        result_files = processor.process_video(
            input_source=input_source,
            output_dir=os.path.join('output', job_id),
            output_format=output_format
        )
        
        # Store results
        jobs[job_id]['status'] = 'completed'
        jobs[job_id]['result_files'] = result_files
        
        # Include token usage data if available
        if 'token_usage' in result_files:
            jobs[job_id]['token_usage'] = result_files['token_usage']
        
        jobs[job_id]['error'] = None
        
    except Exception as e:
        jobs[job_id]['status'] = 'failed'
        jobs[job_id]['error'] = str(e)

@app.route('/', methods=['GET', 'POST'])
def index():
    """Home page with video processing form"""
    form = ProcessVideoForm()
    
    if form.validate_on_submit():
        # Generate a unique job ID
        job_id = str(uuid.uuid4())
        
        if form.youtube_url.data:
            input_source = form.youtube_url.data
            source_type = 'youtube'
        else:
            # Save uploaded file
            video_file = form.video_file.data
            filename = secure_filename(video_file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{job_id}_{filename}")
            video_file.save(file_path)
            input_source = file_path
            source_type = 'upload'
        
        # Initialize job tracking
        jobs[job_id] = {
            'id': job_id,
            'source_type': source_type,
            'input_source': input_source,
            'format': form.caption_format.data,
            'status': 'queued',
            'result_files': None,
            'error': None
        }
        
        # Start processing in background thread
        thread = threading.Thread(
            target=process_video_task,
            args=(job_id, input_source, form.caption_format.data)
        )
        thread.daemon = True
        thread.start()
        
        # Redirect to results page
        return redirect(url_for('results', job_id=job_id))
    
    return render_template('index.html', form=form)

@app.route('/results/<job_id>')
def results(job_id):
    """Results page showing processing status and video player"""
    if job_id not in jobs:
        flash('Job not found.')
        return redirect(url_for('index'))
    
    return render_template('results.html', job=jobs[job_id])

@app.route('/job-status/<job_id>')
def job_status(job_id):
    """API endpoint to check job status"""
    if job_id not in jobs:
        return jsonify({'status': 'not_found'})
    
    return jsonify({
        'status': jobs[job_id]['status'],
        'error': jobs[job_id]['error']
    })

@app.route('/video/<job_id>')
def video(job_id):
    """Serve the processed video file"""
    if job_id not in jobs or jobs[job_id]['status'] != 'completed':
        return "Video not ready or job not found", 404
    
    video_path = jobs[job_id]['result_files']['video_with_captions']
    directory, filename = os.path.split(video_path)
    
    return send_from_directory(directory, filename)

@app.route('/captions/<job_id>')
def captions(job_id):
    """Serve the caption file for the video"""
    if job_id not in jobs or jobs[job_id]['status'] != 'completed':
        return "Captions not ready or job not found", 404
    
    caption_path = jobs[job_id]['result_files']['captions']
    directory, filename = os.path.split(caption_path)
    
    # Set the MIME type based on the caption format
    mime_types = {
        'srt': 'text/srt',
        'vtt': 'text/vtt'
    }
    caption_format = jobs[job_id]['format']
    
    return send_from_directory(
        directory, 
        filename, 
        mimetype=mime_types.get(caption_format, 'text/plain')
    )

@app.route('/clear-job/<job_id>')
def clear_job(job_id):
    """Clear a completed job from memory"""
    if job_id in jobs:
        del jobs[job_id]
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
