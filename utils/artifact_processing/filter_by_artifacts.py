import os
import json
import argparse
from pathlib import Path
from typing import List
from verify_artifacts import process_pdf, Config, UrlHit
from ..db_management import DBManager, SelectionStage, ArticleData
from ..article_processing.download_pdfs import download_pdf, is_valid_pdf


# Load search_conf
try:
    with open("confs/search_conf.json", "r") as f:
        search_conf = json.load(f)
except FileNotFoundError:
    search_conf = {"db_path": "databases/database.db"}

def parse_args():
    parser = argparse.ArgumentParser(description='Filter by artifacts')
    parser.add_argument('--iteration', help='iteration number', type=int, required=True)
    parser.add_argument('--db_path', help='db path', type=str, default=search_conf.get("db_path", "databases/database.db"))
    parser.add_argument('--articles', help='folder containing the articles to examine', type=str, required=True)
    args = parser.parse_args()
    return args

def not_peer_reviewed_venue(article: ArticleData) -> bool:
    """ This method should check if the article has a venue and if the venue is not peer reviewed.
    If not, it should return True.
    """
    venue_lower = article.venue.lower() if article.venue else ""
    return not article.venue or venue_lower in ["arxiv", "corr", "openreview"]

def download_pdfs(articles: List[ArticleData], folder: str) -> List[ArticleData]:
    """ This method should download the pdfs for the articles.
    """
    failed_downloads = []
    for article in articles:
        pdf_path = f"{folder}/{article.id}.pdf"
        if not not_peer_reviewed_venue(article) or is_valid_pdf(pdf_path):
            continue
        if download_pdf(article.eprint_url, pdf_path) and is_valid_pdf(pdf_path):
            continue
        else:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
            failed_downloads.append(article)
    
    for failed_download in failed_downloads:
        while True:
            response = input(f"Failed to download {failed_download.id}.pdf ({failed_download.title}) from {failed_download.eprint_url}. "
                           f"Please manually download the pdf and save it as {folder}/{failed_download.id}.pdf. "
                           f"Then press Enter to continue...")
            if is_valid_pdf(f"{folder}/{failed_download.id}.pdf"):
                break
            else:
                continue
    
    return failed_downloads

def display_artifact_hits(article: ArticleData, hits: List[UrlHit]) -> None:
    """Display artifact URLs found in the PDF to the user."""
    print(f"\n{'='*80}")
    print(f"Article: {article.title}")
    print(f"ID: {article.id}")
    print(f"Authors: {article.authors}")
    print(f"Venue: {article.venue if article.venue else 'N/A'}")
    print(f"{'='*80}")
    
    if not hits:
        print("No artifact URLs found in this PDF.")
        return
    
    print(f"\nFound {len(hits)} potential artifact URL(s):\n")
    
    # Group hits by URL to avoid duplicates
    unique_urls = {}
    for hit in hits:
        if hit.url not in unique_urls:
            unique_urls[hit.url] = []
        unique_urls[hit.url].append(hit)
    
    for idx, (url, url_hits) in enumerate(unique_urls.items(), 1):
        print(f"{idx}. {url}")
        print(f"   Found on page {url_hits[0].page_index + 1}")
        if url_hits[0].keyword:
            print(f"   Keyword: {url_hits[0].keyword}")
        print(f"   Reason: {url_hits[0].reason}")
        if url_hits[0].context:
            context_preview = url_hits[0].context[:200] + "..." if len(url_hits[0].context) > 200 else url_hits[0].context
            print(f"   Context: {context_preview}")
        print()

def ask_user_decision(article: ArticleData) -> str:
    """Ask user if the article should be kept based on artifacts found."""
    while True:
        response = input("Does this article provide artifacts/replication packages? (y/n/s for skip): ").lower().strip()
        if response in ['y', 'yes']:
            return 'keep'
        elif response in ['n', 'no']:
            return 'reject'
        elif response in ['s', 'skip']:
            return 'skip'
        else:
            print("Please enter 'y' for yes, 'n' for no, or 's' for skip.")

