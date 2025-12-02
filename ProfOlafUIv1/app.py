#!/usr/bin/env python3
"""
Web UI for Snowball Sampling Research Paper Collection Tool
"""

import os
import json
import time
import threading
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from werkzeug.utils import secure_filename
import sqlite3
from utils.db_management import DBManager, initialize_db, SelectionStage, ArticleData, get_article_data
from utils.proxy_generator import get_proxy
from scholarly import scholarly
import hashlib
import re
from tqdm import tqdm
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'txt', 'json'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Create upload folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Load search configuration
try:
    with open("search_conf.json", "r") as f:
        search_conf = json.load(f)
except FileNotFoundError:
    # Create default configuration if file doesn't exist
    search_conf = {
        "start_year": 2020,
        "end_year": 2024,
        "venue_rank_list": ["A", "B", "C"],
        "proxy_key": "",
        "initial_file": "seed.txt",
        "db_path": "database.db"
    }
    with open("search_conf.json", "w") as f:
        json.dump(search_conf, f, indent=4)
except json.JSONDecodeError:
    # Handle corrupted JSON file
    search_conf = {
        "start_year": 2020,
        "end_year": 2024,
        "venue_rank_list": ["A", "B", "C"],
        "proxy_key": "",
        "initial_file": "seed.txt",
        "db_path": "database.db"
    }
    with open("search_conf.json", "w") as f:
        json.dump(search_conf, f, indent=4)

