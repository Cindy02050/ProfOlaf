import sys, re, json, html, difflib
import os
import csv
from dataclasses import dataclass, asdict
from typing import Optional, List, Tuple, Dict, Any
from urllib.parse import quote_plus, urljoin, urlparse, parse_qs
import requests
from bs4 import BeautifulSoup
from utils.venue_rank_search.conference_similarity_search import VenueMatch, similarity_score
SCIMAGO_BASE_URL = "https://www.scimagojr.com/"

# Path to the Scimago CSV file
# From utils/venue_rank_search/scimago_search.py to utils/ranking_tables/scimagojr.csv
SCIMAGO_CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ranking_tables", "scimagojr.csv")

@dataclass
class JournalRank:
    title: str
    sjr_year: Optional[int]
    sjr_value: Optional[float]
    quartile: Optional[str]
    url: str


def extract_title(url: str, session: requests.Session, headers: Dict[str, str]):
    try: 
        r = session.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.find("h1")
        if title:
            return title.get_text(strip=True)
        else:
            return ""
    except Exception as e:
        pass
    return ""

def scimago_search(venue: str, session: Optional[requests.Session] = None):
    if not venue or not venue.strip():
        raise ValueError("Venue is required")
    session = session or requests.Session()
    url = urljoin(SCIMAGO_BASE_URL, f"journalsearch.php?q={quote_plus(venue)}")
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ScimagoScraper/1.0)"}
    r = session.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    seen = set()
    candidates = []
    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        href = a["href"]
        if not text or any(nav in text for nav in ("Scimago", "Home", "Help", "Country Rankings", "Journal Rankings")):
            continue
        if "journalsearch.php" in href and ("tip=sid" in href or "q=" in href):
            abs_url = urljoin(SCIMAGO_BASE_URL, href)
            if abs_url in seen:
                continue
            seen.add(abs_url)
            clean_title = extract_title(abs_url, session, headers)
            if not clean_title:
                clean_title = text.strip()
            score = similarity_score(venue, clean_title)
            candidates.append(VenueMatch(title=clean_title, url=abs_url, sid=None, similarity_score=score))

    candidates.sort(key=lambda x: x.similarity_score, reverse=True)
    return candidates   
    

def parse_rank_from_detail(html_text: str) -> Tuple[Optional[int], Optional[float], Optional[str]]:
    """Parse the latest SJR year, value, and any inline quartile token."""
    soup = BeautifulSoup(html_text, "html.parser")
    text = soup.get_text("\n", strip=True)

    m = re.search(r"SJR\s+(\d{4})\s+([0-9]+(?:\.[0-9]+)?)\s+(Q[1-4])", text, flags=re.I)
    if m:
        return int(m.group(1)), float(m.group(2)), m.group(3).upper()

    sjr_year = None; sjr_val = None
    mblock = re.search(r"SJR\s*(.+?)(?:\n\n|\nTotal Documents|\nCitations per document|\n% International Collaboration|\Z)", text, flags=re.I|re.S)
    sjr_block = mblock.group(1) if mblock else None
    if not sjr_block:
        mstart = re.search(r"SJR", text, flags=re.I)
        if mstart: sjr_block = text[mstart.end(): mstart.end()+1200]
    if sjr_block:
        pairs = re.findall(r"\b((?:19|20)\d{2})\b\s+([0-9]+(?:\.[0-9]+)?)", sjr_block)
        if pairs:
            sjr_year = max(int(y) for y,_ in pairs)
            for y, v in pairs:
                if int(y) == sjr_year:
                    try: sjr_val = float(v)
                    except Exception: sjr_val = None
                    break

    qtoken = re.search(r"\bQ[1-4]\b", text, flags=re.I)
    quartile = qtoken.group(0).upper() if qtoken else None
    return sjr_year, sjr_val, quartile

