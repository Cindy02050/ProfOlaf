import argparse
import json
from dotenv import load_dotenv
from utils.db_management import (
    DBManager, 
    ArticleData,
    SelectionStage,
)
from utils.pipeline.get_bibtex import process_articles_optimized
from utils.article_search.article_search_method import SearchMethod

load_dotenv()
with open("confs/search_conf.json", "r") as f:
    search_conf = json.load(f)

def parse_args():
    parser = argparse.ArgumentParser(description='Get bibtex for articles')
    parser.add_argument('--iteration', help='iteration number', type=int)
    parser.add_argument('--db_path', help='db path', type=str, default=search_conf["db_path"])
    parser.add_argument('--batch_size', help='batch size for processing', type=int, default=1)
    parser.add_argument('--max_workers', help='max workers for parallel processing', type=int, default=3)
    parser.add_argument('--parallel', help='disable parallel processing', action='store_true')
    parser.add_argument('--delay', help='delay between requests', type=float, default=1.0)
    parser.add_argument(
        '--search_method', 
        help='Search method to use', 
        type=str, 
        default=search_conf["search_method"],
        choices=[method.value for method in SearchMethod]
    )
    args = parser.parse_args()
    return args

if __name__ == "__main__":
    args = parse_args()

    db_manager = DBManager(args.db_path)
    articles = db_manager.get_iteration_data(
        iteration=args.iteration, 
        bibtex__empty=True,
        selected=SelectionStage.NOT_SELECTED
    )
    
    print(f"Found {len(articles)} articles without bibtex in iteration {args.iteration}")
    
    # Use optimized processing
    process_articles_optimized(
        iteration=args.iteration,
        articles=articles,
        db_manager=db_manager,
        batch_size=args.batch_size,
        max_workers=args.max_workers,
        use_parallel=args.parallel,
        search_method=args.search_method,
        delay=args.delay
    )
    
    print("Processing completed!")
