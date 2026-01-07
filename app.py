#!/usr/bin/env python3
"""
ProfOlaf Web Application - Entry Point
"""

import os
import json
import threading
from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, send_file
from pathlib import Path
from collections import defaultdict
from utils.db_management import DBManager, SelectionStage, initialize_db
from utils.article_search_method import SearchMethod, ArticleSearch
from werkzeug.utils import secure_filename
import importlib.util

# Import generate_snowball_start from 0_generate_snowball_start.py
spec = importlib.util.spec_from_file_location("generate_snowball_start_module", "0_generate_snowball_start.py")
generate_snowball_start_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generate_snowball_start_module)
generate_snowball_start = generate_snowball_start_module.generate_snowball_start
extract_titles_from_file = generate_snowball_start_module.extract_titles_from_file

# Import start_iteration from 1_start_iteration.py
spec_iter = importlib.util.spec_from_file_location("start_iteration_module", "1_start_iteration.py")
start_iteration_module = importlib.util.module_from_spec(spec_iter)
spec_iter.loader.exec_module(start_iteration_module)
get_articles = start_iteration_module.get_articles

# Import get_bibtex from 2_get_bibtex.py
spec_bibtex = importlib.util.spec_from_file_location("get_bibtex_module", "2_get_bibtex.py")
get_bibtex_module = importlib.util.module_from_spec(spec_bibtex)
spec_bibtex.loader.exec_module(get_bibtex_module)
process_articles_optimized = get_bibtex_module.process_articles_optimized
get_bibtex_single = get_bibtex_module.get_bibtex_single

# Import generate_conf_rank from 3_generate_conf_rank.py
spec_conf_rank = importlib.util.spec_from_file_location("generate_conf_rank_module", "3_generate_conf_rank.py")
generate_conf_rank_module = importlib.util.module_from_spec(spec_conf_rank)
spec_conf_rank.loader.exec_module(generate_conf_rank_module)
get_venues = generate_conf_rank_module.get_venues
find_similar_venues = generate_conf_rank_module.find_similar_venues
_get_scimago_rank = generate_conf_rank_module._get_scimago_rank
_get_core_rank = generate_conf_rank_module._get_core_rank

# Import filter_by_metadata from 4_filter_by_metadata.py
spec_filter_metadata = importlib.util.spec_from_file_location("filter_metadata_module", "4_filter_by_metadata.py")
filter_metadata_module = importlib.util.module_from_spec(spec_filter_metadata)
spec_filter_metadata.loader.exec_module(filter_metadata_module)
automated_check_venue_and_peer_reviewed = filter_metadata_module.automated_check_venue_and_peer_reviewed

# Global state for tracking running tasks
running_tasks = {
    'generate_snowball_start': {
        'is_running': False,
        'progress': 0,
        'total': 0,
        'current_step': '',
        'logs': [],
        'cancel_flag': None
    },
    'start_iteration': {
        'is_running': False,
        'progress': 0,
        'total': 0,
        'current_step': '',
        'logs': [],
        'cancel_flag': None
    },
    'get_bibtex': {
        'is_running': False,
        'progress': 0,
        'total': 0,
        'current_step': '',
        'logs': [],
        'cancel_flag': None
    }
}

ITERATION_0 = 0

# Configuration for file uploads
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'txt', 'json'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Configuration file path
SEARCH_CONF_PATH = "search_conf.json"
WORKFLOW_STATE_PATH = "workflow_state.json"


def load_workflow_state():
    """Load workflow state from JSON file"""
    try:
        if os.path.exists(WORKFLOW_STATE_PATH):
            with open(WORKFLOW_STATE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            return {
                'db_path': None,
                'current_iteration': None,
                'last_step': None,
                'skipped_steps': []
            }
    except Exception as e:
        print(f"Error loading workflow state: {e}")
        return {
            'db_path': None,
            'current_iteration': None,
            'last_step': None,
            'skipped_steps': []
        }


def save_workflow_state(state):
    """Save workflow state to JSON file"""
    try:
        with open(WORKFLOW_STATE_PATH, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving workflow state: {e}")
        return False


def get_db_manager_for_workflow():
    """Helper function to get DBManager for workflow metadata operations"""
    search_conf = load_search_conf()
    if search_conf and 'db_path' in search_conf:
        db_path = search_conf['db_path']
    else:
        db_path = 'database.db'
    
    if not os.path.exists(db_path):
        return None
    
    try:
        db_manager = DBManager(db_path)
        # Ensure workflow metadata table exists (for existing databases)
        try:
            db_manager.create_workflow_metadata_table()
        except:
            pass  # Table might already exist
        return db_manager
    except Exception as e:
        print(f"Error creating DBManager for workflow: {e}")
        return None


def update_workflow_state(db_path=None, current_iteration=None, last_step=None, skip_step=None):
    """Update workflow state in both database and JSON file (for backwards compatibility)"""
    state = load_workflow_state()
    
    # Ensure skipped_steps list exists
    if 'skipped_steps' not in state:
        state['skipped_steps'] = []
    
    if db_path is not None:
        state['db_path'] = db_path
    if current_iteration is not None:
        state['current_iteration'] = current_iteration
    if last_step is not None:
        state['last_step'] = last_step
    if skip_step is not None:
        # Add step to skipped list if not already there
        if skip_step not in state['skipped_steps']:
            state['skipped_steps'].append(skip_step)
    
    # Update database metadata (primary source)
    db_manager = get_db_manager_for_workflow()
    if db_manager:
        try:
            if current_iteration is not None:
                db_manager.update_current_iteration(current_iteration)
            if last_step is not None:
                db_manager.update_last_step(last_step)
            db_manager.conn.close()
        except Exception as e:
            print(f"Error updating workflow metadata in database: {e}")
    
    # Also save to JSON for backwards compatibility
    save_workflow_state(state)
    return state


def get_next_step_after_skip(current_step):
    """Determine the next logical step after skipping a step"""
    step_map = {
        "Step 0: Generate Snowball Start": "Step 1: Start Iteration",
        "Step 1: Start Iteration": "Step 2: Get BibTeX",
        "Step 2: Get BibTeX": "Step 3: Assign Venue Ranks",
        "Step 3: Assign Venue Ranks": "Step 4: Filter by Metadata",
        "Step 4: Filter by Metadata": "Step 5: Filter by Title",
        "Step 5: Filter by Title": "Step 6: Solve Title Disagreements",
        "Step 6: Solve Title Disagreements": "Step 7: Filter by Content",
        "Step 7: Filter by Content": "Step 8: Solve Content Disagreements",
        "Step 8: Solve Content Disagreements": "Step 9: Remove Duplicates",
        "Step 9: Remove Duplicates": "Step 10: Generate CSV"
    }
    return step_map.get(current_step, None)


def generate_search_conf(data):
    """
    Generate search configuration dictionary from form data.
    
    Args:
        data: Dictionary containing form data
        
    Returns:
        Dictionary containing the search configuration
    """
    # Parse venue ranks from comma-separated string
    venue_list_str = data.get('venue_rank_list', '')
    venue_list = [v.strip() for v in venue_list_str.split(',') if v.strip()]
    
    # Parse annotations from newline-separated string
    annotations_str = data.get('annotations', '')
    annotations = [a.strip() for a in annotations_str.split('\n') if a.strip()]
    
    # Handle proxy key - check if it's a file path or direct value
    proxy_key = data.get('proxy_key', '').strip()
    if proxy_key and data.get('proxy_from_file') == 'true':
        # Read proxy key from file
        try:
            with open(proxy_key, 'r', encoding='utf-8') as f:
                proxy_key = f.read().strip()
        except Exception as e:
            raise ValueError(f"Failed to read proxy key file: {str(e)}")
    
    config = {
        "start_year": int(data.get('start_year', 2020)),
        "end_year": int(data.get('end_year', 2024)),
        "venue_rank_list": venue_list,
        "proxy_key": proxy_key,
        "initial_file": data.get('initial_file', 'seed.txt'),
        "db_path": data.get('db_path', 'database.db'),
        "csv_path": data.get('csv_path', 'results.csv'),
        "search_method": data.get('search_method', 'google_scholar'),
        "annotations": annotations
    }
    
    return config


def load_search_conf():
    """Load search configuration if it exists"""
    if os.path.exists(SEARCH_CONF_PATH):
        try:
            with open(SEARCH_CONF_PATH, 'r') as f:
                return json.load(f)
        except Exception:
            return None
    return None


def get_current_iteration_from_db(db_manager, all_articles):
    """
    Determine the current iteration from the database.
    First checks if there's a stored current_iteration in search_conf.
    Otherwise falls back to MAX(iteration) from articles.
    """
    # Try to get from search_conf first
    search_conf = load_search_conf()
    if search_conf and 'current_iteration' in search_conf:
        stored_iteration = search_conf['current_iteration']
        if stored_iteration is not None:
            try:
                return int(stored_iteration)
            except (ValueError, TypeError):
                pass
    
    # Fall back to database method
    try:
        result = db_manager.check_current_iteration()
        if result:
            iteration = result[0]
            if iteration is not None:
                try:
                    return int(iteration)
                except (ValueError, TypeError):
                    pass
    except:
        pass
    
    # Last resort: calculate from articles
    if all_articles:
        iteration_max = 0
        for article in all_articles:
            try:
                iter_num = int(article.iteration) if article.iteration else 0
                iteration_max = max(iteration_max, iter_num)
            except (ValueError, TypeError):
                continue
        return iteration_max if iteration_max >= 0 else None
    
    return None


def update_current_iteration(iteration):
    """
    Update the current_iteration in search_conf.json
    """
    search_conf = load_search_conf()
    if search_conf is None:
        search_conf = {}
    
    try:
        iteration_int = int(iteration)
        search_conf['current_iteration'] = iteration_int
        
        with open(SEARCH_CONF_PATH, 'w') as f:
            json.dump(search_conf, f, indent=4)
        return True
    except (ValueError, TypeError, Exception):
        return False


def get_workflow_info():
    """
    Get workflow information (current iteration, step, counts, etc.)
    Returns a dictionary with workflow_info or None if database doesn't exist
    """
    search_conf = load_search_conf()
    
    # Get database path
    if search_conf and 'db_path' in search_conf:
        db_path = search_conf['db_path']
    else:
        db_path = 'database.db'
    
    db_exists = os.path.exists(db_path)
    
    # Load workflow state (used as fallback/primary source)
    workflow_state = load_workflow_state()
    
    if not db_exists:
        return {
            'current_iteration': workflow_state.get('current_iteration'),
            'current_step': workflow_state.get('last_step', "Step 0: Generate Snowball Start"),
            'content_approved_count': 0,
            'new_articles_count': 0,
            'total_articles': 0,
            'search_method': None
        }
    
    try:
        db_manager = DBManager(db_path)
        
        # Ensure workflow metadata table exists
        try:
            db_manager.create_workflow_metadata_table()
        except:
            pass  # Table might already exist
        
        # Try to get current iteration and last step from database metadata (primary source)
        current_iteration = db_manager.get_current_iteration()
        current_step = db_manager.get_last_step()
        
        # If database doesn't have metadata yet, try to migrate from workflow_state.json
        if current_iteration is None and workflow_state.get('current_iteration') is not None:
            current_iteration = workflow_state.get('current_iteration')
            db_manager.update_current_iteration(current_iteration)
        
        if current_step is None and workflow_state.get('last_step') is not None:
            current_step = workflow_state.get('last_step')
            db_manager.update_last_step(current_step)
        
        # If still no current iteration, try to infer from database
        if current_iteration is None:
            all_articles = db_manager.get_iteration_data()
            current_iteration = get_current_iteration_from_db(db_manager, all_articles)
            if current_iteration is not None:
                db_manager.update_current_iteration(current_iteration)
        
        # If still no current step, set default
        if current_step is None:
            current_step = "Step 0: Generate Snowball Start"
        
        # Get all articles to calculate stats
        all_articles = db_manager.get_iteration_data()
        
        # Get max_selected and search_method for the current iteration
        max_selected = None
        search_method = None
        if current_iteration is not None:
            try:
                result = db_manager.check_current_iteration()
                if result:
                    iter_from_db, max_selected, search_method = result
            except:
                pass
        
        # Only infer step if we don't have an explicit last_step from database
        # For iteration 0, always show "Step 0" since articles are auto-approved but never went through Step 7
        if current_step is None:
            # Need to infer step
            if current_iteration == 0:
                # For iteration 0, default to Step 0 (articles are automatically content_approved but didn't go through that step)
                current_step = "Step 0: Generate Snowball Start"
                # Save this to database
                try:
                    db_manager.update_last_step(current_step)
                except:
                    pass
            elif current_iteration is not None:
                if max_selected is not None:
                    try:
                        max_selected_int = int(max_selected)
                        if max_selected_int == 0:
                            current_step = "Step 1-2: Initial Setup & BibTeX"
                        elif max_selected_int == 1:
                            current_step = "Step 4: Filter by Metadata"
                        elif max_selected_int == 2:
                            current_step = "Step 5: Title Screening"
                        elif max_selected_int == 3:
                            # Only infer Step 7 if we're not on iteration 0
                            # (iteration 0 articles are auto-approved, but iteration > 0 articles need to go through the step)
                            current_step = "Step 7: Content Screening"
                        else:
                            current_step = f"Step: Selection Stage {max_selected_int}"
                    except (ValueError, TypeError):
                        current_step = "Step: Unknown"
                    
                    # Save inferred step to database
                    try:
                        db_manager.update_last_step(current_step)
                    except:
                        pass
                else:
                    if all_articles:
                        has_bibtex = any(getattr(a, 'bibtex', '') for a in all_articles if hasattr(a, 'bibtex'))
                        if has_bibtex:
                            current_step = "Step 3: Assign Venue Ranks"
                        else:
                            current_step = "Step 2: Get BibTeX"
                    else:
                        current_step = "Step 0: Generate Snowball Start"
                    
                    # Save inferred step to database
                    try:
                        db_manager.update_last_step(current_step)
                    except:
                        pass
        elif current_step == "Step 0: Generate Snowball Start" and current_iteration == 0:
            # If we have Step 0 and we're on iteration 0, make sure it's saved (might have been inferred before)
            try:
                db_manager.update_last_step(current_step)
            except:
                pass
        
        # Count content approved papers (selected = 3)
        content_approved_count = 0
        for article in all_articles:
            try:
                selected = int(article.selected) if article.selected is not None else 0
                if selected == 3:  # CONTENT_APPROVED
                    content_approved_count += 1
            except (ValueError, TypeError):
                continue
        
        # Count articles in current iteration
        new_articles_count = 0
        if current_iteration is not None:
            try:
                current_iter_int = int(current_iteration)
                for article in all_articles:
                    try:
                        article_iter = getattr(article, 'iteration', None)
                        if article_iter is not None:
                            article_iter_int = int(article_iter)
                            if article_iter_int == current_iter_int:
                                new_articles_count += 1
                    except (ValueError, TypeError, AttributeError):
                        continue
            except (ValueError, TypeError):
                new_articles_count = 0
        
        workflow_info = {
            'current_iteration': current_iteration,
            'current_step': current_step,
            'content_approved_count': content_approved_count,
            'new_articles_count': new_articles_count,
            'total_articles': len(all_articles),
            'search_method': search_method
        }
        
        # Close database connection
        db_manager.conn.close()
        
        # Sync workflow state JSON with database for backwards compatibility
        if workflow_state.get('db_path') != db_path or workflow_state.get('current_iteration') != current_iteration or workflow_state.get('last_step') != current_step:
            update_workflow_state(
                db_path=db_path,
                current_iteration=current_iteration,
                last_step=current_step
            )
        
        return workflow_info
        
    except Exception as e:
        return {
            'current_iteration': None,
            'current_step': "Error",
            'content_approved_count': 0,
            'new_articles_count': 0,
            'total_articles': 0,
            'search_method': None,
            'error': str(e)
        }


@app.route('/')
def index():
    """Main dashboard page"""
    # Check if search_conf.json exists
    config_exists = os.path.exists(SEARCH_CONF_PATH)
    
    # Check if database exists (from config if available)
    db_exists = False
    db_path = None
    search_conf = load_search_conf()
    if search_conf and 'db_path' in search_conf:
        db_path = search_conf['db_path']
        db_exists = os.path.exists(db_path)
    
    return render_template('index.html', 
                         config_exists=config_exists,
                         db_exists=db_exists,
                         db_path=db_path)


@app.route('/generate_search_conf', methods=['GET', 'POST'])
def generate_search_conf_route():
    """Generate search configuration"""
    if request.method == 'GET':
        # Show the form
        return render_template('generate_search_conf.html')
    
    # Handle POST request
    try:
        # Get form data
        form_data = request.form.to_dict()
        
        # Validate required fields
        if not form_data.get('start_year') or not form_data.get('end_year'):
            flash('Start year and end year are required', 'error')
            return redirect(url_for('generate_search_conf_route'))
        
        if not form_data.get('initial_file'):
            flash('Initial file is required', 'error')
            return redirect(url_for('generate_search_conf_route'))
        
        if not form_data.get('db_path'):
            flash('Database path is required', 'error')
            return redirect(url_for('generate_search_conf_route'))
        
        if not form_data.get('csv_path'):
            flash('CSV path is required', 'error')
            return redirect(url_for('generate_search_conf_route'))
        
        # Validate year range
        start_year = int(form_data.get('start_year'))
        end_year = int(form_data.get('end_year'))
        
        if start_year >= end_year:
            flash('Starting year must be less than ending year', 'error')
            return redirect(url_for('generate_search_conf_route'))
        
        # Generate configuration
        config = generate_search_conf(form_data)
        
        # Save to file
        with open(SEARCH_CONF_PATH, 'w') as f:
            json.dump(config, f, indent=4)
        
        flash('Search configuration generated successfully!', 'success')
        return redirect(url_for('configuration'))
        
    except ValueError as e:
        flash(f'Validation error: {str(e)}', 'error')
        return redirect(url_for('generate_search_conf_route'))
    except Exception as e:
        flash(f'Error generating configuration: {str(e)}', 'error')
        return redirect(url_for('generate_search_conf_route'))


@app.route('/configuration', methods=['GET'])
def configuration():
    """Configuration page - view and generate search configuration"""
    config_exists = os.path.exists(SEARCH_CONF_PATH)
    current_config = None
    
    if config_exists:
        try:
            with open(SEARCH_CONF_PATH, 'r') as f:
                current_config = json.load(f)
        except Exception:
            current_config = None
    
    return render_template('configuration.html', 
                         config_exists=config_exists, 
                         current_config=current_config)


@app.route('/api/database/load', methods=['POST'])
def load_database():
    """Load a new database file and update search_conf.json"""
    try:
        data = request.get_json()
        if not data or 'db_path' not in data:
            return jsonify({'success': False, 'error': 'Database path not provided'}), 400
        
        db_path = data['db_path'].strip()
        if not db_path:
            return jsonify({'success': False, 'error': 'Database path cannot be empty'}), 400
        
        # Validate that the database file exists
        if not os.path.exists(db_path):
            return jsonify({
                'success': False, 
                'error': f'Database file not found: {db_path}. Please check the path and try again.'
            }), 404
        
        # Verify it's a valid SQLite database (basic check)
        try:
            db_manager = DBManager(db_path)
            # Try to query the database to verify it's valid
            _ = db_manager.get_iteration_data()
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'Invalid database file: {str(e)}'
            }), 400
        
        # Load current search_conf
        search_conf = load_search_conf()
        if search_conf is None:
            # Create a new configuration if it doesn't exist
            search_conf = {
                'start_year': 2020,
                'end_year': 2024,
                'venue_rank_list': ['A*', 'A', 'B', 'C', 'Q1', 'Q2'],
                'proxy_key': '',
                'initial_file': 'seed.txt',
                'db_path': db_path,
                'csv_path': 'results.csv',
                'search_method': 'google_scholar',
                'annotations': ['Methods', 'Area'],
                'current_iteration': None
            }
        else:
            # Update the db_path in existing configuration
            search_conf['db_path'] = db_path
        
        # Save updated search_conf
        with open(SEARCH_CONF_PATH, 'w') as f:
            json.dump(search_conf, f, indent=4)
        
        return jsonify({
            'success': True,
            'message': f'Database loaded successfully: {db_path}',
            'db_path': db_path
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error loading database: {str(e)}'
        }), 500


