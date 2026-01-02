import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from typing import List, Tuple


class SearchConfigGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Search Configuration Generator")
        self.root.geometry("700x800")
        
        # Variables to store input values
        self.start_year_var = tk.StringVar()
        self.end_year_var = tk.StringVar()
        self.venue_list = []
        self.proxy_key_var = tk.StringVar()
        self.proxy_is_file_var = tk.BooleanVar(value=False)
        self.initial_file_var = tk.StringVar()
        self.db_path_var = tk.StringVar()
        self.csv_path_var = tk.StringVar()
        self.search_method_var = tk.StringVar(value="google_scholar")
        self.annotations_list = []
        
        self.create_widgets()
    
    def create_widgets(self):
        # Main frame with scrolling
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        row = 0
        
        # Start Year
        ttk.Label(main_frame, text="Starting Year:").grid(row=row, column=0, sticky=tk.W, pady=5)
        start_year_entry = ttk.Entry(main_frame, textvariable=self.start_year_var, width=20)
        start_year_entry.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)
        row += 1
        
        # End Year
        ttk.Label(main_frame, text="Ending Year:").grid(row=row, column=0, sticky=tk.W, pady=5)
        end_year_entry = ttk.Entry(main_frame, textvariable=self.end_year_var, width=20)
        end_year_entry.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)
        row += 1
        
        # Venue Ranks
        venue_frame = ttk.LabelFrame(main_frame, text="Accepted Venue Ranks", padding="5")
        venue_frame.grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        venue_frame.columnconfigure(0, weight=1)
        
        self.venue_text = scrolledtext.ScrolledText(venue_frame, height=4, width=40)
        self.venue_text.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=2)
        ttk.Label(venue_frame, text="Enter venue ranks separated by commas (e.g., A*, A, B, Q1, Q2):", 
                 font=('TkDefaultFont', 10)).grid(row=1, column=0, columnspan=2, sticky=tk.W)
        row += 1
        
        # Proxy Key
        proxy_frame = ttk.Frame(main_frame)
        proxy_frame.grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        proxy_frame.columnconfigure(0, weight=1)
        ttk.Label(proxy_frame, text="Proxy Key (optional):").grid(row=0, column=0, sticky=tk.W)
        proxy_entry = ttk.Entry(proxy_frame, textvariable=self.proxy_key_var, width=30)
        proxy_entry.grid(row=1, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        proxy_checkbox = ttk.Checkbutton(proxy_frame, text="From file", variable=self.proxy_is_file_var,
                                         command=self.toggle_proxy_browse)
        proxy_checkbox.grid(row=1, column=1, sticky=tk.W, padx=(0, 5))
        self.proxy_browse_btn = ttk.Button(proxy_frame, text="Browse...", 
                                           command=lambda: self.browse_file(self.proxy_key_var),
                                           state="disabled")
        self.proxy_browse_btn.grid(row=1, column=2)
        row += 1
        
        # Initial File
        file_frame = ttk.Frame(main_frame)
        file_frame.grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        file_frame.columnconfigure(0, weight=1)
        ttk.Label(file_frame, text="Initial File:").grid(row=0, column=0, sticky=tk.W)
        initial_file_entry = ttk.Entry(file_frame, textvariable=self.initial_file_var, width=30)
        initial_file_entry.grid(row=1, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        ttk.Button(file_frame, text="Browse...", command=lambda: self.browse_file(self.initial_file_var)).grid(row=1, column=1)
        row += 1
        
        # DB Path
        db_frame = ttk.Frame(main_frame)
        db_frame.grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        db_frame.columnconfigure(0, weight=1)
        ttk.Label(db_frame, text="Database Path:").grid(row=0, column=0, sticky=tk.W)
        db_path_entry = ttk.Entry(db_frame, textvariable=self.db_path_var, width=30)
        db_path_entry.grid(row=1, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        ttk.Button(db_frame, text="Browse...", command=lambda: self.browse_file(self.db_path_var, filetypes=[("Database files", "*.db"), ("All files", "*.*")])).grid(row=1, column=1)
        row += 1
        
        # CSV Path
        csv_frame = ttk.Frame(main_frame)
        csv_frame.grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        csv_frame.columnconfigure(0, weight=1)
        ttk.Label(csv_frame, text="CSV Path:").grid(row=0, column=0, sticky=tk.W)
        csv_path_entry = ttk.Entry(csv_frame, textvariable=self.csv_path_var, width=30)
        csv_path_entry.grid(row=1, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        ttk.Button(csv_frame, text="Browse...", command=lambda: self.browse_file(self.csv_path_var, filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])).grid(row=1, column=1)
        row += 1
        
        # Search Method
        ttk.Label(main_frame, text="Search Method:").grid(row=row, column=0, sticky=tk.W, pady=5)
        search_method_combo = ttk.Combobox(main_frame, textvariable=self.search_method_var, 
                                          values=["google_scholar", "semantic_scholar"], 
                                          state="readonly", width=20)
        search_method_combo.grid(row=row, column=1, sticky=tk.W, pady=5)
        row += 1
        
        # Annotations
        annotation_frame = ttk.LabelFrame(main_frame, text="Annotations", padding="5")
        annotation_frame.grid(row=row, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        annotation_frame.columnconfigure(0, weight=1)
        
        self.annotation_text = scrolledtext.ScrolledText(annotation_frame, height=4, width=40)
        self.annotation_text.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=2)
        ttk.Label(annotation_frame, text="Enter annotations, one per line:", 
                 font=('TkDefaultFont', 8)).grid(row=1, column=0, sticky=tk.W)
        row += 1
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=row, column=0, columnspan=2, pady=20)
        ttk.Button(button_frame, text="Generate Configuration", command=self.generate_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.root.quit).pack(side=tk.LEFT, padx=5)
        
        # Configure row weights for scrolling
        main_frame.rowconfigure(row, weight=1)
    
    def toggle_proxy_browse(self):
        """Enable/disable browse button based on checkbox"""
        if self.proxy_is_file_var.get():
            self.proxy_browse_btn.config(state="normal")
        else:
            self.proxy_browse_btn.config(state="disabled")
    
    def browse_file(self, var, filetypes=None):
        """Open file dialog to browse for a file"""
        if filetypes is None:
            filename = filedialog.askopenfilename()
        else:
            filename = filedialog.askopenfilename(filetypes=filetypes)
        if filename:
            var.set(filename)
    
    def validate_inputs(self) -> Tuple[bool, str]:
        """Validate all inputs and return (is_valid, error_message)"""
        # Validate years
        try:
            start_year = int(self.start_year_var.get())
            end_year = int(self.end_year_var.get())
            
            if start_year <= 0 or end_year <= 0:
                return False, "Years must be positive integers."
            if start_year >= end_year:
                return False, "Starting year must be less than ending year."
        except ValueError:
            return False, "Years must be valid integers."
        
        # Validate required fields
        if not self.initial_file_var.get().strip():
            return False, "Initial file is required."
        if not self.db_path_var.get().strip():
            return False, "Database path is required."
        if not self.csv_path_var.get().strip():
            return False, "CSV path is required."
        
        return True, ""
    
    def parse_venue_ranks(self) -> List[str]:
        """Parse venue ranks from text input"""
        text = self.venue_text.get("1.0", tk.END).strip()
        if not text:
            return []
        
        # Split by commas or newlines
        venues = []
        for line in text.split('\n'):
            venues.extend([v.strip() for v in line.split(',') if v.strip()])
        
        return venues
    
    def parse_annotations(self) -> List[str]:
        """Parse annotations from text input"""
        text = self.annotation_text.get("1.0", tk.END).strip()
        if not text:
            return []
        
        # One annotation per line
        return [line.strip() for line in text.split('\n') if line.strip()]
    
    def generate_config(self):
        """Generate the search configuration JSON file"""
        # Validate inputs
        is_valid, error_msg = self.validate_inputs()
        if not is_valid:
            messagebox.showerror("Validation Error", error_msg)
            return
        
        try:
            # Parse inputs
            start_year = int(self.start_year_var.get())
            end_year = int(self.end_year_var.get())
            venue_list = self.parse_venue_ranks()
            
            # Handle proxy key - either from file or direct input
            proxy_key_path = self.proxy_key_var.get().strip()
            if proxy_key_path:
                if self.proxy_is_file_var.get():
                    # Read proxy key from file
                    try:
                        with open(proxy_key_path, 'r', encoding='utf-8') as f:
                            proxy_key = f.read().strip()
                    except Exception as e:
                        messagebox.showerror("Error", f"Failed to read proxy key file: {str(e)}")
                        return
                else:
                    # Use direct proxy key
                    proxy_key = proxy_key_path
            else:
                proxy_key = ""
            
            initial_file = self.initial_file_var.get().strip()
            db_path = self.db_path_var.get().strip()
            csv_path = self.csv_path_var.get().strip()
            search_method = self.search_method_var.get()
            annotations = self.parse_annotations()
            
            # Create configuration dictionary
            search_conf = {
                "start_year": start_year,
                "end_year": end_year,
                "venue_rank_list": venue_list,
                "proxy_key": proxy_key,
                "initial_file": initial_file,
                "db_path": db_path,
                "csv_path": csv_path,
                "search_method": search_method,
                "annotations": annotations
            }

            # Save to file
            with open("search_conf.json", "w") as f:
                json.dump(search_conf, f, indent=4)
            
            messagebox.showinfo("Success", "Configuration saved to search_conf.json!")
            self.root.quit()
            
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred: {str(e)}")


def main():
    root = tk.Tk()
    app = SearchConfigGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()