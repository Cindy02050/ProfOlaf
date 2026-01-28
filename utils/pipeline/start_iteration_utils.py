from tqdm import tqdm
import sys

from ..db_management import DBManager
from ..article_search.article_search_method import ArticleSearch, SemanticScholarSearchMethod, GoogleScholarSearchMethod, DBLPSearchMethod


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

def repair_references(iteration: int, db_manager: DBManager, verbose: bool = False):
    """ Repair broken references for the given iteration """
    articles = db_manager.get_iteration_data(iteration=iteration, id__empty=True)
    semantic_scholar_search = SemanticScholarSearchMethod()
    google_scholar_search = GoogleScholarSearchMethod()
    dblp_search = DBLPSearchMethod()
    search_methods = [semantic_scholar_search, google_scholar_search, dblp_search]
    for article in articles:
        confirmation = input(f"Is this an article {article.title}? (y/n):")
        if confirmation == "y":
            title = input(f"Enter the title of the article (leave empty to use the current title):")
            title = title.strip() if title.strip() != "" else article.title
            article.title = title  # Update title if changed
            for search_method in search_methods:
                found_article = search_method.search(title)
                if found_article:
                    article.id = found_article.id
                    break
            if article.id is None or article.id == "":
                print(f"No article found for {title}")
                continue
            db_manager.insert_iteration_data([article])
            # Update seen_titles table to link title to new ID
            db_manager.insert_seen_titles_data([(article.title.lower(), article.id)])
            
            # Delete the old entry (with empty ID)
            db_manager.cursor.execute(
                "DELETE FROM iterations WHERE id = ? AND iteration = ? AND title = ?",
                ('', iteration, article.title)
            )
            db_manager.conn.commit()

    db_manager.clear_unidentified_articles(iteration)