@app.route('/database', methods=['GET'])
def database_state():
    """Database state page - displays database statistics"""
    search_conf = load_search_conf()
    if search_conf and 'db_path' in search_conf:
        db_path = search_conf['db_path']
    else:
        db_path = 'database.db'
    
    db_exists = os.path.exists(db_path)
    db_error = None
    db_stats = None
    iteration_stats = []
    articles_display = []
    
    if db_exists:
        try:
            db_manager = DBManager(db_path)
            
            # Get all iteration data
            all_articles = db_manager.get_iteration_data()
            
            # Calculate statistics
            total_articles = len(all_articles)
            
            # Group by iteration
            by_iteration = defaultdict(int)
            by_selection_stage = defaultdict(int)
            iteration_max = 0
            
            for article in all_articles:
                # Convert iteration to int (it might be stored as string in DB)
                iter_num = 0
                if hasattr(article, 'iteration'):
                    try:
                        iter_num = int(article.iteration) if article.iteration else 0
                    except (ValueError, TypeError):
                        iter_num = 0
                
                by_iteration[iter_num] += 1
                iteration_max = max(iteration_max, iter_num)
                
                # Convert selected to int (it might be stored as string in DB)
                selected = 0
                if hasattr(article, 'selected'):
                    try:
                        selected = int(article.selected) if article.selected is not None else 0
                    except (ValueError, TypeError):
                        selected = 0
                
                by_selection_stage[selected] += 1
            
            # Get iteration statistics
            for iter_num in range(iteration_max + 1):
                # Filter articles for this iteration, converting to int for comparison
                iter_articles = []
                for a in all_articles:
                    if hasattr(a, 'iteration'):
                        try:
                            article_iter = int(a.iteration) if a.iteration else 0
                            if article_iter == iter_num:
                                iter_articles.append(a)
                        except (ValueError, TypeError):
                            continue
                
                iter_count = len(iter_articles)
                
                if iter_count > 0:
                    # Count by selection stage for this iteration
                    iter_selection_counts = defaultdict(int)
                    for article in iter_articles:
                        selected = 0
                        if hasattr(article, 'selected'):
                            try:
                                selected = int(article.selected) if article.selected is not None else 0
                            except (ValueError, TypeError):
                                selected = 0
                        iter_selection_counts[selected] += 1
                    
                    iteration_stats.append({
                        'iteration': iter_num,
                        'total': iter_count,
                        'not_selected': iter_selection_counts.get(0, 0),
                        'metadata_approved': iter_selection_counts.get(1, 0),
                        'title_approved': iter_selection_counts.get(2, 0),
                        'content_approved': iter_selection_counts.get(3, 0),
                        'duplicate': iter_selection_counts.get(-1, 0)
                    })
            
            # Try to get current iteration info
            try:
                result = db_manager.check_current_iteration()
                if result:
                    current_iteration, max_selected, search_method = result
                    if current_iteration is None:
                        current_iteration = iteration_max if iteration_max >= 0 else None
                else:
                    current_iteration = iteration_max if iteration_max >= 0 else None
                    max_selected = None
                    search_method = None
            except:
                current_iteration = iteration_max if iteration_max >= 0 else None
                max_selected = None
                search_method = None
            
            # Get seen titles count
            try:
                seen_titles = db_manager.get_seen_titles_data()
                seen_titles_count = len(seen_titles) if seen_titles else 0
            except:
                seen_titles_count = 0
            
            db_stats = {
                'total_articles': total_articles,
                'total_iterations': iteration_max + 1 if iteration_max >= 0 else 0,
                'current_iteration': current_iteration,
                'search_method': search_method,
                'seen_titles_count': seen_titles_count,
                'by_selection_stage': dict(by_selection_stage)
            }
            
            # Prepare articles for display (limit to first 1000 for performance)
            articles_display = []
            for article in all_articles[:1000]:  # Limit for performance
                try:
                    iter_num = int(article.iteration) if article.iteration else 0
                except (ValueError, TypeError):
                    iter_num = 0
                
                try:
                    selected = int(article.selected) if article.selected is not None else 0
                except (ValueError, TypeError):
                    selected = 0
                
                articles_display.append({
                    'id': getattr(article, 'id', ''),
                    'title': getattr(article, 'title', '') or '(No title)',
                    'authors': getattr(article, 'authors', '') or '(No authors)',
                    'venue': getattr(article, 'venue', '') or '(No venue)',
                    'pub_year': getattr(article, 'pub_year', '') or '',
                    'iteration': iter_num,
                    'selected': selected,
                    'eprint_url': getattr(article, 'eprint_url', ''),
                    'num_citations': getattr(article, 'num_citations', '') or 0
                })
            
        except Exception as e:
            db_error = str(e)
            articles_display = []
    
    return render_template('database_state.html',
                         db_exists=db_exists,
                         db_path=db_path,
                         db_stats=db_stats,
                         iteration_stats=iteration_stats,
                         articles=articles_display,
                         db_error=db_error,
                         SelectionStage=SelectionStage)


@app.route('/workflow', methods=['GET'])
def workflow_stage():
    """Workflow stage page - shows current workflow progress"""
    search_conf = load_search_conf()
    
    # Get database path
    if search_conf and 'db_path' in search_conf:
        db_path = search_conf['db_path']
    else:
        db_path = 'database.db'
    
    db_exists = os.path.exists(db_path)
    workflow_info = get_workflow_info()
    db_error = workflow_info.get('error') if workflow_info else None
    
    return render_template('workflow_stage.html',
                         search_conf=search_conf,
                         db_exists=db_exists,
                         db_path=db_path,
                         workflow_info=workflow_info,
                         db_error=db_error)


