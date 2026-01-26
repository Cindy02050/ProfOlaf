#!/usr/bin/env python3
"""
Filter articles by artifact verification.

This script:
1. Fetches articles without venues (arxiv, corr, openreview, etc.) that haven't passed metadata filtering
2. Downloads their PDFs
3. Extracts artifact links using verify_artifacts
4. Prompts user to accept/reject each article
5. Updates accepted articles in the database as passing metadata filtering
"""

import argparse
import os
import sys
import tempfile
import shutil
from pathlib import Path
from typing import List

# Add parent directory to path to import utils
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.db_management import DBManager, SelectionStage, ArticleData
from utils.article_processing.download_pdfs import download_pdf, is_valid_pdf
from utils.pipeline.verify_artifacts import (
    process_pdf,
    Config,
    UrlHit,
    DEFAULT_CONFIG,
)


def has_no_venue(venue: str) -> bool:
    """Check if article has no proper venue (arxiv, corr, ssrn, openreview, etc.)"""
    if not venue or venue.strip() == "":
        return True
    venue_lower = venue.lower()
    no_venue_keywords = ["arxiv", "corr", "ssrn", "openreview", "na"]
    return any(keyword in venue_lower for keyword in no_venue_keywords)


def get_articles_to_process(db_manager: DBManager, iteration: int) -> List[ArticleData]:
    """
    Get articles that:
    - Don't have a venue (arxiv, corr, openreview, etc.)
    - Haven't passed metadata filtering (selected = NOT_SELECTED)
    - Fulfill other metadata requirements (not filtered out by year/language/download)
    """
    # Get all articles in iteration that haven't been selected yet
    articles = db_manager.get_iteration_data(
        iteration=iteration,
        selected=SelectionStage.NOT_SELECTED
    )
    
    # Filter articles that:
    # 1. Have no venue (or venue is arxiv/corr/etc.)
    # 2. Haven't been filtered out by other metadata checks
    filtered_articles = []
    for article in articles:
        if not has_no_venue(article.venue):
            continue
        
        # Check if article was filtered out by other metadata checks
        if (article.year_filtered_out or 
            article.language_filtered_out or 
            article.download_filtered_out):
            continue
        
        # Must have a PDF URL to download
        if not article.eprint_url and not article.pub_url:
            continue
        
        filtered_articles.append(article)
    
    return filtered_articles


def download_article_pdfs(articles: List[ArticleData], temp_dir: Path) -> dict[str, Path]:
    """
    Download PDFs for articles to temporary directory.
    Returns dict mapping article_id -> pdf_path (or None if download failed)
    """
    pdf_paths = {}
    
    print(f"\nDownloading {len(articles)} PDFs to {temp_dir}...")
    for i, article in enumerate(articles, 1):
        print(f"[{i}/{len(articles)}] Downloading PDF for article {article.id}...")
        
        url = article.eprint_url or article.pub_url
        pdf_path = temp_dir / f"{article.id}.pdf"
        
        if pdf_path.exists() and is_valid_pdf(str(pdf_path)):
            print(f"  PDF already exists: {pdf_path}")
            pdf_paths[article.id] = pdf_path
            continue
        
        if download_pdf(url, str(pdf_path)):
            if is_valid_pdf(str(pdf_path)):
                print(f"  Successfully downloaded: {pdf_path}")
                pdf_paths[article.id] = pdf_path
            else:
                print(f"  Downloaded but invalid PDF: {pdf_path}")
                if pdf_path.exists():
                    pdf_path.unlink()
                pdf_paths[article.id] = None
        else:
            print(f"  Failed to download PDF from {url}")
            pdf_paths[article.id] = None
    
    return pdf_paths


def display_artifact_hits(article: ArticleData, hits: List[UrlHit]) -> None:
    """Display artifact links found in the PDF"""
    print("\n" + "="*80)
    print(f"Article ID: {article.id}")
    print(f"Title: {article.title}")
    print(f"Authors: {article.authors}")
    print(f"URL: {article.eprint_url or article.pub_url}")
    print("="*80)
    
    if not hits:
        print("\nNo artifact links found in this PDF.")
        return
    
    print(f"\nFound {len(hits)} artifact link(s):\n")
    
    # Group by URL to show unique URLs
    unique_urls = {}
    for hit in hits:
        if hit.url not in unique_urls:
            unique_urls[hit.url] = []
        unique_urls[hit.url].append(hit)
    
    for i, (url, url_hits) in enumerate(unique_urls.items(), 1):
        print(f"{i}. {url}")
        print(f"   Found on page(s): {', '.join(str(h.page_index + 1) for h in url_hits)}")
        print(f"   Reason(s): {', '.join(set(h.reason for h in url_hits))}")
        if url_hits[0].keyword:
            print(f"   Keyword: {url_hits[0].keyword}")
        if url_hits[0].context:
            context = url_hits[0].context[:200]  # Limit context length
            print(f"   Context: {context}...")
        print()