# Global variables for tracking progress
progress_data = {
    'is_running': False,
    'current_step': '',
    'progress_percent': 0,
    'total_items': 0,
    'processed_items': 0,
    'results': []
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_titles_from_file(file_path: str):
    """Extract titles from a text file with one title per line."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f.readlines() if line.strip()]

def extract_titles_from_json(json_file_path: str):
    """Extract titles from a JSON file."""
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        titles = []
        if 'papers' not in data:
            return []
        for paper in data['papers']:
            if 'title' not in paper:
                continue
            titles.append(paper['title'])
        return titles
    except Exception as e:
        print(f"Error reading JSON file: {e}")
        return []

def create_mock_article_data(title: str, iteration: int) -> ArticleData:
    """Create mock article data when Google Scholar is not accessible."""
    mock_id = hashlib.md5(title.encode('utf-8')).hexdigest()
    
    mock_data = {
        "id": mock_id,
        "container_type": "Unknown",
        "eprint_url": "",
        "source": "Mock",
        "title": title,
        "authors": "Unknown Authors",
        "venue": "Unknown Venue",
        "pub_year": "2020",
        "pub_url": "",
        "num_citations": 0,
        "citedby_url": "",
        "url_related_articles": "",
        "new_pub": True,
        "selected": SelectionStage.SELECTED,
        "iteration": iteration
    }
    
    return ArticleData(**mock_data)

def search_google_scholar(title: str, iteration: int):
    """Search Google Scholar for a paper title."""
    try:
        search_query = scholarly.search_pubs(title)
        result = next(search_query, None)
        
        if result is None:
            return None
        
        scholar_id = result.get('citedby_url')
        if scholar_id is None:
            id = hashlib.md5(title.encode('utf-8')).hexdigest()
            article_data = get_article_data(result, id, iteration, new_pub=True, selected=SelectionStage.SELECTED)
            return article_data
        
        match = re.search(r"cites=(\d+)", scholar_id)
        if match is None:
            return None
        id = int(match.group(1))
        article_data = get_article_data(result, id, iteration, new_pub=True, selected=SelectionStage.SELECTED)
        return article_data
    
    except Exception as e:
        print(f"Error searching for '{title}': {e}")
        return None

def run_snowball_start_thread(input_file: str, delay: float, db_path: str):
    """Background thread for running snowball start initialization."""
    global progress_data
    
    try:
        progress_data['is_running'] = True
        progress_data['current_step'] = 'Initializing snowball sampling...'
        progress_data['progress_percent'] = 0
        
        # Import the snowball start functionality
        from utils.db_management import DBManager, initialize_db, SelectionStage, get_article_data
        import hashlib
        import re
        
        # Initialize database
        db_manager = initialize_db(db_path, 0)
        
        # Extract titles from file
        if input_file.endswith('.json'):
            with open(input_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            titles = []
            if 'papers' in data:
                for paper in data['papers']:
                    if 'title' in paper:
                        titles.append(paper['title'])
        elif input_file.endswith('.txt'):
            with open(input_file, 'r', encoding='utf-8') as f:
                titles = [line.strip() for line in f.readlines() if line.strip()]
        else:
            progress_data['current_step'] = 'Error: Unsupported file type'
            progress_data['is_running'] = False
            return
        
        if not titles:
            progress_data['current_step'] = 'Error: No titles found'
            progress_data['is_running'] = False
            return
        
        progress_data['total_items'] = len(titles)
        progress_data['processed_items'] = 0
        progress_data['current_step'] = f'Processing {len(titles)} initial papers...'
        
        # Process each title
        initial_pubs = []
        seen_titles = []
        
        for i, title in enumerate(titles):
            progress_data['processed_items'] = i + 1
            progress_data['progress_percent'] = int((i + 1) / len(titles) * 100)
            progress_data['current_step'] = f'Searching for: {title[:50]}...'
            
            try:
                # Search Google Scholar
                search_query = scholarly.search_pubs(title)
                result = next(search_query, None)
                
                if result is None:
                    continue
                
                scholar_id = result.get('citedby_url')
                if scholar_id is None:
                    id = hashlib.md5(title.encode('utf-8')).hexdigest()
                    article_data = get_article_data(result, id, 0, new_pub=True, selected=SelectionStage.NOT_SELECTED)
                else:
                    match = re.search(r"cites=(\d+)", scholar_id)
                    if match is None:
                        continue
                    id = int(match.group(1))
                    article_data = get_article_data(result, id, 0, new_pub=True, selected=SelectionStage.NOT_SELECTED)
                
                initial_pubs.append(article_data)
                seen_titles.append((title, article_data.id))
                
            except Exception as e:
                print(f"Error searching for '{title}': {e}")
                continue
            
            time.sleep(delay)
        
        # Save to database
        progress_data['current_step'] = 'Saving to database...'
        db_manager.insert_iteration_data(initial_pubs)
        db_manager.insert_seen_titles_data(seen_titles)
        
        progress_data['current_step'] = 'Snowball initialization completed successfully!'
        progress_data['is_running'] = False
        
    except Exception as e:
        progress_data['current_step'] = f'Error: {str(e)}'
        progress_data['is_running'] = False

def process_papers_thread(input_file: str, delay: float, db_path: str):
    """Background thread for processing papers."""
    global progress_data
    
    try:
        progress_data['is_running'] = True
        progress_data['current_step'] = 'Reading input file...'
        progress_data['progress_percent'] = 0
        
        # Extract titles
        if input_file.endswith('.json'):
            titles = extract_titles_from_json(input_file)
        elif input_file.endswith('.txt'):
            titles = extract_titles_from_file(input_file)
        else:
            progress_data['current_step'] = 'Error: Unsupported file type'
            progress_data['is_running'] = False
            return
        
        if not titles:
            progress_data['current_step'] = 'Error: No titles found'
            progress_data['is_running'] = False
            return
        
        progress_data['total_items'] = len(titles)
        progress_data['processed_items'] = 0
        progress_data['current_step'] = f'Processing {len(titles)} papers...'
        
        # Initialize database
        db_manager = initialize_db(db_path, 0)
        
        # Process each title
        results = []
        for i, title in enumerate(titles):
            progress_data['processed_items'] = i + 1
            progress_data['progress_percent'] = int((i + 1) / len(titles) * 100)
            progress_data['current_step'] = f'Searching for: {title[:50]}...'
            
            article_data = search_google_scholar(title, 0)
            
            if article_data:
                results.append({
                    'title': title,
                    'status': 'Found',
                    'data': article_data.__dict__
                })
            else:
                # Create mock data
                mock_data = create_mock_article_data(title, 0)
                results.append({
                    'title': title,
                    'status': 'Mock data created',
                    'data': mock_data.__dict__
                })
            
            time.sleep(delay)
        
        # Save to database
        progress_data['current_step'] = 'Saving to database...'
        article_objects = []
        seen_titles = []
        
        for result in results:
            article_data = ArticleData(**result['data'])
            article_objects.append(article_data)
            seen_titles.append((result['title'], article_data.id))
        
        db_manager.insert_iteration_data(article_objects)
        db_manager.insert_seen_titles_data(seen_titles)
        
        progress_data['results'] = results
        progress_data['current_step'] = 'Completed successfully!'
        progress_data['is_running'] = False
        
    except Exception as e:
        progress_data['current_step'] = f'Error: {str(e)}'
        progress_data['is_running'] = False

@app.route('/')
def main():
    """Main dashboard page."""
    return render_template('main.html')

@app.route('/upload')
def upload_page():
    """Upload page."""
    return render_template('upload.html')

@app.route('/snowball-start')
def snowball_start():
    """Snowball start page."""
    return render_template('snowball_start.html')

@app.route('/run-snowball-start', methods=['POST'])
def run_snowball_start():
    """Handle snowball start execution."""
    if 'input_file' not in request.files:
        flash('No file selected')
        return redirect(url_for('snowball_start'))
    
    file = request.files['input_file']
    if file.filename == '':
        flash('No file selected')
        return redirect(url_for('snowball_start'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Get form data
        db_path = request.form.get('db_path', 'database.db')
        delay = float(request.form.get('delay', 2.0))
        proxy_key = request.form.get('proxy_key', '')
        
        # Update search configuration
        search_conf.update({
            'proxy_key': proxy_key,
            'db_path': db_path,
            'delay': delay
        })
        
        # Save updated configuration
        with open('search_conf.json', 'w') as f:
            json.dump(search_conf, f, indent=4)
        
        # Start background processing for snowball start
        thread = threading.Thread(target=run_snowball_start_thread, args=(filepath, delay, db_path))
        thread.daemon = True
        thread.start()
        
        flash('Snowball initialization started! This may take several minutes.')
        return redirect(url_for('progress'))
    
    flash('Invalid file type. Please upload a .txt or .json file.')
    return redirect(url_for('snowball_start'))

@app.route('/upload_file', methods=['POST'])
def upload_file():
    """Handle file upload."""
    if 'file' not in request.files:
        flash('No file selected')
        return redirect(request.url)
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected')
        return redirect(request.url)
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Get form data
        delay = float(request.form.get('delay', 2.0))
        db_path = request.form.get('db_path', search_conf['db_path'])
        start_year = int(request.form.get('start_year', search_conf.get('start_year', 2020)))
        end_year = int(request.form.get('end_year', search_conf.get('end_year', 2024)))
        accepted_ranks = request.form.get('accepted_ranks', ','.join(search_conf.get('venue_rank_list', ['A', 'B', 'C'])))
        proxy_key = request.form.get('proxy_key', search_conf.get('proxy_key', ''))
        final_csv = request.form.get('final_csv', search_conf.get('final_csv', 'results.csv'))
        
        # Update search configuration with form data
        search_conf.update({
            'start_year': start_year,
            'end_year': end_year,
            'venue_rank_list': [rank.strip() for rank in accepted_ranks.split(',')],
            'proxy_key': proxy_key,
            'final_csv': final_csv,
            'db_path': db_path,
            'delay': delay
        })
        
        # Save updated configuration
        with open('search_conf.json', 'w') as f:
            json.dump(search_conf, f, indent=4)
        
        # Start background processing
        thread = threading.Thread(target=process_papers_thread, args=(filepath, delay, db_path))
        thread.daemon = True
        thread.start()
        
        flash('File uploaded and processing started!')
        return redirect(url_for('progress'))
    
    flash('Invalid file type. Please upload a .txt or .json file.')
    return redirect(url_for('upload_page'))

@app.route('/progress')
def progress():
    """Progress monitoring page."""
    return render_template('progress.html')

@app.route('/api/progress')
def api_progress():
    """API endpoint for progress updates."""
    # Convert progress_data to JSON-serializable format
    serializable_data = {
        'is_running': progress_data['is_running'],
        'current_step': progress_data['current_step'],
        'progress_percent': progress_data['progress_percent'],
        'total_items': progress_data['total_items'],
        'processed_items': progress_data['processed_items'],
        'results': []
    }
    
    # Convert results to serializable format
    for result in progress_data.get('results', []):
        if isinstance(result, dict) and 'data' in result:
            # Convert ArticleData object to dict
            data_dict = result['data'].__dict__ if hasattr(result['data'], '__dict__') else result['data']
            serializable_data['results'].append({
                'title': result.get('title', ''),
                'status': result.get('status', ''),
                'data': data_dict
            })
    
    return jsonify(serializable_data)

@app.route('/results')
def results():
    """Results page."""
    if not progress_data['results']:
        flash('No results available. Please run a search first.')
        return redirect(url_for('main'))
    
    return render_template('results.html', results=progress_data['results'])

@app.route('/database')
def database_view():
    """Database viewer page."""
    db_path = request.args.get('db_path', search_conf.get('db_path', 'database.db'))
    
    try:
        db_manager = DBManager(db_path)
        
        # Get iteration data
        iteration_data = db_manager.get_iteration_data()
        
        # Get seen titles data
        seen_titles = db_manager.get_seen_titles_data()
        
        return render_template('database.html', 
                             iteration_data=iteration_data,
                             seen_titles=seen_titles,
                             db_path=db_path)
    except Exception as e:
        return render_template('database.html', 
                             iteration_data=None,
                             seen_titles=None,
                             db_path=db_path,
                             error=f'Error accessing database: {str(e)}')

@app.route('/api/reset')
def reset_progress():
    """Reset progress data."""
    global progress_data
    progress_data = {
        'is_running': False,
        'current_step': '',
        'progress_percent': 0,
        'total_items': 0,
        'processed_items': 0,
        'results': []
    }
    return jsonify({'status': 'reset'})

@app.route('/api/generate_search_conf', methods=['POST'])
def generate_search_conf_api():
    """Generate search configuration and return JSON content."""
    try:
        # Get form data from request
        data = request.get_json()
        
        # Create search configuration with form data or defaults
        config = {
            "start_year": data.get('start_year', 2020),
            "end_year": data.get('end_year', 2024),
            "venue_rank_list": data.get('accepted_ranks', ["A", "B", "C"]),
            "proxy_key": data.get('proxy_key', ""),
            "final_csv": data.get('final_csv', "results.csv"),
            "initial_file": "seed.txt",
            "db_path": data.get('db_path', "database.db")
        }
        
        # Write the configuration to search_conf.json
        with open('search_conf.json', 'w') as f:
            json.dump(config, f, indent=4)
        
        return jsonify({
            'success': True,
            'json_content': config,
            'message': 'Search configuration generated successfully!'
        })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Unexpected error: {str(e)}'
        }), 500

if __name__ == '__main__':
    # Try to set up proxy
    try:
        pg = get_proxy(search_conf["proxy_key"])
        if pg:
            try:
                scholarly.use_proxy(pg)
                print("Proxy successfully configured")
            except Exception as e:
                print(f"Could not apply proxy to scholarly: {e}")
                print("Continuing without proxy...")
        else:
            print("No proxy available, continuing without proxy...")
    except Exception as e:
        print(f"Proxy setup failed: {e}")
        print("Continuing without proxy...")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