@app.route('/api/search_conf', methods=['GET'])
def get_search_conf():
    """API endpoint to get current search configuration"""
    if not os.path.exists(SEARCH_CONF_PATH):
        return jsonify({'error': 'search_conf.json not found'}), 404
    
    try:
        with open(SEARCH_CONF_PATH, 'r') as f:
            config = json.load(f)
        return jsonify(config)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/workflow/generate_snowball_start', methods=['GET'])
def generate_snowball_start_page():
    """Page for Step 0: Generate Snowball Start"""
    search_conf = load_search_conf()
    
    # Get defaults from config
    default_input_file = search_conf.get('initial_file', '') if search_conf else ''
    default_delay = 1.0
    default_search_method = search_conf.get('search_method', 'google_scholar') if search_conf else 'google_scholar'
    
    task_state = running_tasks['generate_snowball_start']
    workflow_info = get_workflow_info()
    
    return render_template('generate_snowball_start.html',
                         default_input_file=default_input_file,
                         default_delay=default_delay,
                         default_search_method=default_search_method,
                         is_running=task_state['is_running'],
                         logs=task_state['logs'][-50:],  # Last 50 log entries
                         workflow_info=workflow_info)


@app.route('/api/workflow/generate_snowball_start/execute', methods=['POST'])
def execute_generate_snowball_start():
    """Execute the generate snowball start process"""
    task_state = running_tasks['generate_snowball_start']
    
    if task_state['is_running']:
        return jsonify({'error': 'Task is already running'}), 400
    
    try:
        # Get form data
        data = request.get_json() if request.is_json else request.form
        
        input_file = data.get('input_file', '').strip()
        delay = float(data.get('delay', 1.0))
        search_method_str = data.get('search_method', 'google_scholar')
        
        # Validate search method
        try:
            search_method = SearchMethod(search_method_str)
        except ValueError:
            return jsonify({'error': f'Invalid search method: {search_method_str}'}), 400
        
        # Validate input file
        if not input_file:
            return jsonify({'error': 'Input file is required'}), 400
        
        if not os.path.exists(input_file):
            return jsonify({'error': f'Input file does not exist: {input_file}'}), 400
        
        # Get database path from config
        search_conf = load_search_conf()
        if not search_conf or 'db_path' not in search_conf:
            return jsonify({'error': 'Database path not configured. Please set up configuration first.'}), 400
        
        db_path = search_conf['db_path']
        
        # Initialize task state
        task_state['is_running'] = True
        task_state['progress'] = 0
        task_state['total'] = 0
        task_state['current_step'] = 'Starting...'
        task_state['logs'] = []
        cancel_flag = threading.Event()
        task_state['cancel_flag'] = cancel_flag
        
        # Start worker thread
        def worker():
            try:
                # Helper functions for callbacks
                def log(msg):
                    task_state['logs'].append(msg)
                    if len(task_state['logs']) > 1000:  # Limit log size
                        task_state['logs'] = task_state['logs'][-1000:]
                
                def progress(current, total):
                    task_state['progress'] = current
                    task_state['total'] = total
                
                log("Initializing database...")
                db_manager = initialize_db(db_path)
                
                log(f"Starting snowball start generation...")
                log(f"Input file: {input_file}")
                log(f"Search method: {search_method_str}")
                log(f"Delay: {delay} seconds")
                
                # Execute the generation
                generate_snowball_start(
                    input_file=input_file,
                    iteration=ITERATION_0,
                    delay=delay,
                    db_manager=db_manager,
                    search_method=search_method,
                    log_callback=log,
                    progress_callback=progress,
                    cancel_flag=cancel_flag
                )
                
                if not cancel_flag.is_set():
                    log("✓ Generation completed successfully!")
                    # Update current iteration to 0
                    update_current_iteration(ITERATION_0)
                    # Update workflow state
                    update_workflow_state(
                        db_path=db_path,
                        current_iteration=ITERATION_0,
                        last_step="Step 0: Generate Snowball Start"
                    )
                
            except Exception as e:
                task_state['logs'].append(f"Error: {str(e)}")
                import traceback
                task_state['logs'].append(traceback.format_exc())
            finally:
                task_state['is_running'] = False
                task_state['current_step'] = 'Completed' if not cancel_flag.is_set() else 'Cancelled'
                task_state['cancel_flag'] = None
        
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        
        return jsonify({'success': True, 'message': 'Generation started'})
        
    except Exception as e:
        task_state['is_running'] = False
        return jsonify({'error': str(e)}), 500


@app.route('/api/workflow/generate_snowball_start/status', methods=['GET'])
def get_generate_snowball_start_status():
    """Get status of generate snowball start task"""
    task_state = running_tasks['generate_snowball_start']
    return jsonify({
        'is_running': task_state['is_running'],
        'progress': task_state['progress'],
        'total': task_state['total'],
        'current_step': task_state['current_step'],
        'logs': task_state['logs'][-100:]  # Last 100 log entries
    })


@app.route('/api/workflow/generate_snowball_start/cancel', methods=['POST'])
def cancel_generate_snowball_start():
    """Cancel the running generate snowball start task"""
    task_state = running_tasks['generate_snowball_start']
    
    if not task_state['is_running']:
        return jsonify({'error': 'No task is running'}), 400
    
    if task_state['cancel_flag']:
        task_state['cancel_flag'].set()
        task_state['logs'].append("Cancellation requested...")
        return jsonify({'success': True, 'message': 'Cancellation requested'})
    
    return jsonify({'error': 'No cancel flag available'}), 400


@app.route('/workflow/start_iteration', methods=['GET'])
def start_iteration_page():
    """Page for Step 1: Start Iteration"""
    search_conf = load_search_conf()
    
    # Get defaults from config
    default_search_method = search_conf.get('search_method', 'google_scholar') if search_conf else 'google_scholar'
    
    # Get workflow info
    workflow_info = get_workflow_info()
    current_iteration = workflow_info.get('current_iteration') if workflow_info else None
    
    # Default to iteration 1 if no current iteration
    default_iteration = (current_iteration + 1) if current_iteration is not None else 1
    
    task_state = running_tasks['start_iteration']
    
    return render_template('start_iteration.html',
                         default_iteration=default_iteration,
                         default_search_method=default_search_method,
                         is_running=task_state['is_running'],
                         logs=task_state['logs'][-50:],
                         workflow_info=workflow_info)


@app.route('/api/workflow/start_iteration/execute', methods=['POST'])
def execute_start_iteration():
    """Execute the start iteration process"""
    task_state = running_tasks['start_iteration']
    
    if task_state['is_running']:
        return jsonify({'error': 'Task is already running'}), 400
    
    try:
        # Get form data
        data = request.get_json() if request.is_json else request.form
        
        iteration = int(data.get('iteration'))
        search_method_str = data.get('search_method', 'google_scholar')
        
        # Validate search method
        try:
            search_method = SearchMethod(search_method_str)
        except ValueError:
            return jsonify({'error': f'Invalid search method: {search_method_str}'}), 400
        
        # Validate iteration
        if iteration < 1:
            return jsonify({'error': 'Iteration must be >= 1'}), 400
        
        # Get database path from config
        search_conf = load_search_conf()
        if not search_conf or 'db_path' not in search_conf:
            return jsonify({'error': 'Database path not configured. Please set up configuration first.'}), 400
        
        db_path = search_conf['db_path']
        
        # Initialize task state
        task_state['is_running'] = True
        task_state['progress'] = 0
        task_state['total'] = 0
        task_state['current_step'] = 'Starting...'
        task_state['logs'] = []
        cancel_flag = threading.Event()
        task_state['cancel_flag'] = cancel_flag
        
        # Start worker thread
        def worker():
            try:
                # Helper functions for callbacks
                def log(msg):
                    task_state['logs'].append(msg)
                    if len(task_state['logs']) > 1000:  # Limit log size
                        task_state['logs'] = task_state['logs'][-1000:]
                
                def progress(current, total):
                    task_state['progress'] = current
                    task_state['total'] = total
                
                log("Initializing database...")
                db_manager = DBManager(db_path)
                
                log(f"Starting iteration {iteration}...")
                log(f"Search method: {search_method_str}")
                
                # Get seed publications from previous iteration
                log(f"Fetching seed publications from iteration {iteration - 1}...")
                initial_pubs = db_manager.get_iteration_data(
                    iteration=iteration - 1,
                    selected=SelectionStage.CONTENT_APPROVED,
                    search_method=search_method_str
                )
                
                if len(initial_pubs) == 0:
                    log("✗ No seed publications found!")
                    log("Possible reasons:")
                    log(f"  1. No publications found for search method: {search_method_str}")
                    log(f"  2. No publications found for iteration: {iteration - 1}")
                    log("  3. No publications are marked as CONTENT_APPROVED")
                    task_state['is_running'] = False
                    task_state['current_step'] = 'Failed: No seed publications'
                    return
                
                log(f"Found {len(initial_pubs)} seed publications")
                task_state['total'] = len(initial_pubs)
                
                # Create search instance
                search_method_instance = search_method.create_instance()
                article_search = ArticleSearch(search_method_instance)
                
                # Process articles with progress tracking
                processed = 0
                for i, initial_pub in enumerate(initial_pubs):
                    if cancel_flag.is_set():
                        log("Operation cancelled by user.")
                        return
                    
                    processed = i + 1
                    task_state['progress'] = processed
                    log(f"Processing [{processed}/{len(initial_pubs)}]: {initial_pub.title[:60] if initial_pub.title else 'Unknown'}...")
                    
                    citedby = initial_pub.id
                    try:
                        articles = article_search.get_snowballing_articles(
                            citedby, 
                            iteration=iteration, 
                            backwards=True, 
                            forwards=True
                        )
                    except Exception as e:
                        log(f"  ✗ Error fetching articles: {str(e)}")
                        continue
                    
                    if len(articles) == 0:
                        log(f"  No articles found")
                        continue
                    
                    log(f"  Found {len(articles)} articles")
                    
                    # Filter out already seen articles
                    filtered_articles = [
                        article for article in articles 
                        if db_manager.get_seen_title(article.title) is None
                    ]
                    
                    log(f"  {len(filtered_articles)} new articles")
                    
                    if filtered_articles:
                        db_manager.insert_iteration_data(filtered_articles)
                        db_manager.insert_seen_titles_data(
                            [(article.title, article.id) for article in filtered_articles]
                        )
                        log(f"  ✓ Saved to database")
                
                if not cancel_flag.is_set():
                    log(f"✓ Successfully completed iteration {iteration}")
                    # Update current iteration
                    update_current_iteration(iteration)
                    # Update workflow state
                    update_workflow_state(
                        db_path=db_path,
                        current_iteration=iteration,
                        last_step="Step 1: Start Iteration"
                    )
                    db_manager.conn.close()
                
            except Exception as e:
                task_state['logs'].append(f"Error: {str(e)}")
                import traceback
                task_state['logs'].append(traceback.format_exc())
            finally:
                task_state['is_running'] = False
                task_state['current_step'] = 'Completed' if not cancel_flag.is_set() else 'Cancelled'
                task_state['cancel_flag'] = None
        
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        
        return jsonify({'success': True, 'message': 'Iteration started'})
        
    except Exception as e:
        task_state['is_running'] = False
        return jsonify({'error': str(e)}), 500


@app.route('/api/workflow/start_iteration/status', methods=['GET'])
def get_start_iteration_status():
    """Get status of start iteration task"""
    task_state = running_tasks['start_iteration']
    return jsonify({
        'is_running': task_state['is_running'],
        'progress': task_state['progress'],
        'total': task_state['total'],
        'current_step': task_state['current_step'],
        'logs': task_state['logs'][-100:]
    })


@app.route('/api/workflow/start_iteration/cancel', methods=['POST'])
def cancel_start_iteration():
    """Cancel the running start iteration task"""
    task_state = running_tasks['start_iteration']
    
    if not task_state['is_running']:
        return jsonify({'error': 'No task is running'}), 400
    
    if task_state['cancel_flag']:
        task_state['cancel_flag'].set()
        task_state['logs'].append("Cancellation requested...")
        return jsonify({'success': True, 'message': 'Cancellation requested'})
    
    return jsonify({'error': 'No cancel flag available'}), 400


@app.route('/workflow/get_bibtex', methods=['GET'])
def get_bibtex_page():
    """Page for Step 2: Get BibTeX"""
    search_conf = load_search_conf()
    
    # Get defaults from config
    default_search_method = search_conf.get('search_method', 'google_scholar') if search_conf else 'google_scholar'
    
    # Get workflow info
    workflow_info = get_workflow_info()
    current_iteration = workflow_info.get('current_iteration') if workflow_info else None
    
    # Default to current iteration if available
    default_iteration = current_iteration if current_iteration is not None else 0
    
    task_state = running_tasks['get_bibtex']
    
    return render_template('get_bibtex.html',
                         default_iteration=default_iteration,
                         default_search_method=default_search_method,
                         is_running=task_state['is_running'],
                         logs=task_state['logs'][-50:],
                         workflow_info=workflow_info)