def fetch_rank(url: str, session: requests.Session):
    session = session or requests.Session()
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ScimagoScraper/1.0)"}
    r = session.get(url, headers=headers)
    r.raise_for_status()
    year, val, q = parse_rank_from_detail(r.text)
    soup = BeautifulSoup(r.text, "html.parser")

    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)
    else:
        title_tag = soup.find("title")
        page_title = title_tag.get_text(strip=True) if title_tag else url
    return JournalRank(title=title, sjr_year=year, sjr_value=val, quartile=q, url=url)
 

def parse_categories_quartile(html_text: str) -> Dict[str, Dict[str, Any]]:
    """Extract per-category quartiles from the 'Quartiles' section of a SCImago page."""
    soup = BeautifulSoup(html_text, "html.parser")
    
    # First try to extract from JavaScript dataquartiles variable
    js_data_match = re.search(r'var dataquartiles = "([^"]+)"', html_text)
    if js_data_match:
        data_string = js_data_match.group(1)
        data: Dict[str, Dict[str, Any]] = {}
        
        lines = data_string.split('\\n')
        for line in lines[1:]:  # Skip header line
            if ';' in line:
                parts = line.split(';')
                if len(parts) >= 3:
                    category = parts[0].strip()
                    year = int(parts[1].strip())
                    quartile = parts[2].strip().upper()
                    
                    entry = {"year": year, "quartile": quartile}
                    bucket = data.setdefault(category, {"entries": []})
                    bucket["entries"].append(entry)
        order = {"Q1":1,"Q2":2,"Q3":3,"Q4":4}
        if data is None:
            return {}
        for cat, bucket in data.items():
            entries = sorted(bucket["entries"], key=lambda e: e["year"])
            bucket["entries"] = entries
            bucket["latest"] = entries[-1] if entries else None
            bucket["best_quartile"] = min(entries, key=lambda e: order.get(e["quartile"], 99))["quartile"] if entries else None
        
        return data
    

def _load_scimago_csv():
    """Load the Scimago CSV file into memory. Returns a list of dictionaries."""
    if not os.path.exists(SCIMAGO_CSV_PATH):
        raise FileNotFoundError(f"Scimago CSV file not found at {SCIMAGO_CSV_PATH}")
    
    journals = []
    with open(SCIMAGO_CSV_PATH, 'r', encoding='utf-8') as f:
        # CSV uses semicolon as delimiter
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            journals.append({
                'title': row.get('Title', '').strip(),
                'categories': row.get('Categories', '').strip(),
                'sjr': row.get('SJR', '').strip(),
                'sjr_best_quartile': row.get('SJR Best Quartile', '').strip()
            })
    return journals

def _parse_categories_from_csv(categories_str: str) -> Dict[str, Dict[str, Any]]:
    """
    Parse categories string from CSV format: "Category1 (Q1); Category2 (Q2); ..."
    Returns a dictionary similar to parse_categories_quartile format.
    """
    if not categories_str:
        return {}
    
    categories = {}
    # Split by semicolon
    category_parts = [part.strip() for part in categories_str.split(';')]
    
    for part in category_parts:
        # Match pattern like "Category Name (Q1)" or "Category Name (Q2)"
        match = re.match(r'^(.+?)\s*\(([Qq][1-4])\)$', part)
        if match:
            category_name = match.group(1).strip()
            quartile = match.group(2).upper()
            
            # Create structure similar to parse_categories_quartile
            if category_name not in categories:
                categories[category_name] = {
                    "entries": [],
                    "latest": {"quartile": quartile},
                    "best_quartile": quartile,
                    "current": {"quartile": quartile}
                }
            else:
                # Update if this is a better quartile
                current_best = categories[category_name]["best_quartile"]
                quartile_order = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}
                if quartile_order.get(quartile, 99) < quartile_order.get(current_best, 99):
                    categories[category_name]["best_quartile"] = quartile
                    categories[category_name]["latest"]["quartile"] = quartile
                    categories[category_name]["current"]["quartile"] = quartile
    
    return categories

