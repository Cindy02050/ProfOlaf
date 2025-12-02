// Progress monitoring JavaScript for Snowball Sampling Tool

let progressInterval;
let isCompleted = false;

// Start monitoring progress when page loads
document.addEventListener('DOMContentLoaded', function() {
    startProgressMonitoring();
});

function startProgressMonitoring() {
    // Update progress every 2 seconds
    progressInterval = setInterval(updateProgress, 2000);
    
    // Initial update
    updateProgress();
}

function updateProgress() {
    fetch('/api/progress')
        .then(response => response.json())
        .then(data => {
            updateProgressUI(data);
            
            // If processing is complete, stop monitoring
            if (!data.is_running && data.progress_percent === 100) {
                completeProcessing();
            }
        })
        .catch(error => {
            console.error('Error fetching progress:', error);
            updateStatusMessage('Error fetching progress data', 'error');
        });
}

function updateProgressUI(data) {
    // Update progress bar
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');
    const currentStep = document.getElementById('current-step');
    
    if (progressBar && progressText && currentStep) {
        progressBar.style.width = data.progress_percent + '%';
        progressBar.setAttribute('aria-valuenow', data.progress_percent);
        progressText.textContent = data.progress_percent + '%';
        currentStep.textContent = data.current_step || 'Processing...';
    }
    
    // Update counters
    const totalItems = document.getElementById('total-items');
    const processedItems = document.getElementById('processed-items');
    const remainingItems = document.getElementById('remaining-items');
    
    if (totalItems) totalItems.textContent = data.total_items || 0;
    if (processedItems) processedItems.textContent = data.processed_items || 0;
    if (remainingItems) {
        const remaining = (data.total_items || 0) - (data.processed_items || 0);
        remainingItems.textContent = Math.max(0, remaining);
    }
    
    // Update status message
    updateStatusMessage(data.current_step || 'Processing...', 'info');
    
    // Show/hide spinner based on running state
    const spinner = document.getElementById('spinner');
    if (spinner) {
        if (data.is_running) {
            spinner.style.display = 'block';
        } else {
            spinner.style.display = 'none';
        }
    }
}

function updateStatusMessage(message, type) {
    const statusAlert = document.getElementById('status-alert');
    const statusMessage = document.getElementById('status-message');
    
    if (statusAlert && statusMessage) {
        statusMessage.textContent = message;
        
        // Update alert class based on type
        statusAlert.className = 'alert';
        if (type === 'error') {
            statusAlert.classList.add('alert-danger');
        } else if (type === 'success') {
            statusAlert.classList.add('alert-success');
        } else if (type === 'warning') {
            statusAlert.classList.add('alert-warning');
        } else {
            statusAlert.classList.add('alert-info');
        }
    }
}

function completeProcessing() {
    if (isCompleted) return;
    isCompleted = true;
    
    // Stop monitoring
    if (progressInterval) {
        clearInterval(progressInterval);
    }
    
    // Hide progress container and show completion container
    const progressContainer = document.getElementById('progress-container');
    const completionContainer = document.getElementById('completion-container');
    
    if (progressContainer && completionContainer) {
        progressContainer.style.display = 'none';
        completionContainer.style.display = 'block';
        completionContainer.classList.add('fade-in');
    }
    
    // Update final status
    updateStatusMessage('Processing completed successfully!', 'success');
}

function resetProgress() {
    if (confirm('Are you sure you want to reset the progress? This will clear all current processing data.')) {
        fetch('/api/reset')
            .then(response => response.json())
            .then(data => {
                if (data.status === 'reset') {
                    // Reload the page to show fresh state
                    window.location.reload();
                }
            })
            .catch(error => {
                console.error('Error resetting progress:', error);
                alert('Error resetting progress. Please refresh the page manually.');
            });
    }
}

// Handle page visibility change to pause/resume monitoring
document.addEventListener('visibilitychange', function() {
    if (document.hidden) {
        // Page is hidden, pause monitoring
        if (progressInterval) {
            clearInterval(progressInterval);
        }
    } else {
        // Page is visible, resume monitoring
        if (!isCompleted) {
            startProgressMonitoring();
        }
    }
});

// Handle page unload
window.addEventListener('beforeunload', function() {
    if (progressInterval) {
        clearInterval(progressInterval);
    }
});