@app.route('/api/workflow/get_bibtex/execute', methods=['POST'])
def execute_get_bibtex():
    """Execute the get bibtex process"""
    task_state = running_tasks['get_bibtex']
    
    if task_state['is_running']:
        return jsonify({'error': 'Task is already running'}), 400
    
    try:
        # Get form data
        data = request.get_json() if request.is_json else request.form
        
        iteration = int(data.get('iteration'))
        search_method_str = data.get('search_method', 'google_scholar')
        delay = float(data.get('delay', 1.0))
        batch_size = int(data.get('batch_size', 10))
        max_workers = int(data.get('max_workers', 3))
        use_parallel = data.get('use_parallel', 'true') == 'true'
        
        # Validate search method (the script expects a string value, not an enum)
        valid_methods = [method.value for method in SearchMethod]
        if search_method_str not in valid_methods:
            return jsonify({'error': f'Invalid search method: {search_method_str}. Valid options: {valid_methods}'}), 400
        
        # Validate iteration
        if iteration < 0:
            return jsonify({'error': 'Iteration must be >= 0'}), 400
        
        # Get database path from config
        search_conf = load_search_conf()
        if not search_conf or 'db_path' not in search_conf:
            return jsonify({'error': 'Database path not configured. Please set up configuration first.'}), 400
        
        db_path = search_conf['db_path']
        
        # Initialize task state
        task_state['is_running'] = True
        task_state['progress'] = 0
        task_state['total'] = 0
        task_state['current_step'] = 'Starting...'
        task_state['logs'] = []
        cancel_flag = threading.Event()
        task_state['cancel_flag'] = cancel_flag
        
        # Start worker thread
        def worker():
            try:
                # Helper functions for callbacks
                def log(msg):
                    task_state['logs'].append(msg)
                    if len(task_state['logs']) > 1000:  # Limit log size
                        task_state['logs'] = task_state['logs'][-1000:]
                
                log("Initializing database...")
                db_manager = DBManager(db_path)
                
                log(f"Fetching articles from iteration {iteration} without bibtex...")
                articles = db_manager.get_iteration_data(
                    iteration=iteration,
                    bibtex__empty=True,
                    selected=SelectionStage.NOT_SELECTED
                )
                
                if len(articles) == 0:
                    log("No articles found that need BibTeX processing.")
                    log("All articles in this iteration already have BibTeX data.")
                    task_state['is_running'] = False
                    task_state['current_step'] = 'Completed: No articles to process'
                    return
                
                log(f"Found {len(articles)} articles without bibtex")
                task_state['total'] = len(articles)
                
                # Process articles with progress tracking
                processed_article_ids = set()  # Track unique article IDs to avoid double counting
                
                # Monkey-patch the process function to track progress
                original_update = db_manager.update_batch_iteration_data
                def tracked_update(iter_num, update_data):
                    # Only count unique articles (by article_id) to avoid triple counting
                    # since update_bibtex_info calls update_batch_iteration_data 3 times
                    for item in update_data:
                        if len(item) >= 1:
                            article_id = item[0]
                            processed_article_ids.add(article_id)
                    task_state['progress'] = len(processed_article_ids)
                    task_state['current_step'] = f'Processed {len(processed_article_ids)}/{len(articles)} articles'
                    return original_update(iter_num, update_data)
                
                db_manager.update_batch_iteration_data = tracked_update
                
                log(f"Starting BibTeX retrieval for {len(articles)} articles...")
                log(f"Search method: {search_method_str}")
                log(f"Delay: {delay} seconds")
                log(f"Batch size: {batch_size}")
                log(f"Parallel processing: {use_parallel}")
                if use_parallel:
                    log(f"Max workers: {max_workers}")
                
                # Execute the processing (pass string value, not enum, and cancel_flag)
                process_articles_optimized(
                    iteration=iteration,
                    articles=articles,
                    db_manager=db_manager,
                    batch_size=batch_size,
                    max_workers=max_workers,
                    use_parallel=use_parallel,
                    search_method=search_method_str,
                    delay=delay,
                    cancel_flag=cancel_flag
                )
                
                if not cancel_flag.is_set():
                    log(f"✓ Successfully processed {len(articles)} articles and saved BibTeX to database.")
                    # Update workflow state
                    # db_path is already available from outer scope
                    current_iter = get_current_iteration_from_db(db_manager, articles)
                    update_workflow_state(
                        db_path=db_path,
                        current_iteration=current_iter,
                        last_step="Step 2: Get BibTeX"
                    )
                
            except Exception as e:
                task_state['logs'].append(f"Error: {str(e)}")
                import traceback
                task_state['logs'].append(traceback.format_exc())
            finally:
                task_state['is_running'] = False
                task_state['current_step'] = 'Completed' if not cancel_flag.is_set() else 'Cancelled'
                task_state['cancel_flag'] = None
        
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        
        return jsonify({'success': True, 'message': 'BibTeX retrieval started'})
        
    except Exception as e:
        task_state['is_running'] = False
        return jsonify({'error': str(e)}), 500


@app.route('/api/workflow/get_bibtex/status', methods=['GET'])
def get_get_bibtex_status():
    """Get status of get bibtex task"""
    task_state = running_tasks['get_bibtex']
    return jsonify({
        'is_running': task_state['is_running'],
        'progress': task_state['progress'],
        'total': task_state['total'],
        'current_step': task_state['current_step'],
        'logs': task_state['logs'][-100:]
    })


@app.route('/api/workflow/get_bibtex/cancel', methods=['POST'])
def cancel_get_bibtex():
    """Cancel the running get bibtex task"""
    task_state = running_tasks['get_bibtex']
    
    if not task_state['is_running']:
        return jsonify({'error': 'No task is running'}), 400
    
    if task_state['cancel_flag']:
        task_state['cancel_flag'].set()
        task_state['logs'].append("Cancellation requested...")
        return jsonify({'success': True, 'message': 'Cancellation requested'})
    
    return jsonify({'error': 'No cancel flag available'}), 400


@app.route('/workflow/generate_conf_rank', methods=['GET'])
def generate_conf_rank_page():
    """Page for Step 3: Generate Conf Rank"""
    search_conf = load_search_conf()
    
    # Get workflow info
    workflow_info = get_workflow_info()
    current_iteration = workflow_info.get('current_iteration') if workflow_info else None
    
    # Default to current iteration if available
    default_iteration = current_iteration if current_iteration is not None else 0
    
    # Get valid venue ranks from config
    venue_ranks = search_conf.get('venue_rank_list', ['A*', 'A', 'B', 'C', 'D', 'Q1', 'Q2', 'Q3', 'Q4', 'NA']) if search_conf else ['A*', 'A', 'B', 'C', 'D', 'Q1', 'Q2', 'Q3', 'Q4', 'NA']
    
    # Check if BibTeX step was skipped
    workflow_state = load_workflow_state()
    skipped_steps = workflow_state.get('skipped_steps', [])
    bibtex_skipped = 'Step 2: Get BibTeX' in skipped_steps
    conf_rank_not_possible = bibtex_skipped
    
    return render_template('generate_conf_rank.html',
                         default_iteration=default_iteration,
                         venue_ranks=venue_ranks,
                         workflow_info=workflow_info,
                         bibtex_skipped=bibtex_skipped,
                         conf_rank_not_possible=conf_rank_not_possible)