def prompt_user_decision(article: ArticleData) -> bool:
    """Prompt user whether to keep the article"""
    while True:
        response = input(f"\nKeep this article? (y/n/q to quit): ").strip().lower()
        if response == 'y':
            return True
        elif response == 'n':
            return False
        elif response == 'q':
            print("\nQuitting...")
            sys.exit(0)
        else:
            print("Please enter 'y' for yes, 'n' for no, or 'q' to quit.")


def main():
    parser = argparse.ArgumentParser(
        description="Filter articles by artifact verification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python filter_by_artifacts.py test.db 1
  python filter_by_artifacts.py /path/to/db.db 2 --config config.yml
        """
    )
    parser.add_argument(
        "db_path",
        help="Path to the database file"
    )
    parser.add_argument(
        "iteration",
        type=int,
        help="Current iteration number"
    )
    parser.add_argument(
        "--config",
        "-c",
        help="YAML config path for artifact detection (optional)"
    )
    parser.add_argument(
        "--dedup",
        action="store_true",
        help="Enable deduplication of identical URLs"
    )
    parser.add_argument(
        "--context-words",
        type=int,
        default=10,
        help="Number of words to include in context snippet (default: 10)"
    )
    
    args = parser.parse_args()
    
    # Validate database path
    if not os.path.exists(args.db_path):
        print(f"Error: Database file not found: {args.db_path}", file=sys.stderr)
        sys.exit(1)
    
    # Load config for artifact detection
    if args.config:
        from utils.pipeline.verify_artifacts import load_config
        cfg = load_config(args.config)
    else:
        cfg = Config.from_dict({})
    
    # Initialize database manager
    db_manager = DBManager(args.db_path)
    
    # Get articles to process
    print(f"Fetching articles for iteration {args.iteration}...")
    articles = get_articles_to_process(db_manager, args.iteration)
    
    if not articles:
        print(f"No articles found that match the criteria.")
        print("Articles must:")
        print("  - Have no venue (or venue is arxiv/corr/openreview/etc.)")
        print("  - Not have passed metadata filtering yet")
        print("  - Not be filtered out by year/language/download checks")
        print("  - Have a PDF URL available")
        sys.exit(0)
    
    print(f"Found {len(articles)} article(s) to process.\n")
    
    # Create temporary directory for PDFs
    temp_dir = Path(tempfile.mkdtemp(prefix="artifact_filter_"))
    print(f"Using temporary directory: {temp_dir}")
    
    try:
        # Download PDFs
        pdf_paths = download_article_pdfs(articles, temp_dir)
        
        # Process each article
        accepted_articles = []
        skipped_articles = []
        
        for i, article in enumerate(articles, 1):
            print(f"\n{'='*80}")
            print(f"Processing article {i}/{len(articles)}")
            print(f"{'='*80}")
            
            pdf_path = pdf_paths.get(article.id)
            
            if not pdf_path or not pdf_path.exists():
                print(f"\nSkipping article {article.id}: PDF not available")
                skipped_articles.append(article.id)
                continue
            
            # Process PDF to find artifact links
            try:
                print(f"\nAnalyzing PDF: {pdf_path}")
                hits = process_pdf(
                    pdf_path,
                    cfg,
                    dedup_enabled=args.dedup,
                    context_words=args.context_words,
                )
                
                # Display results
                display_artifact_hits(article, hits)
                
                # Prompt user
                if prompt_user_decision(article):
                    accepted_articles.append(article.id)
                    print(f"✓ Article {article.id} accepted")
                else:
                    print(f"✗ Article {article.id} rejected")
                    
            except Exception as e:
                print(f"\nError processing PDF for article {article.id}: {e}")
                print("Skipping this article...")
                skipped_articles.append(article.id)
                continue
        
        # Update database with accepted articles
        if accepted_articles:
            print(f"\n{'='*80}")
            print(f"Updating database: {len(accepted_articles)} article(s) accepted")
            print(f"{'='*80}")
            
            update_data = [
                (article_id, SelectionStage.METADATA_APPROVED.value, "selected")
                for article_id in accepted_articles
            ]
            
            db_manager.update_batch_iteration_data(args.iteration, update_data)
            print(f"\n✓ Successfully updated {len(accepted_articles)} article(s) in database")
        else:
            print("\nNo articles were accepted.")
        
        if skipped_articles:
            print(f"\nSkipped {len(skipped_articles)} article(s) due to download/processing errors")
        
    finally:
        # Clean up temporary directory
        print(f"\nCleaning up temporary directory: {temp_dir}")
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        print("Done.")


if __name__ == "__main__":
    main()

