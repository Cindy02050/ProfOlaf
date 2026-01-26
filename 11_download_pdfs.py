import os
import argparse
import csv
import time
import pathlib
import sys

from utils.article_processing.download_pdfs import download_pdf, is_valid_pdf


def main():
    parser = argparse.ArgumentParser(description='Download PDFs')
    parser.add_argument('--csv_file', help='CSV file', type=str, default=search_conf["csv_path"])
    parser.add_argument('--article_folder', help='Output folder', type=str, default=analysis_conf["articles_folder"])
    args = parser.parse_args()
    csv_file = args.csv_file
    output_folder = args.article_folder
    
    if not os.path.exists(csv_file):
        print(f"CSV file not found: {csv_file}")
        sys.exit(1)
    
    pathlib.Path(output_folder).mkdir(parents=True, exist_ok=True)
    
    failed_downloads = []
    print(f"Downloading PDFs from {csv_file} to {output_folder}")
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)      

        for row in reader:
            article_id = row.get('title', '').strip()
            eprint_url = row.get('url', '').strip()
            
            if not eprint_url:
                continue
            
            article_id = article_id.replace(" ", "_").replace(":", "_").replace("/", "_").replace("\\", "_").replace("*", "_").replace("?", "_").replace("\"", "_").replace("<", "_").replace(">", "_").replace(".", "_")
            output_file = os.path.join(output_folder, f"{article_id}.pdf")
            
            if os.path.exists(output_file):
                print(f"File already exists: {output_file}")
                continue
            
            print(f"Downloading {article_id}.pdf from {eprint_url}")
            
            if download_pdf(eprint_url, output_file):
                if is_valid_pdf(output_file):
                    print(f"Successfully downloaded and verified: {output_file}")
                    time.sleep(1)
                else:
                    print(f"Downloaded but invalid PDF: {output_file}")
                    os.remove(output_file)
                    failed_downloads.append((article_id, eprint_url))
            else:
                failed_downloads.append((article_id, eprint_url))
    
    if failed_downloads:
        print("\nFailed downloads:")
        for article_id, url in failed_downloads:
            print(f"\nID {article_id}: {url}")
            print(f"Please manually download and save as: {output_folder}/{article_id}.pdf")
            
            while True:
                response = input("Have you completed the download? (y/n): ").lower().strip()
                if response in ['y', 'yes']:
                    file_path = os.path.join(output_folder, f"{article_id}.pdf")
                    if os.path.exists(file_path) and is_valid_pdf(file_path):
                        print(f"✓ File {article_id}.pdf verified successfully!")
                        break
                    else:
                        if os.path.exists(file_path):
                            print(f"✗ File {article_id}.pdf exists but is not a valid PDF. Please ensure it's a valid PDF file.")
                        else:
                            print(f"✗ File {article_id}.pdf not found. Please ensure it's saved correctly.")
                        continue
                elif response in ['n', 'no']:
                    print("Please complete the download and try again.")
                    continue
                else:
                    print("Please answer with 'y' or 'n'.")
    
    print(f"\nDownload complete. Files saved to: {output_folder}")

if __name__ == "__main__":
    main()