def filter_artifacts(db_manager: DBManager, iteration: int, articles_folder: str):
    """ This method should iterate over the articles in the database that need artifact checking and check the corresponding
    pdfs for possible artifact/replication packages links. If found, it should show the user the links and ask them to confirm if the article should be kept.
    
    article pdf name format: {article_id}.pdf
    articles to check: articles that passed the metadata filtering step but do not have a venue or the venue is arxiv, corr, openreview.
    """
    # Get articles that passed metadata filtering or title screening (but not content screening yet)
    metadata_articles = db_manager.get_iteration_data(
        iteration=iteration,
        selected=SelectionStage.METADATA_APPROVED,
    )
    
    # Combine and deduplicate by ID
    all_articles_dict = {}
    for article in metadata_articles:
        all_articles_dict[article.id] = article
    for article in title_articles:
        if article.id not in all_articles_dict:
            all_articles_dict[article.id] = article
    
    all_articles = list(all_articles_dict.values())
    
    # Filter articles that need artifact checking (no venue or non-peer-reviewed venue)
    articles_to_check = [article for article in all_articles if not_peer_reviewed_venue(article)]
    
    print(f"Found {len(articles_to_check)} articles to check for artifacts.")
    print(f"Articles folder: {articles_folder}\n")
    
    # Download PDFs for articles that need checking
    print("Downloading PDFs...")
    download_pdfs(articles_to_check, folder=articles_folder)
    
    # Process each article's PDF
    cfg = Config.from_dict({})  # Use default config
    kept_count = 0
    rejected_count = 0
    skipped_count = 0
    
    for article in articles_to_check:
        pdf_path = Path(articles_folder) / f"{article.id}.pdf"
        
        if not pdf_path.exists() or not is_valid_pdf(str(pdf_path)):
            print(f"\nSkipping {article.id}: PDF not found or invalid")
            skipped_count += 1
            continue
        
        print(f"\nProcessing: {article.id} - {article.title[:60]}...")
        
        try:
            # Find artifact URLs in PDF
            hits = process_pdf(pdf_path, cfg, dedup_enabled=True, context_words=10)
            
            # Display results to user
            display_artifact_hits(article, hits)
            
            # Ask user for decision
            decision = ask_user_decision(article)
            
            if decision == 'keep':
                # Keep the article - advance to TITLE_APPROVED if not already there
                current_stage = SelectionStage(int(article.selected)) if article.selected is not None else SelectionStage.NOT_SELECTED
                if current_stage.value < SelectionStage.TITLE_APPROVED.value:
                    db_manager.update_iteration_data(
                        iteration=iteration,
                        article_id=article.id,
                        selected=SelectionStage.TITLE_APPROVED
                    )
                kept_count += 1
                print(f"✓ Article {article.id} kept (has artifacts).")
            elif decision == 'reject':
                # Reject the article - mark as not selected
                db_manager.update_iteration_data(
                    iteration=iteration,
                    article_id=article.id,
                    selected=SelectionStage.NOT_SELECTED
                )
                rejected_count += 1
                print(f"✗ Article {article.id} rejected (no artifacts).")
            else:  # skip
                skipped_count += 1
                print(f"⊘ Article {article.id} skipped.")
        
        except Exception as e:
            print(f"Error processing {article.id}: {e}")
            skipped_count += 1
            continue
    
    # Summary
    print(f"\n{'='*80}")
    print("Summary:")
    print(f"  Kept: {kept_count}")
    print(f"  Rejected: {rejected_count}")
    print(f"  Skipped: {skipped_count}")
    print(f"  Total processed: {kept_count + rejected_count + skipped_count}")
    print(f"{'='*80}")

def main():
    args = parse_args()
    db_manager = DBManager(args.db_path)
    filter_artifacts(
        db_manager, 
        args.iteration, 
        args.articles
    )

if __name__ == "__main__":
    main()