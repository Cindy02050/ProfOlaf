#!/usr/bin/env python3
"""
Startup script for Snowball Sampling Web UI
"""

import os
import sys
import subprocess

def check_dependencies():
    """Check if required dependencies are installed."""
    try:
        import flask
        import scholarly
        import requests
        import tqdm
        print("✓ All dependencies are installed")
        return True
    except ImportError as e:
        print(f"✗ Missing dependency: {e}")
        print("Please run: pip install -r requirements.txt")
        return False

def check_config():
    """Check if configuration files exist."""
    if not os.path.exists("search_conf.json"):
        print("✗ search_conf.json not found")
        return False
    
    if not os.path.exists("utils/db_management.py"):
        print("✗ utils/db_management.py not found")
        return False
    
    print("✓ Configuration files found")
    return True

def main():
    """Main startup function."""
    print("Snowball Sampling Web UI - Starting...")
    print("=" * 40)
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Check configuration
    if not check_config():
        sys.exit(1)
    
    # Create necessary directories
    os.makedirs("uploads", exist_ok=True)
    os.makedirs("templates", exist_ok=True)
    os.makedirs("static/css", exist_ok=True)
    os.makedirs("static/js", exist_ok=True)
    
    print("✓ Directory structure verified")
    print("\nStarting web server...")
    print("Open your browser and go to: http://localhost:5000")
    print("Press Ctrl+C to stop the server")
    print("=" * 40)
    
    # Start the Flask app
    try:
        from app import app
        app.run(debug=True, host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except Exception as e:
        print(f"Error starting server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