@app.route('/api/workflow/generate_conf_rank/unindexed_venues', methods=['GET'])
def get_unindexed_venues():
    """Get list of unindexed venues for an iteration"""
    try:
        print("Getting unindexed venues...")
        iteration = int(request.args.get('iteration'))
        
        # Get database path from config
        search_conf = load_search_conf()
        if not search_conf or 'db_path' not in search_conf:
            return jsonify({'error': 'Database path not configured'}), 400
        
        db_path = search_conf['db_path']
        db_manager = DBManager(db_path)
        
        # Get articles with BibTeX
        print("[DEBUG] iteration: ", iteration)
        articles = db_manager.get_iteration_data(
            iteration=iteration,
            bibtex__not_empty=True,
            bibtex__ne="NO_BIBTEX",
            selected=SelectionStage.NOT_SELECTED
        )
        
        # Get venues from articles
        venues = get_venues(articles)
        print("Venues: ", venues)
        
        # Get existing conf_rank data
        conf_rank_data = db_manager.get_conf_rank_data()
        conf_rank = {venue: rank for venue, rank in conf_rank_data}
        
        # Filter unindexed venues (excluding arxiv/ssrn/corr)
        unindexed_venues = []
        for venue in venues:
            venue = venue.strip().replace("\n", " ")
            venue_lower = venue.lower()
            
            # Skip if already in conf_rank (case-insensitive)
            if venue_lower not in [k.lower() for k in conf_rank.keys()]:
                # Auto-assign NA for arxiv/ssrn/corr
                if "arxiv" in venue_lower or "ssrn" in venue_lower or 'corr' in venue_lower:
                    # Auto-save these
                    db_manager.insert_conf_rank_data([(venue, "NA")])
                    continue
                unindexed_venues.append(venue)
        
        return jsonify({
            'success': True,
            'unindexed_venues': unindexed_venues,
            'total': len(unindexed_venues)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/workflow/generate_conf_rank/similar_venues', methods=['GET'])
def get_similar_venues():
    """Get similar venues for a given venue"""
    try:
        venue = request.args.get('venue')
        if not venue:
            return jsonify({'error': 'Venue parameter required'}), 400
        
        # Get database path from config
        search_conf = load_search_conf()
        if not search_conf or 'db_path' not in search_conf:
            return jsonify({'error': 'Database path not configured'}), 400
        
        db_path = search_conf['db_path']
        db_manager = DBManager(db_path)
        
        # Get existing conf_rank data
        conf_rank_data = db_manager.get_conf_rank_data()
        conf_rank_dict = {venue_name: rank for venue_name, rank in conf_rank_data}
        
        # Find similar venues (adapting the function to accept conf_rank)
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        
        existing_venues = set(conf_rank_dict.keys())
        if not existing_venues:
            return jsonify({'success': True, 'similar_venues': []})
        
        vectorizer = TfidfVectorizer()
        all_venues = [venue] + list(existing_venues)
        tfidf_matrix = vectorizer.fit_transform(all_venues)
        cosine_similarities = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:]).flatten()
        
        similar_venues = []
        for i, sim in enumerate(cosine_similarities):
            if sim > 0.5:  # threshold
                venue_name = list(existing_venues)[i]
                similar_venues.append({
                    'venue': venue_name,
                    'similarity': round(sim, 2),
                    'rank': conf_rank_dict[venue_name]
                })
        
        similar_venues.sort(key=lambda x: x['similarity'], reverse=True)
        similar_venues = similar_venues[:5]  # top_k
        
        return jsonify({
            'success': True,
            'similar_venues': similar_venues
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/workflow/generate_conf_rank/search_scimago', methods=['GET'])
def search_scimago_venue():
    """Search Scimago database for a venue"""
    try:
        venue = request.args.get('venue')
        if not venue:
            return jsonify({'error': 'Venue parameter required'}), 400
        
        print(f"\n{'='*80}")
        print(f"SCIMAGO SEARCH for venue: {venue}")
        print(f"{'='*80}")
        
        # Use the imported function
        result = _get_scimago_rank(venue, as_string=True)
        
        if result == "":
            print("RESULT: Not Found in database")
            print(f"{'='*80}\n")
            return jsonify({
                'success': True,
                'found': False,
                'data': 'Not Found in database'
            })
        
        print(f"RESULT:\n{result}")
        print(f"{'='*80}\n")
        
        return jsonify({
            'success': True,
            'found': True,
            'data': result
        })
        
    except Exception as e:
        print(f"ERROR in Scimago search: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/workflow/generate_conf_rank/search_core', methods=['GET'])
def search_core_venue():
    """Search Core Table database for a venue"""
    try:
        venue = request.args.get('venue')
        if not venue:
            return jsonify({'error': 'Venue parameter required'}), 400
        
        print(f"\n{'='*80}")
        print(f"CORE TABLE SEARCH for venue: {venue}")
        print(f"{'='*80}")
        
        # Use the imported function
        result = _get_core_rank(venue, as_string=True)
        
        if result == "":
            print("RESULT: Not Found in database")
            print(f"{'='*80}\n")
            return jsonify({
                'success': True,
                'found': False,
                'data': 'Not Found in database'
            })
        
        print(f"RESULT:\n{result}")
        print(f"{'='*80}\n")
        
        return jsonify({
            'success': True,
            'found': True,
            'data': result
        })
        
    except Exception as e:
        print(f"ERROR in Core Table search: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/workflow/generate_conf_rank/save_rank', methods=['POST'])
def save_venue_rank():
    """Save a venue rank to the database"""
    try:
        data = request.get_json()
        venue = data.get('venue')
        rank = data.get('rank')
        
        if not venue or not rank:
            return jsonify({'error': 'Venue and rank are required'}), 400
        
        # Get database path from config
        search_conf = load_search_conf()
        if not search_conf or 'db_path' not in search_conf:
            return jsonify({'error': 'Database path not configured'}), 400
        
        db_path = search_conf['db_path']
        db_manager = DBManager(db_path)
        
        # Save the rank
        db_manager.insert_conf_rank_data([(venue, rank)])
        
        # Get current iteration from workflow state or config
        workflow_info = get_workflow_info()
        current_iter = workflow_info.get('current_iteration') if workflow_info else None
        if current_iter is None:
            current_iter = search_conf.get('current_iteration')
        
        # Update workflow state when saving ranks
        # Note: This updates on every venue save, but that's okay for tracking progress
        update_workflow_state(
            db_path=db_path,
            current_iteration=current_iter,
            last_step="Step 3: Assign Venue Ranks"
        )
        
        return jsonify({
            'success': True,
            'message': f'Rank "{rank}" saved for venue "{venue}"'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/workflow/filter_by_metadata', methods=['GET'])
def filter_by_metadata_page():
    """Page for Step 4: Filter by Metadata"""
    search_conf = load_search_conf()
    
    # Get workflow info
    workflow_info = get_workflow_info()
    current_iteration = workflow_info.get('current_iteration') if workflow_info else None
    
    # Default to current iteration if available
    default_iteration = current_iteration if current_iteration is not None else 0
    
    # Get config values for display
    start_year = search_conf.get('start_year', 2019) if search_conf else 2019
    end_year = search_conf.get('end_year', 2025) if search_conf else 2025
    venue_rank_list = search_conf.get('venue_rank_list', []) if search_conf else []
    
    # Check if BibTeX or Generate Conf Rank steps were skipped
    workflow_state = load_workflow_state()
    skipped_steps = workflow_state.get('skipped_steps', [])
    bibtex_skipped = 'Step 2: Get BibTeX' in skipped_steps
    conf_rank_skipped = 'Step 3: Assign Venue Ranks' in skipped_steps
    venue_filter_disabled = bibtex_skipped or conf_rank_skipped
    
    return render_template('filter_by_metadata.html',
                         default_iteration=default_iteration,
                         start_year=start_year,
                         end_year=end_year,
                         venue_rank_list=venue_rank_list,
                         workflow_info=workflow_info,
                         venue_filter_disabled=venue_filter_disabled,
                         bibtex_skipped=bibtex_skipped,
                         conf_rank_skipped=conf_rank_skipped)


@app.route('/api/workflow/filter_by_metadata/articles', methods=['GET'])
def get_articles_for_metadata_filter():
    """Get list of articles that need metadata filtering for an iteration"""
    try:
        iteration = int(request.args.get('iteration'))
        
        # Get database path from config
        search_conf = load_search_conf()
        if not search_conf or 'db_path' not in search_conf:
            return jsonify({'error': 'Database path not configured'}), 400
        
        db_path = search_conf['db_path']
        db_manager = DBManager(db_path)

        print("Iteration: ", iteration)
        
        # Check if BibTeX or Generate Conf Rank steps were skipped
        workflow_state = load_workflow_state()
        skipped_steps = workflow_state.get('skipped_steps', [])
        bibtex_skipped = 'Step 2: Get BibTeX' in skipped_steps
        conf_rank_skipped = 'Step 3: Assign Venue Ranks' in skipped_steps
        venue_filter_disabled = bibtex_skipped or conf_rank_skipped
        
        # If venue filtering is disabled (BibTeX or Conf Rank skipped), 
        # get articles without requiring BibTeX
        if venue_filter_disabled:
            # Get all articles that haven't been selected yet (don't require BibTeX)
            articles = db_manager.get_iteration_data(
                iteration=iteration,
                selected=SelectionStage.NOT_SELECTED
            )
        else:
            # Get articles with BibTeX that haven't been selected yet
            articles = db_manager.get_iteration_data(
                iteration=iteration,
                bibtex__not_empty=True,
                bibtex__ne="NO_BIBTEX",
                selected=SelectionStage.NOT_SELECTED
            )

        print("Articles: ", len(articles))
        
        # Convert to JSON-serializable format
        articles_data = []
        for article in articles:
            articles_data.append({
                'id': article.id,
                'title': article.title or '',
                'venue': article.venue or '',
                'pub_year': article.pub_year or '',
                'eprint_url': article.eprint_url or '',
                'bibtex': article.bibtex or ''
            })
        
        return jsonify({
            'success': True,
            'articles': articles_data,
            'total': len(articles_data),
            'venue_filter_disabled': venue_filter_disabled
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/workflow/filter_by_metadata/check_venue', methods=['POST'])
def check_venue_peer_reviewed():
    """Check if venue is peer-reviewed and in allowed ranks"""
    try:
        data = request.get_json()
        article_id = data.get('article_id')
        bibtex = data.get('bibtex')
        
        if not article_id or not bibtex:
            return jsonify({'error': 'Article ID and BibTeX are required'}), 400
        
        # Get database path from config
        search_conf = load_search_conf()
        if not search_conf or 'db_path' not in search_conf:
            return jsonify({'error': 'Database path not configured'}), 400
        
        db_path = search_conf['db_path']
        db_manager = DBManager(db_path)
        
        # Run automated check
        result = automated_check_venue_and_peer_reviewed(bibtex, db_manager)
        
        return jsonify({
            'success': True,
            'automated_result': result,  # True, False, or None (needs user input)
            'needs_user_input': result is None
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/workflow/filter_by_metadata/check_year', methods=['POST'])
def check_year_valid():
    """Check if year is valid (web-friendly version without input prompts)"""
    try:
        data = request.get_json()
        pub_year = data.get('pub_year', '')
        
        search_conf = load_search_conf()
        if not search_conf:
            return jsonify({'error': 'Configuration not found'}), 400
        
        # Try to parse year
        try:
            year_int = int(pub_year) if pub_year and pub_year.isdigit() else 0
        except (ValueError, AttributeError):
            year_int = 0
        
        start_year = int(search_conf.get('start_year', 2019))
        end_year = int(search_conf.get('end_year', 2025))
        
        if year_int != 0:
            is_valid = start_year <= year_int <= end_year
            needs_user_input = False
        else:
            # Year is 0 or invalid - needs user confirmation
            is_valid = None
            needs_user_input = True
        
        return jsonify({
            'success': True,
            'is_valid': is_valid,
            'needs_user_input': needs_user_input,
            'year': year_int if year_int != 0 else None
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/workflow/filter_by_metadata/check_english', methods=['POST'])
def check_english_language():
    """Check if title is in English (web-friendly version)"""
    try:
        data = request.get_json()
        title = data.get('title', '')
        
        if not title:
            return jsonify({
                'success': True,
                'is_english': None,
                'needs_user_input': True
            })
        
        # Try language detection
        try:
            from langdetect import detect
            detected_lang = detect(title)
            is_english = (detected_lang == "en")
            # Always ask user to verify if not detected as English (even if detected as another language)
            # This allows user to override incorrect detections
            if is_english:
                needs_user_input = False  # Confidently English - no verification needed
            else:
                needs_user_input = True  # Not English or uncertain - user should verify
                is_english = None  # Set to None to indicate needs user verification
        except Exception:
            # If detection fails, ask user
            is_english = None
            detected_lang = None
            needs_user_input = True
        
        return jsonify({
            'success': True,
            'is_english': is_english,  # True if English, None if needs verification
            'needs_user_input': needs_user_input,
            'detected_language': detected_lang if 'detected_lang' in locals() else None
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/workflow/filter_by_metadata/check_download', methods=['POST'])
def check_downloadable():
    """Check if article is downloadable"""
    try:
        data = request.get_json()
        eprint_url = data.get('eprint_url', '')
        
        # If URL exists and is not empty, it's downloadable
        is_downloadable = bool(eprint_url and eprint_url.strip())
        
        return jsonify({
            'success': True,
            'is_downloadable': is_downloadable,
            'needs_user_input': not is_downloadable  # If no URL, ask user
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/workflow/filter_by_metadata/evaluate_article', methods=['POST'])
def evaluate_metadata_article():
    """Evaluate all checks for an article and determine if it needs user input or can be auto-processed"""
    try:
        data = request.get_json()
        article = data.get('article')
        iteration = int(data.get('iteration'))
        filter_options = data.get('filter_options', {})
        
        if not article:
            return jsonify({'error': 'Article data is required'}), 400
        
        # Skip articles without IDs - they cannot be processed
        article_id = article.get('id') or article.get('article_id')
        if not article_id:
            return jsonify({
                'success': True,
                'skip': True,
                'message': 'Article skipped: no ID available'
            })
        
        # Get database path from config
        search_conf = load_search_conf()
        if not search_conf or 'db_path' not in search_conf:
            return jsonify({'error': 'Database path not configured'}), 400
        
        db_path = search_conf['db_path']
        db_manager = DBManager(db_path)
        
        venue_filter_disabled = filter_options.get('venue_filter_disabled', False)
        enable_venue = filter_options.get('enableVenueCheck', True) and not venue_filter_disabled
        enable_year = filter_options.get('enableYearCheck', True)
        enable_language = filter_options.get('enableLanguageCheck', True)
        enable_download = filter_options.get('enableDownloadCheck', True)
        
        check_results = {}
        needs_user_input = False
        filter_result = None
    
        if enable_venue:
            bibtex = article.get('bibtex', '')
            if bibtex:
                result = automated_check_venue_and_peer_reviewed(bibtex, db_manager)
                check_results['venue'] = result
                if result is False:
                    # Venue check failed - immediately filter and skip other checks
                    filter_result = 'venue_filtered'
                elif result is None:
                    # Venue check needs user input, but continue checking other filters
                    needs_user_input = True
            else:
                check_results['venue'] = None
                needs_user_input = True
        
        # Check year (only if venue didn't fail)
        if enable_year and filter_result is None:
            pub_year = article.get('pub_year', '')
            try:
                year_int = int(pub_year) if pub_year and pub_year.isdigit() else 0
            except (ValueError, AttributeError):
                year_int = 0
            
            start_year = int(search_conf.get('start_year', 2019))
            end_year = int(search_conf.get('end_year', 2025))
            
            if year_int != 0:
                year_check = start_year <= year_int <= end_year
                check_results['year'] = year_check
                if year_check is False:
                    # Year check failed - immediately filter and skip remaining checks
                    filter_result = 'year_filtered'
            else:
                check_results['year'] = None
                # Year needs user input, but continue checking other filters
                needs_user_input = True
        
        # Check language (only if previous checks didn't fail)
        if enable_language and filter_result is None:
            title = article.get('title', '')
            if title:
                try:
                    from langdetect import detect
                    detected_lang = detect(title)
                    is_english = (detected_lang == "en")
                    if is_english:
                        # Confidently detected as English - no user input needed
                        check_results['language'] = True
                    else:
                        # Detected as non-English OR detection uncertain - needs user verification
                        check_results['language'] = None
                        needs_user_input = True
                except Exception:
                    # Detection failed - needs user input
                    check_results['language'] = None
                    needs_user_input = True
            else:
                # No title - needs user input
                check_results['language'] = None
                needs_user_input = True
        
        # Check download (only if previous checks didn't fail)
        if enable_download and filter_result is None:
            eprint_url = article.get('eprint_url', '')
            download_check = bool(eprint_url and eprint_url.strip())
            check_results['download'] = download_check
            if download_check is False:
                # Download check failed - immediately filter
                filter_result = 'download_filtered'
        
        # If no filter failed yet, determine final result
        if filter_result is None:
            if not needs_user_input:
                # All checks have definitive results and none failed
                filter_result = 'approved'
            # else: needs_user_input is True, filter_result remains None
        
        return jsonify({
            'success': True,
            'check_results': check_results,
            'needs_user_input': needs_user_input and filter_result is None,  # Only needs input if no filter failed
            'filter_result': filter_result  # Set if any filter failed or all passed
        })
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/workflow/filter_by_metadata/save_result', methods=['POST'])
def save_metadata_filter_result():
    """Save the metadata filter result for an article"""
    try:
        data = request.get_json()
        article_id = data.get('article_id')
        filter_result = data.get('filter_result')  # 'approved', 'venue_filtered', 'year_filtered', 'language_filtered', 'download_filtered'
        iteration = int(data.get('iteration'))
        
        # Skip articles without IDs - return success but don't process
        if not article_id:
            return jsonify({
                'success': True,
                'skipped': True,
                'message': 'Article skipped: no ID available'
            })
        
        if not filter_result:
            return jsonify({'error': 'Filter result is required'}), 400
        
        # Get database path from config
        search_conf = load_search_conf()
        if not search_conf or 'db_path' not in search_conf:
            return jsonify({'error': 'Database path not configured'}), 400
        
        db_path = search_conf['db_path']
        db_manager = DBManager(db_path)
        
        # Prepare update data based on filter result
        update_data = []
        if filter_result == 'approved':
            update_data.append((article_id, SelectionStage.METADATA_APPROVED.value, "selected"))
        elif filter_result == 'venue_filtered':
            update_data.append((article_id, True, "venue_filtered_out"))
        elif filter_result == 'year_filtered':
            update_data.append((article_id, True, "year_filtered_out"))
        elif filter_result == 'language_filtered':
            update_data.append((article_id, True, "language_filtered_out"))
        elif filter_result == 'download_filtered':
            update_data.append((article_id, True, "download_filtered_out"))
        else:
            return jsonify({'error': 'Invalid filter result'}), 400
        
        # Save to database
        db_manager.update_batch_iteration_data(iteration, update_data)
        
        # Update workflow state
        update_workflow_state(
            db_path=db_path,
            current_iteration=iteration,
            last_step="Step 4: Filter by Metadata"
        )
        
        return jsonify({
            'success': True,
            'message': f'Filter result saved for article {article_id}'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/workflow/filter_by_title', methods=['GET'])
def filter_by_title_page():
    """Page for Step 5: Filter by Title"""
    search_conf = load_search_conf()
    
    # Get workflow info
    workflow_info = get_workflow_info()
    current_iteration = workflow_info.get('current_iteration') if workflow_info else None
    
    # Default to current iteration if available
    default_iteration = current_iteration if current_iteration is not None else 0
    
    return render_template('filter_by_title.html',
                         default_iteration=default_iteration,
                         workflow_info=workflow_info)


@app.route('/api/workflow/filter_by_title/articles', methods=['GET'])
def get_articles_for_title_filter():
    """Get list of articles that need title filtering for an iteration"""
    try:
        iteration = int(request.args.get('iteration'))
        
        # Get database path from config
        search_conf = load_search_conf()
        if not search_conf or 'db_path' not in search_conf:
            return jsonify({'error': 'Database path not configured'}), 400
        
        db_path = search_conf['db_path']
        db_manager = DBManager(db_path)
        
        # Get articles with METADATA_APPROVED status that haven't been title-filtered yet
        articles = db_manager.get_iteration_data(
            iteration=iteration,
            selected=SelectionStage.METADATA_APPROVED
        )
        
        # Filter out articles that are already title-approved or title-filtered-out
        filtered_articles = []
        for article in articles:
            selected_int = int(article.selected) if article.selected is not None else 0
            if selected_int < SelectionStage.TITLE_APPROVED.value and not article.title_filtered_out:
                filtered_articles.append(article)
        
        # Convert to JSON-serializable format
        articles_data = []
        for article in filtered_articles:
            articles_data.append({
                'id': article.id,
                'title': article.title or '',
                'venue': article.venue or '',
                'pub_year': article.pub_year or '',
                'eprint_url': article.eprint_url or '',
                'authors': article.authors or '',
                'title_reason': getattr(article, 'title_reason', '') or ''
            })
        
        return jsonify({
            'success': True,
            'articles': articles_data,
            'total': len(articles_data)
        })
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/workflow/filter_by_title/save_result', methods=['POST'])
def save_title_filter_result():
    """Save the title filter result for an article"""
    try:
        data = request.get_json()
        article_id = data.get('article_id')
        decision = data.get('decision')  # 'approve' or 'reject'
        reason = data.get('reason', '')  # Optional reason
        iteration = int(data.get('iteration'))
        
        if not article_id or not decision:
            return jsonify({'error': 'Article ID and decision are required'}), 400
        
        if decision not in ['approve', 'reject']:
            return jsonify({'error': 'Decision must be "approve" or "reject"'}), 400
        
        # Get database path from config
        search_conf = load_search_conf()
        if not search_conf or 'db_path' not in search_conf:
            return jsonify({'error': 'Database path not configured'}), 400
        
        db_path = search_conf['db_path']
        db_manager = DBManager(db_path)
        
        # Prepare update data based on decision
        update_data = []
        if decision == 'approve':
            update_data.append((article_id, SelectionStage.TITLE_APPROVED.value, "selected"))
            if reason:
                update_data.append((article_id, reason, "title_reason"))
        elif decision == 'reject':
            update_data.append((article_id, True, "title_filtered_out"))
            if reason:
                update_data.append((article_id, reason, "title_reason"))
        
        # Save to database
        db_manager.update_batch_iteration_data(iteration, update_data)
        
        # Update workflow state
        update_workflow_state(
            db_path=db_path,
            current_iteration=iteration,
            last_step="Step 5: Filter by Title"
        )
        
        return jsonify({
            'success': True,
            'message': f'Title filter result saved for article {article_id}'
        })
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/workflow/filter_by_content', methods=['GET'])
def filter_by_content_page():
    """Page for Step 7: Filter by Content"""
    search_conf = load_search_conf()
    
    # Get workflow info
    workflow_info = get_workflow_info()
    current_iteration = workflow_info.get('current_iteration') if workflow_info else None
    
    # Default to current iteration if available
    default_iteration = current_iteration if current_iteration is not None else 0
    
    # Get annotations from config
    annotations = search_conf.get('annotations', []) if search_conf else []
    
    return render_template('filter_by_content.html',
                         default_iteration=default_iteration,
                         workflow_info=workflow_info,
                         annotations=annotations)


@app.route('/api/workflow/filter_by_content/articles', methods=['GET'])
def get_articles_for_content_filter():
    """Get articles that need content filtering (title-approved articles)"""
    try:
        iteration = int(request.args.get('iteration', 0))
        
        # Get database path from config
        search_conf = load_search_conf()
        if not search_conf or 'db_path' not in search_conf:
            return jsonify({'error': 'Database path not configured'}), 400
        
        db_path = search_conf['db_path']
        db_manager = DBManager(db_path)
        
        # Get articles with TITLE_APPROVED status that haven't been content-filtered yet
        articles = db_manager.get_iteration_data(
            iteration=iteration,
            selected=SelectionStage.TITLE_APPROVED
        )
        
        # Filter out articles that are already content-approved or content-filtered-out
        filtered_articles = []
        for article in articles:
            selected_int = int(article.selected) if article.selected is not None else 0
            abstract_filtered = getattr(article, 'abstract_filtered_out', False)
            if selected_int < SelectionStage.CONTENT_APPROVED.value and not abstract_filtered:
                filtered_articles.append(article)
        
        # Convert to JSON-serializable format
        articles_data = []
        for article in filtered_articles:
            # Parse content_reason if it exists (might be JSON with annotations)
            content_reason = getattr(article, 'content_reason', '') or ''
            reason_text = ''
            annotations_data = {}
            
            if content_reason:
                try:
                    # Try to parse as JSON (if it contains annotations)
                    reason_json = json.loads(content_reason)
                    reason_text = reason_json.get('reason', '')
                    # Extract annotation fields (everything except 'reason')
                    for key, value in reason_json.items():
                        if key != 'reason':
                            annotations_data[key] = value
                except (json.JSONDecodeError, TypeError):
                    # If not JSON, treat as plain text reason
                    reason_text = content_reason
            
            # Get all URL fields
            eprint_url = getattr(article, 'eprint_url', '') or ''
            pub_url = getattr(article, 'pub_url', '') or ''
            
            articles_data.append({
                'id': article.id,
                'title': getattr(article, 'title', '') or '',
                'venue': getattr(article, 'venue', '') or '',
                'pub_year': getattr(article, 'pub_year', '') or '',
                'eprint_url': eprint_url,
                'pub_url': pub_url,
                'authors': getattr(article, 'authors', '') or '',
                'content_reason': reason_text,
                'annotations': annotations_data
            })
        
        return jsonify({
            'success': True,
            'articles': articles_data,
            'total': len(articles_data)
        })
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/workflow/filter_by_content/save_result', methods=['POST'])
def save_content_filter_result():
    """Save the content filter result for an article"""
    try:
        data = request.get_json()
        article_id = data.get('article_id')
        decision = data.get('decision')  # 'approve' or 'reject'
        reason = data.get('reason', '')  # Optional reason
        annotations = data.get('annotations', {})  # Optional annotations dict
        iteration = int(data.get('iteration'))
        
        if not article_id or not decision:
            return jsonify({'error': 'Article ID and decision are required'}), 400
        
        if decision not in ['approve', 'reject']:
            return jsonify({'error': 'Decision must be "approve" or "reject"'}), 400
        
        # Get database path from config
        search_conf = load_search_conf()
        if not search_conf or 'db_path' not in search_conf:
            return jsonify({'error': 'Database path not configured'}), 400
        
        db_path = search_conf['db_path']
        db_manager = DBManager(db_path)
        
        # Prepare update data based on decision
        update_data = []
        if decision == 'approve':
            update_data.append((article_id, SelectionStage.CONTENT_APPROVED.value, "selected"))
            
            # Combine reason and annotations into JSON for content_reason
            user_data = {'reason': reason}
            if annotations:
                user_data.update(annotations)
            update_data.append((article_id, json.dumps(user_data), "content_reason"))
        elif decision == 'reject':
            update_data.append((article_id, True, "abstract_filtered_out"))
            
            # Save reason (no annotations for rejected articles)
            user_data = {'reason': reason}
            update_data.append((article_id, json.dumps(user_data), "content_reason"))
        
        # Save to database
        db_manager.update_batch_iteration_data(iteration, update_data)
        
        # Update workflow state
        update_workflow_state(
            db_path=db_path,
            current_iteration=iteration,
            last_step="Step 7: Filter by Content"
        )
        
        return jsonify({
            'success': True,
            'message': f'Content filter result saved for article {article_id}'
        })
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/workflow/skip_step', methods=['POST'])
def skip_workflow_step():
    """Skip a workflow step"""
    try:
        data = request.get_json()
        step_name = data.get('step_name')
        iteration = data.get('iteration')
        
        if not step_name:
            return jsonify({'error': 'Step name is required'}), 400
        
        # Get current workflow state
        workflow_state = load_workflow_state()
        current_iteration = iteration if iteration is not None else workflow_state.get('current_iteration')
        
        if current_iteration is None:
            return jsonify({'error': 'Iteration is required'}), 400
        
        # Get database path from config
        search_conf = load_search_conf()
        db_path = search_conf.get('db_path', 'database.db') if search_conf else 'database.db'
        
        # For filter steps, automatically approve all articles in the appropriate stage
        db_manager = DBManager(db_path)
        update_data = []
        articles_updated = 0
        
        if step_name == 'Step 4: Filter by Metadata':
            # Skip metadata filter: approve ALL articles in this iteration (set to METADATA_APPROVED)
            # When skipping Step 4, we bypass all metadata filtering, so all articles are approved
            articles = db_manager.get_iteration_data(iteration=current_iteration)
            for article in articles:
                # Check current selected status - only update if not already METADATA_APPROVED or higher
                current_selected = getattr(article, 'selected', SelectionStage.NOT_SELECTED.value)
                if current_selected is not None:
                    try:
                        current_selected = int(current_selected) if isinstance(current_selected, (str, int)) else SelectionStage.NOT_SELECTED.value
                    except (ValueError, TypeError):
                        current_selected = SelectionStage.NOT_SELECTED.value
                else:
                    current_selected = SelectionStage.NOT_SELECTED.value
                
                # Update to METADATA_APPROVED if not already at that stage or higher
                if current_selected < SelectionStage.METADATA_APPROVED.value:
                    update_data.append((article.id, SelectionStage.METADATA_APPROVED.value, "selected"))
                    articles_updated += 1
        
        elif step_name == 'Step 5: Filter by Title':
            # Skip title filter: approve all METADATA_APPROVED articles (set to TITLE_APPROVED)
            # When skipping Step 5, we bypass title filtering, so all METADATA_APPROVED articles are approved
            articles = db_manager.get_iteration_data(
                iteration=current_iteration,
                selected=SelectionStage.METADATA_APPROVED.value
            )
            for article in articles:
                # Update to TITLE_APPROVED (even if previously filtered out, since we're skipping the step)
                update_data.append((article.id, SelectionStage.TITLE_APPROVED.value, "selected"))
                # Clear the title_filtered_out flag if it was set
                if getattr(article, 'title_filtered_out', False):
                    update_data.append((article.id, False, "title_filtered_out"))
                articles_updated += 1
        
        elif step_name == 'Step 7: Filter by Content':
            # Skip content filter: approve all TITLE_APPROVED articles (set to CONTENT_APPROVED)
            # When skipping Step 7, we bypass content filtering, so all TITLE_APPROVED articles are approved
            articles = db_manager.get_iteration_data(
                iteration=current_iteration,
                selected=SelectionStage.TITLE_APPROVED.value
            )
            for article in articles:
                # Update to CONTENT_APPROVED (even if previously filtered out, since we're skipping the step)
                update_data.append((article.id, SelectionStage.CONTENT_APPROVED.value, "selected"))
                # Clear the abstract_filtered_out flag if it was set
                if getattr(article, 'abstract_filtered_out', False):
                    update_data.append((article.id, False, "abstract_filtered_out"))
                articles_updated += 1
        
        # Apply bulk updates if any
        if update_data:
            db_manager.update_batch_iteration_data(current_iteration, update_data)
        
        db_manager.conn.close()

        update_workflow_state(
            db_path=db_path,
            current_iteration=current_iteration,
            last_step=step_name,
            skip_step=step_name
        )
        
        # Optionally get next step for reference (not used as last_step anymore)
        next_step = get_next_step_after_skip(step_name)
        
        message = f'Step "{step_name}" has been skipped'
        if articles_updated > 0:
            message += f'. {articles_updated} article(s) automatically approved.'
        
        return jsonify({
            'success': True,
            'message': message,
            'articles_updated': articles_updated,
            'next_step': next_step,  # Optional reference for frontend
            'skipped_steps': load_workflow_state().get('skipped_steps', [])
        })
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/workflow/solve_title_disagreements', methods=['GET'])
def solve_title_disagreements_page():
    """Page for Step 6: Solve Title Disagreements"""
    search_conf = load_search_conf()
    
    # Get workflow info
    workflow_info = get_workflow_info()
    current_iteration = workflow_info.get('current_iteration') if workflow_info else None
    
    # Default to current iteration if available
    default_iteration = current_iteration if current_iteration is not None else 0
    
    # Get main database path from config
    main_db_path = search_conf.get('db_path', 'database.db') if search_conf else 'database.db'
    
    return render_template('solve_title_disagreements.html',
                         default_iteration=default_iteration,
                         main_db_path=main_db_path,
                         workflow_info=workflow_info)


@app.route('/api/workflow/solve_title_disagreements/find_disagreements', methods=['POST'])
def find_title_disagreements():
    """Find disagreements between multiple databases"""
    try:
        data = request.get_json()
        iteration = int(data.get('iteration'))
        db_paths = data.get('db_paths', [])  # List of database paths
        
        if not db_paths or len(db_paths) < 2:
            return jsonify({'error': 'At least 2 database paths are required'}), 400
        
        # Validate all databases exist
        for db_path in db_paths:
            if not os.path.exists(db_path):
                return jsonify({'error': f'Database not found: {db_path}'}), 400
        
        # Create DB managers for all databases
        db_managers = {db_path: DBManager(db_path) for db_path in db_paths}
        
        # Get selected publications from each database
        selected_pubs = {}
        for db_path, db_manager in db_managers.items():
            selected_pubs[db_path] = db_manager.get_iteration_data(
                iteration=iteration,
                selected=SelectionStage.TITLE_APPROVED
            )
        
        # Find all unique publications
        all_pubs = set()
        for pubs in selected_pubs.values():
            all_pubs.update(pubs)
        
        # Find disagreements: publications where not all raters agree
        disagreements = []
        for pub in all_pubs:
            rater_decisions = {}  # Track decision for each rater
            reasons = {}
            
            for db_path, db_manager in db_managers.items():
                # Get the article from this database
                article_list = db_manager.get_iteration_data(iteration=iteration, id=pub.id)
                db_name = os.path.basename(db_path).replace('.db', '')
                
                if article_list:
                    article = article_list[0]
                    selected_int = int(article.selected) if article.selected is not None else 0
                    is_filtered_out = getattr(article, 'title_filtered_out', False)
                    
                    # Determine decision: selected, filtered_out, or not_selected
                    if selected_int == SelectionStage.TITLE_APPROVED.value:
                        decision = 'selected'
                    elif is_filtered_out:
                        decision = 'filtered_out'
                    else:
                        decision = 'not_selected'
                    
                    rater_decisions[db_name] = decision
                    
                    # Get reason (could be string or dict)
                    reason = getattr(article, 'title_reason', '') or ''
                    # If reason is a string that looks like JSON, try to parse it
                    if isinstance(reason, str) and reason.startswith('{'):
                        try:
                            import json
                            reason = json.loads(reason)
                            # If it's a dict, extract as string for display
                            if isinstance(reason, dict):
                                reason_str = reason.get(db_name, '') or ''
                                if not reason_str:
                                    # Try to get any value from dict
                                    reason_str = list(reason.values())[0] if reason.values() else ''
                                reason = reason_str if reason_str else ''
                        except:
                            pass
                    
                    # Store reason even if empty (will show "No reason provided")
                    reasons[db_name] = reason if reason else "No reason provided"
                else:
                    # Article doesn't exist in this database - treat as not_selected
                    rater_decisions[db_name] = 'not_selected'
                    reasons[db_name] = "Article not found in this database"
            
            # Check if there's a disagreement
            selected_by = [name for name, decision in rater_decisions.items() if decision == 'selected']
            filtered_out_by = [name for name, decision in rater_decisions.items() if decision == 'filtered_out']
            not_selected_by = [name for name, decision in rater_decisions.items() if decision == 'not_selected']
            
            # Disagreement exists if there are different decisions (selected vs not selected or filtered out)
            has_disagreement = False
            if selected_by:
                # Some selected it
                if filtered_out_by or not_selected_by:
                    has_disagreement = True
            elif filtered_out_by and not_selected_by:
                # Some filtered out, some didn't select - also a disagreement
                has_disagreement = True
            
            if has_disagreement:
                disagreements.append({
                    'id': pub.id,
                    'title': pub.title or 'No title',
                    'url': pub.pub_url or pub.eprint_url or '',
                    'selected_by': selected_by,
                    'filtered_out_by': filtered_out_by,
                    'not_selected_by': not_selected_by,
                    'reasons': reasons,  # All reasons from all raters
                    'rater_decisions': rater_decisions
                })
        
        return jsonify({
            'success': True,
            'disagreements': disagreements,
            'total': len(disagreements)
        })
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/workflow/solve_title_disagreements/save_decision', methods=['POST'])
def save_title_disagreement_decision():
    """Save the final decision for a disagreement"""
    try:
        data = request.get_json()
        article_id = data.get('article_id')
        iteration = int(data.get('iteration'))
        decision = data.get('decision')  # 'accept' or 'reject'
        db_paths = data.get('db_paths', [])
        selected_reasonings = data.get('selected_reasonings', {})  # Dict of rater_name -> reason
        
        if not article_id or not decision or not db_paths:
            return jsonify({'error': 'Article ID, decision, and database paths are required'}), 400
        
        if decision not in ['accept', 'reject']:
            return jsonify({'error': 'Decision must be "accept" or "reject"'}), 400
        
        # Update all databases
        for db_path in db_paths:
            if not os.path.exists(db_path):
                continue
            
            db_manager = DBManager(db_path)
            
            if decision == 'accept':
                # Accept: set to TITLE_APPROVED and save selected reasonings
                # Build reasonings dict from selected_reasonings
                reasonings_dict = selected_reasonings
                db_manager.update_iteration_data(
                    iteration,
                    article_id,
                    selected=SelectionStage.TITLE_APPROVED.value,
                    title_reason=reasonings_dict
                )
            else:
                # Reject: set to METADATA_APPROVED (one stage back)
                db_manager.update_iteration_data(
                    iteration,
                    article_id,
                    selected=SelectionStage.METADATA_APPROVED.value
                )
        
        # Update workflow state
        search_conf = load_search_conf()
        db_path = search_conf.get('db_path', 'database.db') if search_conf else 'database.db'
        update_workflow_state(
            db_path=db_path,
            current_iteration=iteration,
            last_step="Step 6: Solve Title Disagreements"
        )
        
        return jsonify({
            'success': True,
            'message': f'Decision saved successfully'
        })
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/workflow/solve_content_disagreements', methods=['GET'])
def solve_content_disagreements_page():
    """Page for Step 8: Solve Content Disagreements"""
    search_conf = load_search_conf()
    
    # Get workflow info
    workflow_info = get_workflow_info()
    current_iteration = workflow_info.get('current_iteration') if workflow_info else None
    
    # Default to current iteration if available
    default_iteration = current_iteration if current_iteration is not None else 0
    
    # Get main database path from config
    main_db_path = search_conf.get('db_path', 'database.db') if search_conf else 'database.db'
    
    return render_template('solve_content_disagreements.html',
                         default_iteration=default_iteration,
                         main_db_path=main_db_path,
                         workflow_info=workflow_info)


@app.route('/api/workflow/solve_content_disagreements/find_disagreements', methods=['POST'])
def find_content_disagreements():
    """Find disagreements between multiple databases for content screening"""
    try:
        data = request.get_json()
        iteration = int(data.get('iteration'))
        db_paths = data.get('db_paths', [])
        
        if not db_paths or len(db_paths) < 2:
            return jsonify({'error': 'At least 2 database paths are required'}), 400
        
        # Open all databases
        db_managers = {}
        all_articles = {}
        
        for db_path in db_paths:
            if not os.path.exists(db_path):
                continue
            db_manager = DBManager(db_path)
            db_managers[db_path] = db_manager
            
            # Get all articles from this database for the iteration
            articles = db_manager.get_iteration_data(iteration=iteration)
            for article in articles:
                if article.id not in all_articles:
                    all_articles[article.id] = article
        
        disagreements = []
        for pub_id, pub in all_articles.items():
            rater_decisions = {}  # Track decision for each rater
            reasons = {}
            annotations = {}  # Track annotations for each rater
            
            for db_path, db_manager in db_managers.items():
                # Get the article from this database
                article_list = db_manager.get_iteration_data(iteration=iteration, id=pub_id)
                db_name = os.path.basename(db_path).replace('.db', '')
                
                if article_list:
                    article = article_list[0]
                    selected_int = int(article.selected) if article.selected is not None else 0
                    is_filtered_out = getattr(article, 'abstract_filtered_out', False)
                    
                    # Determine decision: selected, filtered_out, or not_selected
                    if selected_int == SelectionStage.CONTENT_APPROVED.value:
                        decision = 'selected'
                    elif is_filtered_out:
                        decision = 'filtered_out'
                    else:
                        decision = 'not_selected'
                    
                    rater_decisions[db_name] = decision
                    
                    # Get content_reason (contains JSON with reason and annotations)
                    content_reason = getattr(article, 'content_reason', '') or ''
                    reason_text = ''
                    annotation_dict = {}
                    
                    if content_reason:
                        try:
                            # Try to parse as JSON
                            import json
                            reason_json = json.loads(content_reason)
                            if isinstance(reason_json, dict):
                                reason_text = reason_json.get('reason', '')
                                # Extract annotations (all fields except 'reason')
                                for key, value in reason_json.items():
                                    if key != 'reason':
                                        annotation_dict[key] = value
                        except (json.JSONDecodeError, TypeError):
                            # Not JSON, treat as plain text reason
                            reason_text = content_reason
                    
                    # Store reason and annotations
                    reasons[db_name] = reason_text if reason_text else "No reason provided"
                    if annotation_dict:
                        annotations[db_name] = annotation_dict
                else:
                    # Article doesn't exist in this database - treat as not_selected
                    rater_decisions[db_name] = 'not_selected'
                    reasons[db_name] = "Article not found in this database"
            
            # Check if there's a disagreement
            selected_by = [name for name, decision in rater_decisions.items() if decision == 'selected']
            filtered_out_by = [name for name, decision in rater_decisions.items() if decision == 'filtered_out']
            not_selected_by = [name for name, decision in rater_decisions.items() if decision == 'not_selected']
            
            # Disagreement exists if there are different decisions
            has_disagreement = False
            if selected_by:
                # Some selected it
                if filtered_out_by or not_selected_by:
                    has_disagreement = True
            elif filtered_out_by and not_selected_by:
                # Some filtered out, some didn't select - also a disagreement
                has_disagreement = True
            
            if has_disagreement:
                disagreements.append({
                    'id': pub_id,
                    'title': pub.title or 'No title',
                    'url': pub.pub_url or pub.eprint_url or '',
                    'selected_by': selected_by,
                    'filtered_out_by': filtered_out_by,
                    'not_selected_by': not_selected_by,
                    'reasons': reasons,  # All reasons from all raters
                    'annotations': annotations,  # All annotations from all raters
                    'rater_decisions': rater_decisions
                })
        
        return jsonify({
            'success': True,
            'disagreements': disagreements,
            'total': len(disagreements)
        })
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/workflow/solve_content_disagreements/save_decision', methods=['POST'])
def save_content_disagreement_decision():
    """Save the final decision for a content disagreement"""
    try:
        data = request.get_json()
        article_id = data.get('article_id')
        iteration = int(data.get('iteration'))
        decision = data.get('decision')  # 'accept' or 'reject'
        db_paths = data.get('db_paths', [])
        selected_reasonings = data.get('selected_reasonings', {})  # Dict of rater_name -> reason
        selected_annotations = data.get('selected_annotations', {})  # Dict of rater_name -> annotations dict
        
        if not article_id or not decision or not db_paths:
            return jsonify({'error': 'Article ID, decision, and database paths are required'}), 400
        
        if decision not in ['accept', 'reject']:
            return jsonify({'error': 'Decision must be "accept" or "reject"'}), 400
        
        # Update all databases
        for db_path in db_paths:
            if not os.path.exists(db_path):
                continue
            
            db_manager = DBManager(db_path)
            
            if decision == 'accept':
                # Accept: set to CONTENT_APPROVED and merge selected reasonings and annotations
                # Combine reasonings and annotations into content_reason JSON
                import json
                
                # Merge all selected annotations into one dict
                merged_annotations = {}
                merged_reason = ''
                
                # Collect all annotations (from all selected raters)
                for rater, annotations_dict in selected_annotations.items():
                    if isinstance(annotations_dict, dict):
                        # Add all annotation fields
                        for key, value in annotations_dict.items():
                            if key != 'reason':
                                # If multiple raters have same annotation key, prefer the first one
                                if key not in merged_annotations:
                                    merged_annotations[key] = value
                
                # Collect reasonings - use first selected reasoning
                if selected_reasonings:
                    merged_reason = list(selected_reasonings.values())[0] if selected_reasonings.values() else ''
                
                # Build the content_reason JSON
                content_reason_dict = {'reason': merged_reason}
                content_reason_dict.update(merged_annotations)
                
                db_manager.update_iteration_data(
                    iteration,
                    article_id,
                    selected=SelectionStage.CONTENT_APPROVED.value,
                    content_reason=json.dumps(content_reason_dict)
                )
            else:
                # Reject: set abstract_filtered_out to True
                # Save reason (no annotations for rejected articles)
                import json
                merged_reason = ''
                if selected_reasonings:
                    merged_reason = list(selected_reasonings.values())[0] if selected_reasonings.values() else ''
                
                content_reason_dict = {'reason': merged_reason}
                db_manager.update_iteration_data(
                    iteration,
                    article_id,
                    abstract_filtered_out=True,
                    content_reason=json.dumps(content_reason_dict)
                )
        
        # Update workflow state
        search_conf = load_search_conf()
        db_path = search_conf.get('db_path', 'database.db') if search_conf else 'database.db'
        update_workflow_state(
            db_path=db_path,
            current_iteration=iteration,
            last_step="Step 8: Solve Content Disagreements"
        )
        
        return jsonify({
            'success': True,
            'message': f'Decision saved successfully'
        })
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/workflow/remove_duplicates', methods=['GET'])
def remove_duplicates_page():
    """Page for Step 9: Remove Duplicates"""
    # Get workflow info
    workflow_info = get_workflow_info()
    current_iteration = workflow_info.get('current_iteration') if workflow_info else None
    
    # Default to current iteration if available
    default_iteration = current_iteration if current_iteration is not None else 0
    
    return render_template('remove_duplicates.html',
                         default_iteration=default_iteration,
                         workflow_info=workflow_info)


@app.route('/api/workflow/remove_duplicates/find', methods=['POST'])
def find_duplicates():
    """Find duplicate articles based on title similarity"""
    try:
        from difflib import SequenceMatcher
        
        data = request.get_json()
        iterations = data.get('iterations', [])
        similarity_threshold = float(data.get('similarity_threshold', 0.8))
        
        if not iterations:
            return jsonify({'error': 'At least one iteration is required'}), 400
        
        if similarity_threshold < 0 or similarity_threshold > 1:
            return jsonify({'error': 'Similarity threshold must be between 0.0 and 1.0'}), 400
        
        # Get database path from config
        search_conf = load_search_conf()
        if not search_conf or 'db_path' not in search_conf:
            return jsonify({'error': 'Database path not configured'}), 400
        
        db_path = search_conf['db_path']
        db_manager = DBManager(db_path)
        
        # Fetch articles from all specified iterations
        total_articles = []
        for iteration in iterations:
            articles = db_manager.get_iteration_data(
                iteration=iteration,
                selected=SelectionStage.CONTENT_APPROVED
            )
            total_articles.extend(articles)
        
        # Find duplicate candidates
        duplicates = []
        processed = set()
        
        def calculate_title_similarity(title1: str, title2: str) -> float:
            """Calculate similarity between two titles"""
            norm_title1 = title1.lower().strip() if title1 else ''
            norm_title2 = title2.lower().strip() if title2 else ''
            return SequenceMatcher(None, norm_title1, norm_title2).ratio()
        
        for i, article1 in enumerate(total_articles):
            if article1.id in processed:
                continue
            
            for j, article2 in enumerate(total_articles[i+1:], i+1):
                if article2.id in processed:
                    continue
                
                similarity = calculate_title_similarity(article1.title, article2.title)
                
                if similarity >= similarity_threshold:
                    # Convert articles to dict for JSON serialization
                    article1_dict = {
                        'id': article1.id,
                        'title': article1.title or '',
                        'authors': article1.authors or '',
                        'venue': article1.venue or '',
                        'pub_year': article1.pub_year or 0,
                        'pub_url': article1.pub_url or '',
                        'eprint_url': article1.eprint_url or '',
                        'num_citations': getattr(article1, 'num_citations', -1),
                        'iteration': article1.iteration
                    }
                    article2_dict = {
                        'id': article2.id,
                        'title': article2.title or '',
                        'authors': article2.authors or '',
                        'venue': article2.venue or '',
                        'pub_year': article2.pub_year or 0,
                        'pub_url': article2.pub_url or '',
                        'eprint_url': article2.eprint_url or '',
                        'num_citations': getattr(article2, 'num_citations', -1),
                        'iteration': article2.iteration
                    }
                    
                    duplicates.append({
                        'article1': article1_dict,
                        'article2': article2_dict,
                        'similarity': similarity
                    })
                    
                    processed.add(article1.id)
                    processed.add(article2.id)
                    break
        
        return jsonify({
            'success': True,
            'duplicates': duplicates,
            'total': len(duplicates)
        })
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/workflow/remove_duplicates/save_decision', methods=['POST'])
def save_duplicate_decision():
    """Save the duplicate resolution decision"""
    try:
        data = request.get_json()
        article1_id = data.get('article1_id')
        article2_id = data.get('article2_id')
        article1_iteration = int(data.get('article1_iteration'))
        article2_iteration = int(data.get('article2_iteration'))
        decision = data.get('decision')  # 'keep_article1', 'keep_article2', or 'keep_both'
        keep_id = data.get('keep_id')
        remove_id = data.get('remove_id')
        
        if not article1_id or not article2_id or not decision:
            return jsonify({'error': 'Article IDs and decision are required'}), 400
        
        if decision not in ['keep_article1', 'keep_article2', 'keep_both']:
            return jsonify({'error': 'Invalid decision'}), 400
        
        # Get database path from config
        search_conf = load_search_conf()
        if not search_conf or 'db_path' not in search_conf:
            return jsonify({'error': 'Database path not configured'}), 400
        
        db_path = search_conf['db_path']
        db_manager = DBManager(db_path)
        
        if decision == 'keep_both':
            # Don't mark anything as duplicate
            pass
        else:
            # Mark the article to remove as duplicate
            if remove_id:
                remove_iteration = article2_iteration if remove_id == article2_id else article1_iteration
                db_manager.update_iteration_data(
                    iteration=remove_iteration,
                    article_id=remove_id,
                    selected=SelectionStage.DUPLICATE.value
                )
        
        # Update workflow state
        update_workflow_state(
            db_path=db_path,
            current_iteration=None,  # Don't change iteration
            last_step="Step 9: Remove Duplicates"
        )
        
        return jsonify({
            'success': True,
            'message': 'Decision saved successfully'
        })
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/workflow/generate_csv', methods=['GET'])
def generate_csv_page():
    """Page for Step 10: Generate CSV"""
    search_conf = load_search_conf()
    
    # Get workflow info
    workflow_info = get_workflow_info()
    current_iteration = workflow_info.get('current_iteration') if workflow_info else None
    
    # Default to current iteration if available
    default_iteration = current_iteration if current_iteration is not None else 0
    
    # Get CSV path from config
    csv_path = search_conf.get('csv_path', 'results.csv') if search_conf else 'results.csv'
    
    return render_template('generate_csv.html',
                         default_iteration=default_iteration,
                         csv_path=csv_path,
                         workflow_info=workflow_info)


@app.route('/api/workflow/generate_csv/export', methods=['POST'])
def generate_csv_export():
    """Generate CSV file with content-approved articles"""
    try:
        import pandas as pd
        import os
        
        data = request.get_json()
        iterations = data.get('iterations', [])
        suggested_filename = data.get('output_path', 'results.csv')  # Used for download filename suggestion
        
        if not iterations:
            return jsonify({'error': 'At least one iteration is required'}), 400
        
        # Get database path from config
        search_conf = load_search_conf()
        if not search_conf or 'db_path' not in search_conf:
            return jsonify({'error': 'Database path not configured'}), 400
        
        db_path = search_conf['db_path']
        db_manager = DBManager(db_path)
        
        # Fetch articles from all specified iterations
        article_data = []
        for iteration in iterations:
            articles = db_manager.get_iteration_data(
                iteration=iteration,
                selected=SelectionStage.CONTENT_APPROVED
            )
            
            for article in articles:
                # Parse content_reason to extract reason and annotations
                content_reason = getattr(article, 'content_reason', '') or ''
                reason_text = ''
                annotations_dict = {}
                
                if content_reason:
                    try:
                        reason_json = json.loads(content_reason)
                        if isinstance(reason_json, dict):
                            reason_text = reason_json.get('reason', '')
                            # Extract annotations (everything except 'reason')
                            for key, value in reason_json.items():
                                if key != 'reason':
                                    annotations_dict[key] = value
                    except (json.JSONDecodeError, TypeError):
                        # Not JSON, treat as plain text reason
                        reason_text = content_reason
                
                # Parse authors if it's JSON
                authors_text = article.authors or ''
                if authors_text:
                    try:
                        authors_json = json.loads(authors_text)
                        if isinstance(authors_json, list):
                            authors_text = ', '.join([a.get('name', a) if isinstance(a, dict) else str(a) for a in authors_json])
                    except (json.JSONDecodeError, TypeError):
                        pass  # Use as-is
                
                # Get URL (prefer pub_url, fallback to eprint_url)
                url = article.pub_url or article.eprint_url or ''
                
                # Build row data
                row_data = {
                    'title': article.title or '',
                    'authors': authors_text,
                    'year': article.pub_year or '',
                    'venue': article.venue or '',
                    'citations': getattr(article, 'num_citations', -1) if int(getattr(article, 'num_citations', -1)) >= 0 else '',
                    'url': url,
                    'iteration': iteration,
                    'reason': reason_text
                }
                
                # Add annotation fields
                for key, value in annotations_dict.items():
                    row_data[key] = value
                
                article_data.append(row_data)
        
        # Create DataFrame and save to CSV
        if not article_data:
            return jsonify({
                'success': False,
                'error': 'No content-approved articles found in the specified iterations'
            }), 400
        
        df = pd.DataFrame(article_data)
        
        # Save CSV to uploads directory for web access only
        uploads_dir = 'uploads'
        os.makedirs(uploads_dir, exist_ok=True)
        
        # Generate a unique filename based on timestamp
        import time
        timestamp = int(time.time())
        
        # Use suggested filename if provided, otherwise default
        if suggested_filename and suggested_filename.endswith('.csv'):
            base_name = suggested_filename[:-4]  # Remove .csv extension
            filename = f'{base_name}_{timestamp}.csv'
        else:
            filename = f'results_{timestamp}.csv'
        
        csv_path_in_uploads = os.path.join(uploads_dir, filename)
        
        # Save CSV to uploads directory (only location where file is saved)
        df.to_csv(csv_path_in_uploads, index=False)
        
        # Update workflow state
        update_workflow_state(
            db_path=db_path,
            current_iteration=None,  # Don't change iteration
            last_step="Step 10: Generate CSV"
        )
        
        # Return download URL using Flask route
        download_url = f'/api/workflow/generate_csv/download/{filename}'
        
        return jsonify({
            'success': True,
            'csv_filename': filename,
            'article_count': len(article_data),
            'download_url': download_url
        })
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/workflow/generate_csv/download/<filename>')
def download_csv(filename):
    """Serve CSV file for download"""
    try:
        import os
        
        # Ensure filename is safe (no path traversal)
        filename = os.path.basename(filename)
        csv_path = os.path.join('uploads', filename)
        
        if not os.path.exists(csv_path):
            return jsonify({'error': 'CSV file not found'}), 404
        
        return send_file(
            csv_path,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    # Create templates and static directories if they don't exist
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    
    app.run(debug=True, host='0.0.0.0', port=5000)

