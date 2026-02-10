#!/usr/bin/env python3

import csv
import os
import sys
import re
import pathlib
from urllib.parse import urljoin, urlparse
import requests
import time
import argparse
import json

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _extract_semantic_scholar_paper_id(url: str) -> str | None:
    """Extract paper ID from Semantic Scholar URL."""
    # Pattern: https://www.semanticscholar.org/paper/{paper_id}
    # or https://www.semanticscholar.org/paper/{title}-{paper_id}
    # Paper IDs are typically 40-character hex strings
    # Try to match the ID at the end of /paper/ path
    match = re.search(r'/paper/([a-f0-9]{40})(?:[?/#]|$)', url, re.I)
    if match:
        return match.group(1)
    # Also try to match if there's text before the ID (title-slug format)
    match = re.search(r'/paper/[^/]+-([a-f0-9]{40})(?:[?/#]|$)', url, re.I)
    if match:
        return match.group(1)
    return None


def _get_semantic_scholar_pdf_url(paper_id: str) -> str | None:
    """Try to get PDF URL from Semantic Scholar API."""
    try:
        api_url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}?fields=openAccessPdf,externalIds"
        response = requests.get(api_url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # Try openAccessPdf first
            if data.get("openAccessPdf") and data["openAccessPdf"].get("url"):
                return data["openAccessPdf"]["url"]
            # Try arXiv if available
            if data.get("externalIds") and data["externalIds"].get("ArXiv"):
                arxiv_id = data["externalIds"]["ArXiv"]
                return f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    except Exception as e:
        print(f"  Semantic Scholar API lookup failed: {e}")
    return None


def _extract_pdf_url_from_semantic_scholar(html: str, base_url: str) -> str | None:
    """Extract PDF URL from Semantic Scholar page HTML."""
    # Look for direct PDF links in various formats
    patterns = [
        # Direct PDF links
        r'href=["\']([^"\']*\.pdf[^"\']*)["\']',
        # Links with "pdf" in the text or class
        r'<a[^>]*class=["\'][^"\']*pdf[^"\']*["\'][^>]*href=["\']([^"\']+)["\']',
        # Data attributes
        r'data-pdf-url=["\']([^"\']+)["\']',
        # External PDF sources (arXiv, publisher sites)
        r'(https?://(?:arxiv\.org|.*\.edu|.*\.org)/[^"\'>\s]+\.pdf)',
        # Semantic Scholar reader/viewer links
        r'href=["\']([^"\']*semanticscholar\.org/[^"\']*(?:reader|pdf|viewer)[^"\']*)["\']',
    ]
    
    for pattern in patterns:
        matches = re.finditer(pattern, html, re.I)
        for match in matches:
            url = match.group(1) if match.groups() else match.group(0)
            if url and ('.pdf' in url.lower() or 'pdf' in url.lower() or 'reader' in url.lower()):
                full_url = urljoin(base_url, url)
                # Skip if it's still a Semantic Scholar page URL (not a direct PDF)
                if full_url.endswith('.pdf') or 'arxiv.org/pdf' in full_url:
                    return full_url
    
    # Look for arXiv links
    arxiv_match = re.search(r'(https?://arxiv\.org/(?:abs|pdf)/[a-z-]+/\d+(?:v\d+)?)', html, re.I)
    if arxiv_match:
        arxiv_url = arxiv_match.group(1)
        # Convert /abs/ to /pdf/
        if '/abs/' in arxiv_url:
            return arxiv_url.replace('/abs/', '/pdf/') + '.pdf'
        return arxiv_url
    
    # Look for DOI links that might lead to PDFs
    doi_match = re.search(r'https?://(?:dx\.)?doi\.org/([^"\'>\s]+)', html, re.I)
    if doi_match:
        # Could try to resolve DOI, but that's complex - return None for now
        pass
    
    return None


def _looks_like_pdf(headers: dict, first_bytes: bytes) -> bool:
    ctype = headers.get("Content-Type", "").split(";")[0].strip().lower()
    return (ctype == "application/pdf") or first_bytes.startswith(b"%PDF")

def _extract_pdf_url(html: str, base_url: str) -> str | None:
    m = re.search(r'<meta[^>]+http-equiv=["\']?refresh["\']?[^>]+content=["\'][^"\']*url=([^"\'>]+)', html, re.I)
    if m:
        return urljoin(base_url, m.group(1).strip())

    for tag in ("iframe", "embed", "a"):
        m = re.search(rf'<{tag}[^>]+(?:src|href)=["\']([^"\']+\.pdf[^"\']*)', html, re.I)
        if m:
            return urljoin(base_url, m.group(1).strip())

    m = re.search(r'(?:href|src)=["\']([^"\']*getPDF\.jsp[^"\']*)', html, re.I)
    if m:
        return urljoin(base_url, m.group(1).strip())

    m = re.search(r'href=["\']([^"\']+\.pdf[^"\']*)', html, re.I)
    if m:
        return urljoin(base_url, m.group(1).strip())

    return None

def download_pdf(url: str, output_path: str, timeout: int = 30) -> bool:
    """
    Downloads a PDF from a URL, handling meta-refresh and iframe redirects.
    Special handling for Semantic Scholar URLs.
    Returns True on success, False on failure.
    """
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.8",
        "Referer": url,
    }

    try:
        print(f"Downloading PDF from {url} to {output_path}")
        
        # Check if this is a Semantic Scholar URL
        parsed_url = urlparse(url)
        is_semantic_scholar = "semanticscholar.org" in parsed_url.netloc.lower()
        
        if is_semantic_scholar:
            print(f"  Detected Semantic Scholar URL, attempting to find PDF...")
            paper_id = _extract_semantic_scholar_paper_id(url)
            
            if paper_id:
                # Try API first
                print(f"  Trying Semantic Scholar API for paper ID: {paper_id}")
                api_pdf_url = _get_semantic_scholar_pdf_url(paper_id)
                if api_pdf_url:
                    print(f"  Found PDF via API: {api_pdf_url}")
                    # Try downloading from the API-provided URL
                    with requests.Session() as s:
                        r = s.get(api_pdf_url, headers=headers, stream=True, timeout=timeout, allow_redirects=True)
                        r.raise_for_status()
                        it = r.iter_content(chunk_size=8192)
                        first = next(it, b"")
                        if _looks_like_pdf(r.headers, first):
                            with open(output_path, "wb") as f:
                                if first:
                                    f.write(first)
                                for chunk in it:
                                    if chunk:
                                        f.write(chunk)
                            print(f"  Successfully downloaded PDF from API URL")
                            return True
            
            # Try converting /paper/ to /reader/ or /pdf/
            alternative_urls = []
            if "/paper/" in url:
                alternative_urls.append(url.replace("/paper/", "/reader/"))
                alternative_urls.append(url.replace("/paper/", "/pdf/"))
            
            # Try alternative Semantic Scholar URLs
            for alt_url in alternative_urls:
                try:
                    with requests.Session() as s:
                        r = s.get(alt_url, headers=headers, stream=True, timeout=timeout, allow_redirects=True)
                        r.raise_for_status()
                        it = r.iter_content(chunk_size=8192)
                        first = next(it, b"")
                        if _looks_like_pdf(r.headers, first):
                            with open(output_path, "wb") as f:
                                if first:
                                    f.write(first)
                                for chunk in it:
                                    if chunk:
                                        f.write(chunk)
                            print(f"  Successfully downloaded PDF from alternative URL: {alt_url}")
                            return True
                except Exception:
                    continue
        
        # Standard download process
        with requests.Session() as s:
            r = s.get(url, headers=headers, stream=True, timeout=timeout, allow_redirects=True)
            r.raise_for_status()
            
            it = r.iter_content(chunk_size=8192)
            first = next(it, b"")
            
            if _looks_like_pdf(r.headers, first):
                with open(output_path, "wb") as f:
                    if first:
                        f.write(first)
                    for chunk in it:
                        if chunk:
                            f.write(chunk)
                return True

            r.close()
            r_html = s.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            r_html.raise_for_status()
            html = r_html.text

            # Use Semantic Scholar-specific extraction if needed
            if is_semantic_scholar:
                pdf_url = _extract_pdf_url_from_semantic_scholar(html, r_html.url)
                if pdf_url:
                    print(f"  Found PDF URL from page: {pdf_url}")
                else:
                    pdf_url = _extract_pdf_url(html, r_html.url)
            else:
                pdf_url = _extract_pdf_url(html, r_html.url)
            
            if not pdf_url:
                print(f"  No PDF link found on page")
                return False

            print(f"  Found PDF URL: {pdf_url}")
            r2 = s.get(pdf_url, headers=headers, stream=True, timeout=timeout, allow_redirects=True)
            r2.raise_for_status()
            
            it2 = r2.iter_content(chunk_size=8192)
            first2 = next(it2, b"")
            
            if not _looks_like_pdf(r2.headers, first2):
                print(f"  Resolved link is not a PDF")
                return False

            with open(output_path, "wb") as f:
                if first2:
                    f.write(first2)
                for chunk in it2:
                    if chunk:
                        f.write(chunk)
            return True

    except Exception as e:
        print(f"  Error downloading {url}: {e}")
        return False

def is_valid_pdf(file_path):
    try:
        if not os.path.exists(file_path):
            return False
        
        file_size = os.path.getsize(file_path)
        if file_size < 100:
            return False
        
        with open(file_path, 'rb') as f:
            header = f.read(8)
            if header.startswith(b'%PDF-'):
                return True
            return False
    except Exception:
        return False