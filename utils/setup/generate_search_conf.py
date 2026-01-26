import json
import os

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
            return csv_path

def generate_search_method():
    while True:
        print("Available search methods: google_scholar, semantic_scholar, dblp")
        search_method = input("Enter the search method: ")
        if search_method in ["google_scholar", "semantic_scholar", "dblp"]:
            return search_method
        else:
            print("Invalid search method. Please try again.")

def generate_annotations():
    annotations = []
    print("Enter annotations (one per line, empty line to finish):")
    while True:
        annotation = input()
        if annotation == "":
            break
        annotations.append(annotation.strip())
    return annotations

def main():
    print("Generating search configuration...")
    
    # Collect all inputs
    start_year, end_year = generate_year_interval()
    venue_list = generate_venue_rank()
    proxy_key = generate_proxy_key()
    initial_file = generate_initial_file()
    db_path = generate_db_path()
    csv_path = generate_csv_path()
    search_method = generate_search_method()
    annotations = generate_annotations()
    
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
    os.makedirs("confs", exist_ok=True)
    with open("confs/search_conf.json", "w") as f:
        json.dump(search_conf, f, indent=4)
    
    print("Configuration saved to confs/search_conf.json!")


if __name__ == "__main__":
    main()