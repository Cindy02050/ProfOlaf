#!/usr/bin/env python3
"""
Script to generate snowball sampling starting points from accepted papers.
Extracts titles from accepted_papers.json, searches Google Scholar for citation numbers,
and outputs in the format of initial.json.
"""

import json
import re
import time
import requests
from urllib.parse import quote_plus
import argparse
from typing import List, Dict, Optional, Tuple
from enum import Enum
from scholarly import scholarly
from utils.proxy_generator import get_proxy
from tqdm import tqdm
import hashlib
from dotenv import load_dotenv
from utils.db_management import (
    DBManager, 
    initialize_db, 
    SelectionStage
)

from utils.article_search_method import (
    ArticleSearch, 
    SearchMethod,
)

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

import sv_ttk
import threading
import os

ITERATION_0 = 0 

load_dotenv()

def load_search_conf():
    """Load search configuration from JSON file"""
    try:
        with open("search_conf.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}

search_conf = load_search_conf()

def extract_titles_from_file(file_path: str) -> List[str]:
    """
    Extract titles from a file. The file should be a text file with one title per line.
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f.readlines() if line.strip()]
    
def generate_snowball_start(input_file: str, iteration: int, delay: float = 2.0, 
                           db_manager: DBManager = None, search_method: SearchMethod = SearchMethod.GOOGLE_SCHOLAR,
                           log_callback=None, progress_callback=None, cancel_flag=None):
    """
    Generate snowball sampling starting points from accepted papers.
    
    Args:
        input_file: Path to the input JSON file (e.g., accepted_papers.json)
        iteration: Iteration number for the search
        delay: Delay between requests to avoid rate limiting
        db_manager: Database manager instance
        search_method: Search method to use (SearchMethod enum)
        log_callback: Function to call with log messages (message: str) -> None
        progress_callback: Function to call with progress updates (current: int, total: int) -> None
        cancel_flag: threading.Event to check for cancellation
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)
    
    def update_progress(current, total):
        if progress_callback:
            progress_callback(current, total)
    
    log(f"Reading titles from {input_file}...")
    titles = extract_titles_from_file(input_file)
    if not titles:
        log("No titles found in the input file.")
        return
    log(f"Found {len(titles)} titles. Starting searches with {search_method.value}...")
    
    search_method_instance = search_method.create_instance()
    article_search = ArticleSearch(search_method_instance)
    
    initial_pubs = []
    seen_titles = []
    
    for i, title in enumerate(titles, 1):
        # Check for cancellation
        if cancel_flag and cancel_flag.is_set():
            log("Operation cancelled by user.")
            return
        
        log(f"Searching [{i}/{len(titles)}]: {title[:60]}...")
        update_progress(i - 1, len(titles))
        
        article_data = article_search.search(title)
        if article_data:
            article_data.set_iteration(iteration)
            article_data.set_selected(SelectionStage.CONTENT_APPROVED)
            initial_pubs.append(article_data)
            seen_titles.append((title, article_data.id))
            log(f"  ✓ Found article: {article_data.title[:60] if article_data.title else 'Unknown'}")
        else:
            log(f"  ✗ No article found")

        if i < len(titles):
            time.sleep(delay)

    log("Saving results to database...")
    db_manager.insert_iteration_data(initial_pubs)
    db_manager.insert_seen_titles_data(seen_titles)
    log(f"✓ Successfully processed {len(initial_pubs)} articles and saved to database.")
    update_progress(len(titles), len(titles))


class SnowballStartGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Generate Snowball Start")
        self.root.geometry("900x700")
        
        # Configure modern color scheme
        self.setup_styles()
        
        # Load defaults from search_conf
        default_input_file = search_conf.get("initial_file", "")
        default_db_path = search_conf.get("db_path", "")
        default_search_method = search_conf.get("search_method", "google_scholar")
        default_delay = 1.0
        
        # Variables to store input values
        self.input_file_var = tk.StringVar(value=default_input_file)
        self.db_path_var = tk.StringVar(value=default_db_path)
        self.delay_var = tk.StringVar(value=str(default_delay))
        self.search_method_var = tk.StringVar(value=default_search_method)
        
        # Threading control
        self.worker_thread = None
        self.cancel_flag = threading.Event()
        self.is_running = False
        
        self.create_widgets()
    
    def get_modern_fonts(self):
        """Get modern font families that work cross-platform"""
        import platform
        
        # Modern UI fonts (try modern first, fallback to system defaults)
        modern_fonts = [
            'Inter',           # Modern, clean
            'Roboto',          # Google's modern font
            'SF Pro Display',  # Apple's modern font
            'Segoe UI Variable',  # Windows 11 modern font
            'Ubuntu',          # Modern Linux font
        ]
        
        # System default fallbacks - use modern system fonts
        system = platform.system()
        if system == 'Windows':
            ui_font = 'Segoe UI Variable'  # Windows 11 modern variable font (falls back to Segoe UI if not available)
        elif system == 'Darwin':
            ui_font = 'SF Pro Display'  # macOS modern font
        else:
            ui_font = 'Roboto'  # Modern Linux font
        
        # Modern monospace fonts for code/logs - prioritize most modern first
        monospace_font = 'JetBrains Mono'  # Very modern, clean programming font
        
        return "Roboto", "Roboto"
    
    def setup_styles(self):
        """Configure modern ttk styles"""
        style = ttk.Style()
        
        # Get modern fonts
        ui_font, monospace_font = self.get_modern_fonts()
        self.ui_font = ui_font
        self.monospace_font = monospace_font
        
        # Detect current theme (dark or light)
        # Check if sv_ttk dark theme is active
        current_theme = style.theme_use()
        current_theme_lower = current_theme.lower()
        
        # Check for various dark theme indicators
        is_dark_theme = (
            'dark' in current_theme_lower or 
            'sun-valley-dark' in current_theme_lower or
            'sunvalley-dark' in current_theme_lower
        )
        
        # Also check the root window background color as a fallback
        try:
            root_bg = self.root.cget('bg')
            # If root background is very dark, likely dark theme
            if root_bg and any(c.isdigit() for c in root_bg):
                # Parse hex color
                if root_bg.startswith('#'):
                    r, g, b = int(root_bg[1:3], 16), int(root_bg[3:5], 16), int(root_bg[5:7], 16)
                    # If average brightness is low, it's dark
                    avg_brightness = (r + g + b) / 3
                    if avg_brightness < 100:
                        is_dark_theme = True
        except:
            pass
        
        # Use theme-aware colors
        if is_dark_theme:
            # Dark theme colors
            bg_color = '#1e1e1e'
            fg_color = '#ffffff'
            card_bg = '#2d2d2d'
            accent_color = '#0d7377'
            success_color = '#14a085'
            danger_color = '#c44569'
            log_bg = '#252525'
            log_fg = '#e0e0e0'
        else:
            # Light theme colors
            bg_color = '#f5f5f5'
            fg_color = '#2c3e50'
            card_bg = '#ffffff'
            accent_color = '#3498db'
            success_color = '#27ae60'
            danger_color = '#e74c3c'
            log_bg = '#fafafa'
            log_fg = '#2c3e50'
        
        # Store colors for later use
        self.bg_color = bg_color
        self.fg_color = fg_color
        self.card_bg = card_bg
        self.accent_color = accent_color
        self.success_color = success_color
        self.danger_color = danger_color
        self.log_bg = log_bg
        self.log_fg = log_fg
        self.is_dark_theme = is_dark_theme
        
        # Configure style for the root (only if not using sv_ttk)
        if not is_dark_theme:
            self.root.configure(bg=bg_color)
        
        # Configure button styles (only customize if not using sv_ttk dark theme)
        if not is_dark_theme:
            style.configure('Accent.TButton',
                           background=accent_color,
                           foreground='white',
                           borderwidth=0,
                           focuscolor='none',
                           padding=(20, 10),
                           font=(ui_font, 10, 'bold'))
            
            style.map('Accent.TButton',
                     background=[('active', '#2980b9'), ('pressed', '#21618c')])
            
            style.configure('Success.TButton',
                           background=success_color,
                           foreground='white',
                           borderwidth=0,
                           focuscolor='none',
                           padding=(20, 10),
                           font=(ui_font, 10, 'bold'))
            
            style.map('Success.TButton',
                     background=[('active', '#229954'), ('pressed', '#1e8449')])
            
            style.configure('Danger.TButton',
                           background=danger_color,
                           foreground='white',
                           borderwidth=0,
                           focuscolor='none',
                           padding=(15, 10),
                           font=(ui_font, 10))
            
            style.map('Danger.TButton',
                     background=[('active', '#c0392b'), ('pressed', '#a93226')])
            
            style.configure('Secondary.TButton',
                           background='#95a5a6',
                           foreground='white',
                           borderwidth=0,
                           focuscolor='none',
                           padding=(15, 10),
                           font=(ui_font, 10))
            
            style.map('Secondary.TButton',
                     background=[('active', '#7f8c8d'), ('pressed', '#6c757d')])
        
        # Configure entry styles
        style.configure('Modern.TEntry',
                       fieldbackground=card_bg if is_dark_theme else 'white',
                       borderwidth=1,
                       relief='solid',
                       padding=8,
                       font=(ui_font, 10))
        
        # Configure combobox styles (let sv_ttk handle it for dark theme)
        if not is_dark_theme:
            style.configure('TCombobox',
                           fieldbackground='white',
                           borderwidth=1,
                           padding=8,
                           font=(ui_font, 10))
            style.map('TCombobox',
                     fieldbackground=[('readonly', 'white')],
                     selectbackground=[('readonly', 'white')])
        
        # Configure label styles
        style.configure('Title.TLabel',
                       background=bg_color,
                       foreground=fg_color,
                       font=(ui_font, 17, 'bold'),
                       padding=(0, 10, 0, 20))
        
        style.configure('Heading.TLabel',
                       background=bg_color,
                       foreground=fg_color,
                       font=(ui_font, 11, 'bold'),
                       padding=(0, 5, 0, 5))
        
        style.configure('Normal.TLabel',
                       background=bg_color,
                       foreground=fg_color,
                       font=(ui_font, 10),
                       padding=(0, 5))
        
        # Configure labelframe styles
        border_color = '#4a4a4a' if is_dark_theme else '#bdc3c7'
        style.configure('Card.TLabelframe',
                       background=bg_color,
                       relief='flat',
                       borderwidth=1,
                       bordercolor=border_color)
        
        style.configure('Card.TLabelframe.Label',
                       background=bg_color,
                       foreground=fg_color,
                       font=(ui_font, 11, 'bold'))
        
        # Configure progress bar style
        trough_color = '#3a3a3a' if is_dark_theme else '#ecf0f1'
        style.configure('TProgressbar',
                       background=accent_color,
                       troughcolor=trough_color,
                       borderwidth=0,
                       lightcolor=accent_color,
                       darkcolor=accent_color,
                       thickness=25)
    
    def create_widgets(self):
        # Main container with padding
        container = tk.Frame(self.root, bg=self.bg_color)
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Header/Title section
        header_frame = tk.Frame(container, bg=self.bg_color)
        header_frame.pack(fill=tk.X, pady=(0, 20))
        
        title_label = ttk.Label(header_frame, text="Generate Snowball Start", style='Title.TLabel')
        title_label.pack()
        
        subtitle_label = ttk.Label(header_frame, 
                                   text="Configure and execute article search from initial titles",
                                   style='Normal.TLabel')
        subtitle_label.pack()
        
        # Main frame with card-like appearance
        border_color = '#4a4a4a' if self.is_dark_theme else '#e0e0e0'
        main_frame = tk.Frame(container, bg=self.card_bg, relief='flat', bd=0)
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.config(highlightbackground=border_color, highlightthickness=1)
        
        # Content padding
        content_frame = ttk.Frame(main_frame, padding="25")
        content_frame.pack(fill=tk.BOTH, expand=True)
        content_frame.columnconfigure(1, weight=1)
        
        row = 0
        
        # Input File
        file_frame = tk.Frame(content_frame, bg=self.card_bg)
        file_frame.grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 15))
        file_frame.columnconfigure(1, weight=1)
        
        ttk.Label(file_frame, text="📄 Input File", style='Heading.TLabel', background=self.card_bg).grid(row=0, column=0, columnspan=2, sticky=tk.W)
        input_file_entry = ttk.Entry(file_frame, textvariable=self.input_file_var, style='Modern.TEntry', width=50)
        input_file_entry.grid(row=1, column=0, sticky=(tk.W, tk.E), padx=(0, 10))
        browse_btn = ttk.Button(file_frame, text="Browse...", 
                               command=lambda: self.browse_file(self.input_file_var),
                               style='Secondary.TButton')
        browse_btn.grid(row=1, column=1, sticky=tk.W)
        row += 1
        
        # Database Path
        db_frame = tk.Frame(content_frame, bg=self.card_bg)
        db_frame.grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 15))
        db_frame.columnconfigure(1, weight=1)
        
        ttk.Label(db_frame, text="💾 Database Path", style='Heading.TLabel', background=self.card_bg).grid(row=0, column=0, columnspan=2, sticky=tk.W)
        db_path_entry = ttk.Entry(db_frame, textvariable=self.db_path_var, style='Modern.TEntry', width=50)
        db_path_entry.grid(row=1, column=0, sticky=(tk.W, tk.E), padx=(0, 10))
        db_browse_btn = ttk.Button(db_frame, text="Browse...", 
                                   command=lambda: self.browse_file(self.db_path_var, 
                                                                   filetypes=[("Database files", "*.db"), ("All files", "*.*")],
                                                                   mode="save"),
                                   style='Secondary.TButton')
        db_browse_btn.grid(row=1, column=1, sticky=tk.W)
        row += 1
        
        # Configuration row
        config_frame = tk.Frame(content_frame, bg=self.card_bg)
        config_frame.grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 20))
        config_frame.columnconfigure(0, weight=1)
        config_frame.columnconfigure(2, weight=1)
        
        # Delay
        delay_container = tk.Frame(config_frame, bg=self.card_bg)
        delay_container.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 15))
        ttk.Label(delay_container, text="Delay (seconds)", style='Heading.TLabel', background=self.card_bg).pack(anchor=tk.W)
        delay_entry = ttk.Entry(delay_container, textvariable=self.delay_var, style='Modern.TEntry', width=15)
        delay_entry.pack(anchor=tk.W, pady=(5, 0))
        
        # Search Method
        method_container = tk.Frame(config_frame, bg=self.card_bg)
        method_container.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(15, 0))
        ttk.Label(method_container, text="🔍 Search Method", style='Heading.TLabel', background=self.card_bg).pack(anchor=tk.W)
        search_method_combo = ttk.Combobox(method_container, textvariable=self.search_method_var, 
                                          values=["google_scholar", "semantic_scholar", "dblp"], 
                                          state="readonly", width=20, font=(self.ui_font, 10))
        search_method_combo.pack(anchor=tk.W, pady=(5, 0))
        row += 1
        
        # Progress Section
        progress_frame = tk.Frame(content_frame, bg=self.card_bg)
        progress_frame.grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 20))
        progress_frame.columnconfigure(0, weight=1)
        
        progress_header = tk.Frame(progress_frame, bg=self.card_bg)
        progress_header.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        progress_header.columnconfigure(0, weight=1)
        
        ttk.Label(progress_header, text="📈 Progress", style='Heading.TLabel', background=self.card_bg).grid(row=0, column=0, sticky=tk.W)
        self.progress_var = tk.StringVar(value="Ready")
        self.progress_label = ttk.Label(progress_header, textvariable=self.progress_var, 
                                        style='Normal.TLabel', background=self.card_bg,
                                        font=(self.ui_font, 9))
        self.progress_label.grid(row=0, column=1, sticky=tk.E)
        
        self.progress_bar = ttk.Progressbar(progress_frame, mode='determinate', length=400, 
                                           style='TProgressbar')
        self.progress_bar.grid(row=1, column=0, sticky=(tk.W, tk.E))
        row += 1
        
        # Log Output
        log_frame = ttk.LabelFrame(content_frame, text="📝 Log Output", padding="10", style='Card.TLabelframe')
        log_frame.grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 20))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        # Configure log text styling
        select_bg = '#0d7377' if self.is_dark_theme else '#3498db'
        select_fg = '#ffffff' if self.is_dark_theme else 'white'
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, width=70, wrap=tk.WORD,
                                                  bg=self.log_bg, fg=self.log_fg, 
                                                  font=(self.monospace_font, 10),
                                                  relief='flat', bd=0,
                                                  padx=10, pady=10,
                                                  selectbackground=select_bg,
                                                  selectforeground=select_fg)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        row += 1
        
        # Buttons
        button_frame = tk.Frame(content_frame, bg=self.card_bg)
        button_frame.grid(row=row, column=0, columnspan=2, pady=(10, 0))
        
        self.start_button = ttk.Button(button_frame, text="▶ Start", command=self.start_generation,
                                      style='Success.TButton')
        self.start_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.stop_button = ttk.Button(button_frame, text="■ Stop", command=self.stop_generation, 
                                     state="disabled", style='Danger.TButton')
        self.stop_button.pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(button_frame, text="🗑 Clear Log", command=self.clear_log,
                  style='Secondary.TButton').pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(button_frame, text="✕ Close", command=self.root.quit,
                  style='Secondary.TButton').pack(side=tk.LEFT)
        
        # Configure row weights for scrolling
        content_frame.rowconfigure(row - 1, weight=1)
    
    def browse_file(self, var, filetypes=None, mode="open"):
        """Open file dialog to browse for a file"""
        if mode == "save":
            if filetypes is None:
                filename = filedialog.asksaveasfilename()
            else:
                filename = filedialog.asksaveasfilename(filetypes=filetypes)
        else:
            if filetypes is None:
                filename = filedialog.askopenfilename()
            else:
                filename = filedialog.askopenfilename(filetypes=filetypes)
        if filename:
            var.set(filename)
    
    def clear_log(self):
        """Clear the log output"""
        self.log_text.delete("1.0", tk.END)
    
    def log(self, message: str, level="info"):
        """Add a message to the log output (thread-safe)
        
        Args:
            message: The log message
            level: Log level - 'info', 'success', 'error', 'warning'
        """
        # Auto-detect log level from message content
        if not isinstance(level, str) or level not in ["info", "success", "error", "warning"]:
            level = self._detect_log_level(message)
        
        self.root.after(0, self._log_safe, message, level)
    
    def _detect_log_level(self, message: str) -> str:
        """Auto-detect log level from message content"""
        msg_lower = message.lower()
        if any(x in msg_lower for x in ["✓", "successfully", "found article", "saved"]):
            return "success"
        elif any(x in msg_lower for x in ["✗", "error", "failed", "not found"]):
            return "error"
        elif any(x in msg_lower for x in ["warning", "warn"]):
            return "warning"
        return "info"
    
    def _log_safe(self, message: str, level: str = "info"):
        """Thread-safe log update (called from main thread)"""
        # Theme-aware color mapping for different log levels
        if self.is_dark_theme:
            colors = {
                "info": "#e0e0e0",
                "success": "#14a085",
                "error": "#c44569",
                "warning": "#f39c12"
            }
        else:
            colors = {
                "info": "#2c3e50",
                "success": "#27ae60",
                "error": "#e74c3c",
                "warning": "#f39c12"
            }
        
        color = colors.get(level, colors["info"])
        
        # Create unique tag for this log entry to avoid conflicts
        tag_name = f"log_{level}_{hash(message) % 10000}"
        
        # Insert with color
        self.log_text.insert(tk.END, message + "\n", tag_name)
        self.log_text.tag_config(tag_name, foreground=color)
        self.log_text.see(tk.END)
        
        # Limit log size to prevent memory issues (keep last 1000 lines)
        lines = int(self.log_text.index('end-1c').split('.')[0])
        if lines > 1000:
            self.log_text.delete('1.0', f'{lines-1000}.0')
    
    def update_progress(self, current: int, total: int):
        """Update progress bar (thread-safe)"""
        self.root.after(0, self._update_progress_safe, current, total)
    
    def _update_progress_safe(self, current: int, total: int):
        """Thread-safe progress update (called from main thread)"""
        if total > 0:
            progress = (current / total) * 100
            self.progress_bar['value'] = progress
            self.progress_var.set(f"{current}/{total} ({progress:.1f}%)")
        else:
            self.progress_bar['value'] = 0
            self.progress_var.set("Ready")
    
    def validate_inputs(self) -> Tuple[bool, str]:
        """Validate all inputs and return (is_valid, error_message)"""
        if not self.input_file_var.get().strip():
            return False, "Input file is required."
        
        if not os.path.exists(self.input_file_var.get().strip()):
            return False, f"Input file does not exist: {self.input_file_var.get().strip()}"
        
        if not self.db_path_var.get().strip():
            return False, "Database path is required."
        
        try:
            delay = float(self.delay_var.get())
            if delay < 0:
                return False, "Delay must be non-negative."
        except ValueError:
            return False, "Delay must be a valid number."
        
        search_method_str = self.search_method_var.get()
        try:
            SearchMethod(search_method_str)
        except ValueError:
            return False, f"Invalid search method: {search_method_str}"
        
        return True, ""
    
    def worker_thread_func(self):
        """Worker thread function to run the generation"""
        try:
            # Validate inputs
            is_valid, error_msg = self.validate_inputs()
            if not is_valid:
                self.log(f"Error: {error_msg}")
                self.root.after(0, self._on_complete)
                return
            
            # Parse inputs
            input_file = self.input_file_var.get().strip()
            db_path = self.db_path_var.get().strip()
            delay = float(self.delay_var.get())
            search_method_str = self.search_method_var.get()
            search_method = SearchMethod(search_method_str)
            
            # Initialize database
            self.log("Initializing database...")
            db_manager = initialize_db(db_path)
            
            # Run generation
            generate_snowball_start(
                input_file=input_file,
                iteration=ITERATION_0,
                delay=delay,
                db_manager=db_manager,
                search_method=search_method,
                log_callback=self.log,
                progress_callback=self.update_progress,
                cancel_flag=self.cancel_flag
            )
            
            if not self.cancel_flag.is_set():
                self.log("✓ Generation completed successfully!")
            
        except Exception as e:
            self.log(f"Error: {str(e)}")
            import traceback
            self.log(traceback.format_exc())
        finally:
            self.root.after(0, self._on_complete)
    
    def start_generation(self):
        """Start the generation process"""
        if self.is_running:
            return
        
        # Validate inputs
        is_valid, error_msg = self.validate_inputs()
        if not is_valid:
            messagebox.showerror("Validation Error", error_msg)
            return
        
        # Reset cancel flag
        self.cancel_flag.clear()
        self.is_running = True
        
        # Update UI
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.progress_bar['value'] = 0
        self.progress_var.set("Starting...")
        self.clear_log()
        
        # Start worker thread
        self.worker_thread = threading.Thread(target=self.worker_thread_func, daemon=True)
        self.worker_thread.start()
    
    def stop_generation(self):
        """Stop the generation process"""
        if not self.is_running:
            return
        
        self.log("Stopping generation... Please wait.")
        self.cancel_flag.set()
    
    def _on_complete(self):
        """Called when generation completes (from main thread)"""
        self.is_running = False
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")
        if not self.cancel_flag.is_set():
            self.progress_var.set("Completed")
        else:
            self.progress_var.set("Cancelled")


