import requests
import bibtexparser
from typing import List, Tuple
from ..db_management import DBManager, ArticleData
from ..article_search.article_search_method import (
    ArticleSearch, 
    SearchMethod, 
    GoogleScholarSearchMethod, 
    SemanticScholarSearchMethod, 
    DBLPSearchMethod,
)

from tqdm import tqdm
import sys
import time
import concurrent.futures

DBLP_URL = "https://dblp.org/search/publ/api?q={query}&format=json"

def check_valid_venue(venue: str):
    return venue != "" and all(
        venue.lower() not in invalid_venue 
        for invalid_venue in ["arxiv", "corr", "no title"]
    )

def parse_bibtex(bibtex: str):
    if bibtex != "":
        library = bibtexparser.loads(bibtex)
        if not library.entries:
            return ""
        return library.entries[0]

def get_bibtex_venue(bibtex: str):
    library_entries = parse_bibtex(bibtex)
    if library_entries == "" or library_entries["ENTRYTYPE"] in ["book", "phdthesis", "mastersthesis"]:
        return ""
    elif "booktitle" in library_entries:
        return library_entries["booktitle"]
    elif "journal" in library_entries:
        return library_entries["journal"]
    return ""

def get_bibtex_year(bibtex: str):
    library_entries = parse_bibtex(bibtex)
    if library_entries == "" or not "year" in library_entries:
        return ""
    return library_entries["year"]

def search_bibtex_in_dblp(title: str):
    dblp_url = DBLP_URL.format(query=title)
    response = requests.get(dblp_url)
    data = response.json()
    if data.get("result", {}).get("hits", {}).get("hit", []) != []:
        for hit in data["result"]["hits"]["hit"]:
            if hit["info"]["venue"] and check_valid_venue(hit["info"]["venue"]):
                return hit["info"]
    return ""

def cache_by_title(func):
    cache = {}
    def wrapper(pub):
        title = pub.get("bib", {}).get("title", "")
        if title and title not in cache:
            cache[title] = func(pub)
        return cache.get(title, "")
    return wrapper

@cache_by_title
def get_alternative_bibtexes_cached(pub):
    """
    Cached version of get_alternative_bibtexes to avoid repeated API calls.
    Uses pub as cache key.
    """

    article_search = ArticleSearch(GoogleScholarSearchMethod())
    versions = article_search.get_all_versions_bibtexes(pub)
    for version in versions:
        venue = get_bibtex_venue(version)
        if check_valid_venue(venue):
            return version
    return ""

def _get_main_bibtex(article: ArticleData) -> Tuple[str, str]:
    current_wait_time = 20
    max_retries = 3
    retry_count = 0

    article_search = ArticleSearch(GoogleScholarSearchMethod())
    while retry_count < max_retries:
        try:
            article_search.set_method(GoogleScholarSearchMethod())
            pub = scholarly.search_single_pub(article.title)
            bibtex = article_search.get_bibtex(pub)
            venue = get_bibtex_venue(bibtex)
            if venue and check_valid_venue(venue):
                return bibtex, None
            else:
                return bibtex, pub
        except Exception as e:
            title = article.title
            print(f"Error processing {title}: {e}")
            retry_count += 1
            print(f"Retrying, waiting {current_wait_time}...", file=sys.stderr)
            sys.stdout.flush()
            time.sleep(current_wait_time)
            current_wait_time *= 2
            continue
    return None, None

def _get_dblp_bibtex(article: ArticleData) -> Tuple[str, str]:
    article_search = ArticleSearch(DBLPSearchMethod())
    current_wait_time = 20
    max_retries = 3
    retry_count = 0
    while retry_count < max_retries:
        try:
            bibtex = article_search.get_bibtex(article)
            if bibtex and get_bibtex_venue(bibtex) and check_valid_venue(get_bibtex_venue(bibtex)):
                return bibtex
            else:
                return bibtex
        except Exception as e:
            title = article.title
            print(f"Error processing {title}: {e}")
            retry_count += 1
            print(f"Retrying, waiting {current_wait_time}...", file=sys.stderr)
            sys.stdout.flush()
            time.sleep(current_wait_time)
            current_wait_time *= 2
            continue

    return None

def _get_alternative_bibtex(pub: dict) -> Tuple[str, str]:
    current_wait_time = 20
    max_retries = 3
    retry_count = 0
    while retry_count < max_retries:
        try:
            bibtex = get_alternative_bibtexes_cached(pub)
            if bibtex is not None and bibtex != "":
                return bibtex
            else:
                return None
        except Exception as e:
            title = pub.get('title', "")
            print(f"Error processing {title}: {e}")
            retry_count += 1
            print(f"Retrying, waiting {current_wait_time}...", file=sys.stderr)
            sys.stdout.flush()
            time.sleep(current_wait_time)
            current_wait_time *= 2
            continue
        
    return None

