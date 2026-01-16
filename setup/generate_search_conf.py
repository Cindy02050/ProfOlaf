import json

from argparse import ArgumentParser

def generate_year_interval():
    while True:
        start_year = int(input("Enter the starting year: "))
        end_year = int(input("Enter the ending year: "))
        if start_year > end_year or start_year <= 0 or end_year <= 0:
            print("Starting year must be less than ending year. Please try again.")
        else:
            return start_year, end_year

def generate_venue_rank():
    venue_list = []
    while True:
        venue = input("Enter the accepted venue ranks (stops with empty input): ")
        if venue == "":
            break
        venue_list += venue.split(",")
    
    return [rank.strip() for rank in venue_list]

def generate_proxy_key():
    while True:
        proxy_key = input("Enter the proxy key (or the env variable name): ")
        if proxy_key == "":
            proxy_key = input("Proceed without proxy key? (y/n): ")
            if proxy_key == "y":
                return ""
            else:
                continue
        else:
            return proxy_key

def generate_initial_file():
    while True:
        initial_file = input("Enter the initial file: ")
        if initial_file == "":
            continue
        else:
            return initial_file

def generate_db_path():
    while True:
        db_path = input("Enter the db path: ")
        if db_path == "":
            continue
        else:
            return db_path

def generate_csv_path():
    while True:
        csv_path = input("Enter the path to the final csv file: ")
        if csv_path == "":
            continue
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