def main_gui():
    """Main function for GUI mode"""
    root = tk.Tk()
    sv_ttk.set_theme("dark")
    app = SnowballStartGUI(root)
    root.mainloop()


def main_cli():
    """Main function for CLI mode"""
    parser = argparse.ArgumentParser(description='Generate snowball sampling starting points from file')
    parser.add_argument('--input_file', help='Path to the input file (json or text)', 
                       default=search_conf.get("initial_file", ""))
    parser.add_argument('--delay', type=float, default=1.0, 
                       help='Delay between API requests in seconds (default: 1.0)')
    parser.add_argument('--db_path', help='db path', type=str, 
                       default=search_conf.get("db_path", ""))
    parser.add_argument(
        '--search_method', 
        help='Search method to use', 
        type=str, 
        default=search_conf.get("search_method", "google_scholar"),
        choices=[method.value for method in SearchMethod]
    )
    parser.add_argument('--gui', action='store_true', help='Launch GUI interface')
    args = parser.parse_args()

    if args.gui:
        main_gui()
        return

    # Convert string to enum
    try:
        search_method = SearchMethod(args.search_method)
    except ValueError:
        print(f"Error: Invalid search method '{args.search_method}'. Available options: {[method.value for method in SearchMethod]}")
        return

    db_manager = initialize_db(args.db_path)
    generate_snowball_start(args.input_file, ITERATION_0, args.delay, db_manager, search_method)


if __name__ == "__main__":
    import sys
    # If no arguments provided or --gui flag, launch GUI
    if len(sys.argv) == 1 or '--gui' in sys.argv:
        main_gui()
    else:
        main_cli()
