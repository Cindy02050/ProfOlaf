#!/usr/bin/env python3

import csv
import os
import sys
import re
import pathlib
from urllib.parse import urljoin
import requests
import time
import argparse
import json

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)



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
    Returns True on success, False on failure.
    """
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.8",
        "Referer": url,
    }

    try:
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