/**
 * Main JavaScript for Video Caption Generator
 */

document.addEventListener('DOMContentLoaded', function() {
    
    // File upload preview and validation
    const videoFileInput = document.getElementById('video_file');
    if (videoFileInput) {
        videoFileInput.addEventListener('change', function() {
            const file = this.files[0];
            if (file) {
                // Check file size (max 500MB)
                const maxSize = 500 * 1024 * 1024; // 500MB in bytes
                if (file.size > maxSize) {
                    alert('File is too large. Maximum size is 500MB.');
                    this.value = ''; // Clear the file input
                    return;
                }
                
                // Check file type
                const validTypes = ['video/mp4', 'video/mov', 'video/quicktime', 'video/avi', 'video/x-matroska'];
                if (!validTypes.includes(file.type)) {
                    alert('Invalid file type. Please upload a video file (MP4, MOV, AVI, or MKV).');
                    this.value = ''; // Clear the file input
                    return;
                }
                
                // Show file name as feedback
                const fileName = file.name;
                const fileSize = (file.size / (1024 * 1024)).toFixed(2); // Convert to MB
                
                // You could add a preview element here if desired
                console.log(`File selected: ${fileName} (${fileSize} MB)`);
            }
        });
    }
    
    // Form validation - ensure one option is selected
    const processingForm = document.querySelector('form');
    if (processingForm) {
        processingForm.addEventListener('submit', function(e) {
            const youtubeUrl = document.getElementById('youtube_url').value.trim();
            const videoFile = document.getElementById('video_file').files[0];
            
            if (!youtubeUrl && !videoFile) {
                e.preventDefault();
                alert('Please either enter a YouTube URL or upload a video file.');
                return false;
            }
            
            if (youtubeUrl && videoFile) {
                e.preventDefault();
                alert('Please choose only one option: YouTube URL or file upload.');
                return false;
            }
            
            // If validation passes, show loading state
            if (document.querySelector('button[type="submit"]')) {
                document.querySelector('button[type="submit"]').disabled = true;
                document.querySelector('button[type="submit"]').innerHTML = 
                    '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Processing...';
            }
            
            return true;
        });
    }
    
    // Toggle between YouTube URL and file upload options
    const youtubeUrlInput = document.getElementById('youtube_url');
    if (youtubeUrlInput) {
        youtubeUrlInput.addEventListener('input', function() {
            if (this.value.trim()) {
                // If YouTube URL is entered, disable file upload
                if (videoFileInput) videoFileInput.disabled = true;
            } else {
                // If YouTube URL is cleared, enable file upload
                if (videoFileInput) videoFileInput.disabled = false;
            }
        });
    }
    
    // Similarly, disable YouTube URL if file is selected
    if (videoFileInput) {
        videoFileInput.addEventListener('change', function() {
            if (this.files.length > 0) {
                // If file is selected, disable YouTube URL
                if (youtubeUrlInput) youtubeUrlInput.disabled = true;
            } else {
                // If file selection is cleared, enable YouTube URL
                if (youtubeUrlInput) youtubeUrlInput.disabled = false;
            }
        });
    }
    
    // Video player controls for results page
    const videoPlayer = document.getElementById('video-player');
    const toggleCaptionsBtn = document.getElementById('toggle-captions');
    
    if (videoPlayer) {
        // Enable caption display by default when video loads
        videoPlayer.addEventListener('loadedmetadata', function() {
            // Wait a moment for text tracks to initialize
            setTimeout(() => {
                // If the video has text tracks, enable the first one
                if (this.textTracks && this.textTracks.length > 0) {
                    this.textTracks[0].mode = 'showing';
                    
                    // Update button text to reflect current state
                    if (toggleCaptionsBtn) {
                        toggleCaptionsBtn.textContent = 'Hide Captions';
                    }
                } else {
                    console.warn('No text tracks found in the video');
                    
                    // Update button to indicate no captions available
                    if (toggleCaptionsBtn) {
                        toggleCaptionsBtn.textContent = 'No Captions Available';
                        toggleCaptionsBtn.disabled = true;
                    }
                }
            }, 1000); // Wait 1 second for tracks to load
        });
    }
    
    // Handle caption toggle button
    if (toggleCaptionsBtn) {
        toggleCaptionsBtn.addEventListener('click', function() {
            if (videoPlayer && videoPlayer.textTracks && videoPlayer.textTracks.length > 0) {
                const track = videoPlayer.textTracks[0];
                
                if (track.mode === 'showing') {
                    track.mode = 'hidden';
                    this.textContent = 'Show Captions';
                } else {
                    track.mode = 'showing';
                    this.textContent = 'Hide Captions';
                }
            }
        });
    }
});
