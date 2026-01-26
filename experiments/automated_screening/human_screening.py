import json
import sys
import os
import argparse

def parse_args():
    parser = argparse.ArgumentParser(description="Screen articles from a JSONL file")
    parser.add_argument("input_file", type=str, help="Path to input JSONL file")
    parser.add_argument("output_file", type=str, help="Path to output JSONL file")
    return parser.parse_args()

def screen_articles(input_file, output_file=None):

    if not os.path.exists(input_file):
        print(f"Error: File '{input_file}' not found.")
        sys.exit(1)
    
    if output_file is None:
        base_name = os.path.splitext(input_file)[0]
        ext = os.path.splitext(input_file)[1]
        output_file = f"{base_name}_screened{ext}"
    
    articles = []
    with open(input_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if line:
                try:
                    article = json.loads(line)
                    articles.append(article)
                except json.JSONDecodeError as e:
                    print(f"Warning: Skipping invalid JSON on line {line_num}: {e}")
                    continue
    
    print(f"\nLoaded {len(articles)} articles from '{input_file}'")
    print(f"Output will be written to '{output_file}'\n")
    print("=" * 80)
    
    screened_articles = []
    for idx, article in enumerate(articles, 1):
        title = article.get('title', 'N/A')
        pub_url = article.get('pub_url', 'N/A')
        iteration = article.get('iteration', 'N/A')
        
        print(f"\n[{idx}/{len(articles)}]")
        print(f"Title: {title}")
        print(f"URL: {pub_url}")
        print(f"Iteration: {iteration}")
        print("-" * 80)
        
        while True:
            response = input("Keep this paper? (y/n/q to quit): ").strip().lower()
            if response == 'q':
                print("\nQuitting early. Saving progress...")
                break
            elif response in ['y', 'yes']:
                article['keep'] = True
                screened_articles.append(article)
                print("✓ Kept\n")
                break
            elif response in ['n', 'no']:
                article['keep'] = False
                screened_articles.append(article)
                print("✗ Not kept\n")
                break
            else:
                print("Please enter 'y' for yes, 'n' for no, or 'q' to quit.")
        
        if response == 'q':
            break
    
    # Write screened articles to output file
    with open(output_file, 'w', encoding='utf-8') as f:
        for article in screened_articles:
            f.write(json.dumps(article, ensure_ascii=False) + '\n')
    
    print(f"\n{'=' * 80}")
    print(f"Screening complete!")
    print(f"Total articles screened: {len(screened_articles)}")
    print(f"Kept: {sum(1 for a in screened_articles if a.get('keep', False))}")
    print(f"Not kept: {sum(1 for a in screened_articles if not a.get('keep', False))}")
    print(f"Results written to: {output_file}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python screen_articles.py <input_jsonl_file> [output_jsonl_file]")
        print("\nExample:")
        print("  python screen_articles.py articles.jsonl")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    screen_articles(input_file, output_file)
