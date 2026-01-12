from tqdm import tqdm
import sys

from ..db_management import DBManager
from ..article_search.article_search_method import ArticleSearch


def get_articles(iteration: int, initial_pubs, db_manager: DBManager, article_search: ArticleSearch, verbose: bool = False):
    """
    Get articles that cite the pubs for the given iteration.
    """
    
    for initial_pub in tqdm(initial_pubs, desc="Getting articles from snowballing..."):
        citedby = initial_pub.id
        
        articles = article_search.get_snowballing_articles(citedby, iteration=iteration, backwards=True, forwards=True)
        if len(articles) == 0:
            continue
        
        if verbose:
            print("Citedby: ", citedby, "Total Results: ", len(articles))

        sys.stdout.flush()

        filtered_articles = [article for article in articles if db_manager.get_seen_title(article.title) is None]
        if verbose:
            print(f"Found {len(filtered_articles)} new articles from {initial_pub.title}")

        db_manager.insert_iteration_data(filtered_articles)
        db_manager.insert_seen_titles_data([(article.title, article.id) for article in filtered_articles])
    
    sys.stdout.flush()