def get_bibtex_single(article: ArticleData, search_method: SearchMethod = SearchMethod.GOOGLE_SCHOLAR, delay_between_requests: float = 1.0) -> Tuple[str, str]:
    """
    Get the bibtex string for a single article.
    Returns (article_id, bibtex_string)
    """

    time.sleep(delay_between_requests)
    if search_method == SearchMethod.SEMANTIC_SCHOLAR.value:
        article_search = ArticleSearch(SemanticScholarSearchMethod())
        bibtex = article_search.get_bibtex(article)
        if bibtex is not None and bibtex != "":
            return article.id, bibtex
        else:
            return article.id, "NO_BIBTEX"


    dblp_bibtex = _get_dblp_bibtex(article)
    if dblp_bibtex is not None and dblp_bibtex != "":
        return article.id, dblp_bibtex
    
    scholar_bibtex, pub = _get_main_bibtex(article)
    if scholar_bibtex is not None and scholar_bibtex != "" and pub is None:
        return article.id, scholar_bibtex

    if pub is not None:
        alternative_bibtex = _get_alternative_bibtex(pub)
        if alternative_bibtex is not None and alternative_bibtex != "":
            return article.id, alternative_bibtex
        
    if pub is not None and scholar_bibtex is not None and scholar_bibtex != "":
        return article.id, scholar_bibtex
    else:
        print("No bibtex found")
        return article.id, "NO_BIBTEX"

def process_articles_batch(articles: List[ArticleData], max_workers: int = 3, search_method: SearchMethod = SearchMethod.GOOGLE_SCHOLAR, delay: float = 1.0, cancel_flag=None) -> List[Tuple[str, str]]:
    """
    Process multiple articles in parallel.
    Returns list of (article_id, bibtex_string) tuples.
    """
    results = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_article = {
            executor.submit(get_bibtex_single, article, search_method, delay): article 
            for article in articles
        }
        
        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_article):
            # Check for cancellation
            if cancel_flag and cancel_flag.is_set():
                # Cancel remaining futures
                for f in future_to_article:
                    f.cancel()
                print("Batch processing cancelled.")
                break
            
            article = future_to_article[future]
            try:
                result = future.result(timeout=300)  # 5 minute timeout per article
                # Ensure result is not None and is a tuple
                if result is None:
                    result = (article.id, "")
                elif not isinstance(result, tuple) or len(result) != 2:
                    result = (article.id, "")
                
                results.append(result)
            except concurrent.futures.TimeoutError:
                print(f"Timeout processing article: {article.title}")
                results.append((article.id, ""))
            except Exception as e:
                print(f"Error processing article {article.id}: {e}")
                results.append((article.id, ""))
    
    return results

def update_bibtex_info(iteration: int, results: List[Tuple[str, str, str]], db_manager: DBManager):
    venue_updates = []
    year_updates = []
    for article_id, bibtex, _ in results:
        venue = get_bibtex_venue(bibtex)
        year = get_bibtex_year(bibtex)
        venue_updates.append((article_id, venue, "venue"))
        year_updates.append((article_id, year, "pub_year"))
    db_manager.update_batch_iteration_data(iteration, results)
    db_manager.update_batch_iteration_data(iteration, venue_updates)
    db_manager.update_batch_iteration_data(iteration, year_updates)

def process_articles_optimized(iteration: int, articles: List[ArticleData], db_manager: DBManager,
                              batch_size: int = 10, max_workers: int = 3, 
                              use_parallel: bool = True, search_method: SearchMethod = SearchMethod.GOOGLE_SCHOLAR, delay: float = 1.0,
                              cancel_flag=None) -> None:
    """
    Optimized processing of articles with batch updates and optional parallel processing.
    """
    # Filter articles that need processing
    articles_to_process = [a for a in articles if a.bibtex == "" and a.title != ""]
    
    if not articles_to_process:
        print("No articles need processing.")
        return
    
    print(f"Processing {len(articles_to_process)} articles...")
    
    if use_parallel and len(articles_to_process) > 1:
        print(f"Using parallel processing with {max_workers} workers...")
        # Process in batches to avoid overwhelming the API
        for i in tqdm(range(0, len(articles_to_process), batch_size), desc="Getting bibtex for articles (parallel)"):
            # Check for cancellation
            if cancel_flag and cancel_flag.is_set():
                print("Processing cancelled by user.")
                return
            
            batch = articles_to_process[i:i + batch_size]
            
            results = process_articles_batch(batch, max_workers, search_method, delay, cancel_flag)
            
            # Check again after batch processing
            if cancel_flag and cancel_flag.is_set():
                print("Processing cancelled by user.")
                return
            
            if results is None:
                print(f"Warning: process_articles_batch returned None for batch {i//batch_size + 1}")
                results = []
            
            # Convert results to format expected by update_bibtex_info: (article_id, bibtex, dummy)
            results_for_update = [(article_id, bibtex, "") for article_id, bibtex in results]
            update_bibtex_info(iteration, results_for_update, db_manager)
            print(f"Batch {i//batch_size + 1} completed and saved to database.")
    else:
        print("Using sequential processing...")
        results = []
        desc = f"Getting bibtex for articles (sequential with batch size {batch_size})"
        for i, article in tqdm(enumerate(articles_to_process), desc=desc):
            # Check for cancellation before processing each article
            if cancel_flag and cancel_flag.is_set():
                print("Processing cancelled by user.")
                # Save any remaining results before exiting
                if results:
                    update_bibtex_info(iteration, results, db_manager)
                return
            
            article_id, bibtex = get_bibtex_single(article, search_method, delay_between_requests=delay)
            results.append((article_id, bibtex, "bibtex"))
            if len(results) >= batch_size or i == len(articles_to_process) - 1:
                update_bibtex_info(iteration, results, db_manager)
                results = []
