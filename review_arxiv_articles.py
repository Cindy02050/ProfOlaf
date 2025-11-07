import argparse
import json
import re
import time
import sys
from scholarly import scholarly
from dotenv import load_dotenv
import hashlib

from tqdm import tqdm

from utils.proxy_generator import get_proxy
from utils.db_management import (
    DBManager, 
    SelectionStage
)
from utils.article_search_method import (
    ArticleSearch, 
    SearchMethod,
)


with open("search_conf.json", "r") as f:
    search_conf = json.load(f)

def parse_args():
    parser = argparse.ArgumentParser(description='Generate snowball sampling starting points from file')
    parser.add_argument('--iteration', help='iteration number', type=int, required=True)
    parser.add_argument('--db_path', help='db path', type=str, default=search_conf["db_path"])
    parser.add_argument('--verbose', action='store_true')  
    args = parser.parse_args()
    return args

def manual_validation(pubs):
    print(f"Found {len(pubs)} articles with arxiv as the venue")
    for i,pub in enumerate(pubs):
        print(f"Article {i+1}: {pub.title}")
        user_input = input("Is this article valid? (y/n): ")
        if user_input == 'n':
            continue
        elif user_input != 'y':
            print("Please enter 'y' for yes or 'n' for no. skipping...")
            continue
        else:
            user_input = input("Enter the title of the article for the search:")
            

def main():
    args = parse_args()
    db_manager = DBManager(args.db_path)
    initial_pubs = db_manager.get_iteration_data(
        iteration=args.iteration, 
        venue__like="%arxiv%"
    )
    manual_validation(initial_pubs)

if __name__ == "__main__":
    main()
    