def find_scimago_rank_from_csv(venue: str, min_similarity: float = 0.5):
    """
    Find the rank of the venue from Scimago CSV file.
    Returns the same structure as find_scimago_rank for compatibility.
    """
    journals = _load_scimago_csv()
    
    # Find best matching journal by title similarity
    candidates = []
    for journal in journals:
        title = journal['title']
        score = similarity_score(venue, title)
        candidates.append({
            'title': title,
            'score': score,
            'categories': journal['categories'],
            'sjr': journal['sjr'],
            'sjr_best_quartile': journal['sjr_best_quartile']
        })
    
    # Sort by similarity score
    candidates.sort(key=lambda x: x['score'], reverse=True)
    
    if not candidates:
        raise RuntimeError(f"No candidates found for {venue}")
    
    # Get best match
    best_match = candidates[0]
    if best_match['score'] < min_similarity:
        # Try to find a better match from top 5
        for candidate in candidates[:5]:
            if candidate['score'] >= min_similarity:
                best_match = candidate
                break
    
    if best_match['score'] < min_similarity:
        raise RuntimeError(f"No suitable match found for {venue} (best similarity: {best_match['score']:.2f})")
    
    # Create VenueMatch object (without URL since we're using CSV)
    best = VenueMatch(
        title=best_match['title'],
        url="",  # No URL for CSV-based search
        sid=None,
        similarity_score=best_match['score']
    )
    
    # Create JournalRank object
    # Try to extract SJR value if available
    sjr_value = None
    try:
        sjr_str = best_match['sjr'].replace(',', '.')
        sjr_value = float(sjr_str) if sjr_str else None
    except (ValueError, AttributeError):
        pass
    
    rank = JournalRank(
        title=best_match['title'],
        sjr_year=None,  # CSV doesn't have year info
        sjr_value=sjr_value,
        quartile=best_match['sjr_best_quartile'] if best_match['sjr_best_quartile'] else None,
        url=""  # No URL for CSV-based search
    )
    
    # Parse categories
    categories = _parse_categories_from_csv(best_match['categories'])
    
    return best, rank, categories

def find_scimago_rank(venue: str, session: Optional[requests.Session] = None, min_similarity: float = 0.5, use_csv: bool = True):
    """
    Find the rank of the venue from Scimago.
    By default, uses CSV file. Set use_csv=False to use web scraping (legacy).
    """
    if use_csv:
        try:
            return find_scimago_rank_from_csv(venue, min_similarity)
        except (FileNotFoundError, RuntimeError) as e:
            # Fall back to web scraping if CSV fails
            print(f"CSV search failed: {e}. Falling back to web scraping...")
            return find_scimago_rank_web(venue, session, min_similarity)
    else:
        return find_scimago_rank_web(venue, session, min_similarity)

def find_scimago_rank_web(venue: str, session: Optional[requests.Session] = None, min_similarity: float = 0.5):
    """
    Find the rank of the venue from Scimago using web scraping (legacy method).
    """
    session = session or requests.Session()
    candidates = scimago_search(venue, session)
    if not candidates:
        raise RuntimeError(f"No candidates found for {venue}")
    best = candidates[0]
    if best.similarity_score < min_similarity:
        for candidate in candidates[:5]:
            if candidate.similarity_score > min_similarity:
                best = candidate; break
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ScimagoScraper/1.0)"}
    r = session.get(best.url, headers=headers, timeout=30)
    r.raise_for_status()
    rank = fetch_rank(best.url, session)
    categories = parse_categories_quartile(r.text)

    current_year = rank.sjr_year
    if categories is None:
        return best, rank, {}
    if current_year is not None:
        for category, bucket in categories.items():
            if not bucket.get("entries"):
                continue
            by_year = {e["year"]: e for e in bucket["entries"] if "year" in e}
            bucket["current"] = by_year.get(current_year, bucket.get("latest"))
    else:
        for category, bucket in categories.items():
            bucket["current"] = bucket.get("latest")
    
    return best, rank, categories

    