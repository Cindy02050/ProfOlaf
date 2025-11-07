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
    SemanticScholarSearchMethod,
)

with open("search_conf.json", "r") as f:
    search_conf = json.load(f)

def parse_args():
    parser = argparse.ArgumentParser(description='Generate snowball sampling starting points from file')
    parser.add_argument('--iteration', help='iteration number', type=int, required=True)
    parser.add_argument('--db_path', help='db path', type=str, default=search_conf["db_path"])
    parser.add_argument('--verbose', action='store_true')  
    #parser.add_argument("--search_method", type=str, default="semantic_scholar", choices=[method.value for method in SearchMethod])
    args = parser.parse_args()
    return args

def is_valid_bibtex(bibtex):
    return bibtex is not None and bibtex != ""

def search_for_articles(article_titles):
    semantic_scholar_search = SemanticScholarSearchMethod()
    google_scholar_search = GoogleScholarSearchMethod()
    articles_to_update = []
    articles_not_found = []
    for article_id, article_title in article_titles:
        article = semantic_scholar_search.search(article_title)
        if is_valid_bibtex(article.bibtex):
            articles.append(article_id, article)
            continue
        article = google_scholar_search.search(article_title)
        if is_valid_bibtex(article.bibtex):
            articles.append(article_id, article)
            continue
        articles_not_found.append(article_id)

    return articles_to_update, articles_not_found

def manual_validation(pubs):
    articles_to_delete = []
    article_titles = []
    articles_to_update = []
    print(f"Found {len(pubs)} articles with no bibtex")
    for i,pub in enumerate(pubs):
        print(f"Article {i+1}: {pub.title}")
        user_input = input("Is this article valid? (y/n): ")
        if user_input == 'n':
            articles_to_delete.append(pub.id)
            continue
        elif user_input != 'y':
            print("Please enter 'y' for yes or 'n' for no. skipping...")
            continue
        else:
            user_input = input("Enter the title of the article:")
            article_titles.append((pub.id, user_input))

    articles_to_update, articles_not_found = search_for_articles(article_titles) 
    for article_id, article in articles_to_update:
        db_manager.delete_batch_iteration_data(args.iteration, article_id)
        db_manager.add_iteration_data(args.iteration, article)
    for article_id in articles_not_found:
        db_manager.delete_batch_iteration_data(args.iteration, article_id)
    db_manager.delete_batch_iteration_data(args.iteration, articles_to_delete)

def main():
    args = parse_args()
    db_manager = DBManager(args.db_path)
    initial_pubs = db_manager.get_iteration_data(
        iteration=args.iteration, 
        bibtex="NO_BIBTEX"
    )

    manual_validation(initial_pubs)

if __name__ == "__main__":
    main()
    
