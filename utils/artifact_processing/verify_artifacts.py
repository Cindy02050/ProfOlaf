#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pypdf>=4.0.0",
#   "requests>=2.32.0",
#   "pyyaml>=6.0.0",
#   "urlextract>=1.8.0",
#   "snowballstemmer>=2.2.0",
# ]
# ///
"""
PDF artefact URL finder.

Usage:
    uv run artefact_candidates.py /path/to/file.pdf
    uv run artefact_candidates.py https://example.com/file.pdf
    uv run artefact_candidates.py -                # read PDF bytes from stdin
    uv run artefact_candidates.py                  # read PDF bytes from stdin when piped
    uv run artefact_candidates.py /path/to/file.pdf --config config.yml
"""

import argparse
import logging
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Tuple, Dict, Union, Any
from urllib.parse import urlparse, unquote
import warnings

import requests
import yaml
from pypdf import PdfReader
from pypdf.errors import PdfReadWarning
import snowballstemmer
from urlextract import URLExtract

warnings.filterwarnings("ignore", category=PdfReadWarning)
for _logger_name in ("pypdf", "pypdf._user_warnings"):
    logging.getLogger(_logger_name).setLevel(logging.ERROR)

stemmer = snowballstemmer.stemmer("english")
url_extractor = URLExtract()
url_extractor.update_when_older = False

DEFAULT_WINDOW_SIZE: int = 5
DEFAULT_CTX_SIZE: int = 200
DEFAULT_CONTEXT_WORDS: int = 10
DEFAULT_KEYWORDS: List[str] = [
    "implementation",
    "source code",
    "source-code",
    "dataset",
    "data set",
    "repository",
    "supplementary material",
    "artifact",
    "artefact",
    "benchmark",
    "evaluation code",
    "experiment code",
    "codebase",
    "released"
]
DEFAULT_WHITELIST: List[str] = [
    # "github.com",
    # "github.io",
    # "gitlab.com",
    # "bitbucket.org",
    # "zenodo.org",
    # "figshare.com",
    # "huggingface.co",
    # "osf.io",
]

DEFAULT_CONFIG: Dict[str, Union[List[str], int]] = {
    "whitelisted_services": DEFAULT_WHITELIST,
    "keywords": DEFAULT_KEYWORDS,
    "window_size": DEFAULT_WINDOW_SIZE,
}


@dataclass
class Config:
    whitelisted_services: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    window_size: int = DEFAULT_CONFIG["window_size"]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        merged = dict(DEFAULT_CONFIG)
        merged.update(data or {})
        return cls(
            whitelisted_services=list(merged.get("whitelisted_services", DEFAULT_WHITELIST)),
            keywords=list(merged.get("keywords", DEFAULT_KEYWORDS)),
            window_size=int(merged.get("window_size", DEFAULT_WINDOW_SIZE)),
        )


@dataclass
class UrlHit:
    url: str
    page_index: int
    context: str
    reason: str  # "keyword-url", "citation-url", "footnote-url"
    keyword: str = ""


def load_config(config_path: Optional[str]) -> Config:
    if not config_path:
        return Config.from_dict({})
    path = Path(config_path).expanduser()
    if not path.is_file():
        print(f"Warning: config file not found at {path}, using defaults.", file=sys.stderr)
        return Config.from_dict({})
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        print("Warning: config file must contain a mapping; using defaults.", file=sys.stderr)
        data = {}
    return Config.from_dict(data)


def is_probably_url(target: str) -> bool:
    parsed = urlparse(target)
    return parsed.scheme in ("http", "https")


def is_file_uri(target: str) -> bool:
    return urlparse(target).scheme == "file"


def download_to_temp(url: str) -> Path:
    try:
        response = requests.get(url, stream=True, timeout=20)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"Error: failed to download PDF from {url}: {exc}", file=sys.stderr)
        raise SystemExit(1)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as fh:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                fh.write(chunk)
        return Path(fh.name)


def read_stdin_to_temp() -> Path:
    data = sys.stdin.buffer.read()
    if not data:
        print("Error: stdin was empty; nothing to read.", file=sys.stderr)
        raise SystemExit(1)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as fh:
        fh.write(data)
        return Path(fh.name)


def process_pdf(
    pdf_path: Path,
    cfg: Config,
    dedup_enabled: bool = False,
    context_words: int = DEFAULT_CONTEXT_WORDS,
) -> List[UrlHit]:
    reader = PdfReader(str(pdf_path))

    pages_text_raw = [page.extract_text() or "" for page in reader.pages]
    pages_text = [normalize_ligatures(txt) for txt in pages_text_raw]

    page_link_uris = extract_page_link_uris(reader)
    all_annot_urls: List[str] = [u for urls in page_link_uris.values() for u in urls]

    citation_style = detect_citation_style(pages_text)
    reference_cutoffs = find_reference_cutoffs(pages_text)

    reference_map = build_reference_url_map(pages_text, citation_style, all_annot_urls)
    footnotes_by_page = build_footnote_maps(pages_text)
    footnotes_by_page = upgrade_footnote_maps_with_annotations(footnotes_by_page, page_link_uris)
    keyword_patterns = prepare_keyword_patterns(cfg.keywords)

    hits: List[UrlHit] = []
    seen: set[str] = set()

    for page_index, text in enumerate(pages_text):
        tokens = list(tokenize_with_positions(text))
        keyword_spans = find_keyword_spans(text, tokens, keyword_patterns)

        cutoff = reference_cutoffs.get(page_index)
        if cutoff is not None:
            keyword_spans = [kw for kw in keyword_spans if kw["start"] < cutoff]

        urls_from_text = find_urls_and_dois(text)
        annot_urls = page_link_uris.get(page_index, [])
        urls_on_page = merge_urls_with_annotations(urls_from_text, annot_urls, text)

        citations_on_page = find_citation_markers(text, citation_style)
        if cutoff is not None:
            citations_on_page = [c for c in citations_on_page if c["start"] < cutoff]  # type: ignore[index]

        footnote_markers = find_footnote_markers(text, citations_on_page)

        for kw in keyword_spans:
            kw_context = context_snippet(
                text,
                tokens,
                kw["token_start"],
                kw["token_end"],
                context_words,
            )
            nearby = hits_from_nearby_urls(
                kw, urls_on_page, tokens, page_index, cfg, kw_context, reason="keyword-url"
            )
            if dedup_enabled:
                hits.extend(dedup_hits(nearby, seen))
            else:
                hits.extend(nearby)

        if keyword_spans and citations_on_page:
            citation_hits = hits_from_citations(
                keyword_spans,
                citations_on_page,
                tokens,
                text,
                page_index,
                cfg,
                reference_map,
                context_words,
            )
            if dedup_enabled:
                hits.extend(dedup_hits(citation_hits, seen))
            else:
                hits.extend(citation_hits)

        if keyword_spans and footnotes_by_page.get(page_index):
            footnote_hits = hits_from_footnotes(
                keyword_spans,
                footnote_markers,
                tokens,
                text,
                page_index,
                cfg,
                footnotes_by_page.get(page_index, {}),
                context_words,
            )
            if dedup_enabled:
                hits.extend(dedup_hits(footnote_hits, seen))
            else:
                hits.extend(footnote_hits)

    return hits


def prepare_keyword_patterns(keywords: List[str]) -> List[Dict[str, Any]]:
    patterns: List[Dict[str, Any]] = []
    for kw in keywords:
        tokens = re.findall(r"[A-Za-z]+", kw.lower())
        stems = [stem_word(tok) for tok in tokens]
        if not stems:
            continue
        patterns.append({"stems": stems, "keyword": kw})
    return patterns


def find_keyword_spans(
    text: str,
    tokens: List[Tuple[str, int, int]],
    patterns: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    spans: List[Dict[str, Any]] = []
    if not tokens or not patterns:
        return spans
    stems = [stem_word(tok.lower()) for tok, _, _ in tokens]
    for i in range(len(tokens)):
        for pat in patterns:
            pattern_stems = pat["stems"]
            length = len(pattern_stems)
            if i + length > len(tokens):
                continue
            if stems[i : i + length] != pattern_stems:
                continue
            if not whitespace_only_between(text, tokens, i, i + length):
                continue
            spans.append(
                {
                    "start": tokens[i][1],
                    "end": tokens[i + length - 1][2],
                    "center_token": i + length // 2,
                    "token_start": i,
                    "token_end": i + length - 1,
                    "keyword": pat["keyword"],
                }
            )
    return spans


def whitespace_only_between(text: str, tokens: List[Tuple[str, int, int]], start: int, end: int) -> bool:
    for idx in range(start, end - 1):
        gap = text[tokens[idx][2] : tokens[idx + 1][1]]
        if gap and not gap.isspace():
            return False
    return True


def normalize_url(url: str) -> str:
    if not url:
        return url
    u = url.strip()
    u = u.rstrip(").,;\"'")
    return u


def find_urls_and_dois(text: str) -> List[Tuple[str, int, int]]:
    urls: List[Tuple[str, int, int]] = []

    for found, (start, end) in url_extractor.find_urls(
        text, only_unique=False, get_indices=True, with_schema_only=False
    ):
        parsed = urlparse(found)
        if parsed.scheme not in ("http", "https"):
            continue
        urls.append((normalize_url(found), start, end))

    for match in re.finditer(r"\b10\.\d{4,9}/\S+\b", text):
        doi_raw = match.group(0).rstrip(").,;\"'")
        url = f"https://doi.org/{doi_raw}" if not doi_raw.startswith("http") else doi_raw
        urls.append((normalize_url(url), match.start(), match.end()))

    pattern = re.compile(r"https?://doi\.org/\s*(10\.\d{4,9}/\S+)", re.IGNORECASE)
    for m in pattern.finditer(text):
        doi_part = m.group(1)
        doi_clean = re.sub(r"\s+", "", doi_part)
        url = f"https://doi.org/{doi_clean}"
        urls.append((normalize_url(url), m.start(), m.end()))

    filtered: List[Tuple[str, int, int]] = []
    for url, start, end in urls:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if host in ("doi.org", "dx.doi.org"):
            path = parsed.path.lstrip("/")
            if not re.fullmatch(r"10\.\d{4,9}/\S+", path):
                continue
        filtered.append((url, start, end))

    return filtered


def extract_page_link_uris(reader: PdfReader) -> Dict[int, List[str]]:
    page_links: Dict[int, List[str]] = {}
    for idx, page in enumerate(reader.pages):
        urls: List[str] = []
        try:
            annots = page.get("/Annots") or []
        except Exception:
            annots = []
        for annot_ref in annots:
            try:
                annot = annot_ref.get_object()
            except Exception:
                continue
            if annot.get("/Subtype") != "/Link":
                continue
            action = annot.get("/A") or {}
            if action.get("/S") == "/URI":
                uri = action.get("/URI")
                if isinstance(uri, str) and uri.startswith(("http://", "https://")):
                    urls.append(normalize_url(uri))
        if urls:
            page_links[idx] = urls
    return page_links


def hosts_equivalent(h1: str, h2: str) -> bool:
    h1 = h1.lower()
    h2 = h2.lower()
    if h1 == h2:
        return True
    if h1.endswith("gshare.com") and h2.endswith("gshare.com"):
        return True
    return False


def is_probably_truncated_url(url: str, parsed=None) -> bool:
    from urllib.parse import urlparse as _urlparse

    if parsed is None:
        parsed = _urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path
    if "?" in url and parsed.query == "":
        return True
    if host.endswith("github.com") and path.endswith("/blob/"):
        return True
    if host.endswith("figshare.com") or host.endswith("gshare.com"):
        if path.rstrip("/").endswith("/s") and len(path.rstrip("/").split("/")) <= 3:
            return True
    return False


def merge_urls_with_annotations(
    text_urls: List[Tuple[str, int, int]],
    annot_urls: List[str],
    page_text: str,
) -> List[Tuple[str, int, int]]:
    if not annot_urls:
        return text_urls

    merged: List[Tuple[str, int, int]] = []
    used_annots: set[str] = set()

    for url, start, end in text_urls:
        chosen_url = url
        parsed_text = urlparse(url)
        for a in annot_urls:
            try:
                p_annot = urlparse(a)
            except Exception:
                continue
            if p_annot.scheme not in ("http", "https") or parsed_text.scheme not in ("http", "https"):
                continue
            if not hosts_equivalent(parsed_text.netloc, p_annot.netloc):
                continue
            text_full = parsed_text.geturl()
            annot_full = p_annot.geturl()
            if annot_full.startswith(text_full) or text_full.startswith(annot_full):
                if is_probably_truncated_url(text_full, parsed_text):
                    if len(annot_full) > len(chosen_url):
                        chosen_url = annot_full
                        used_annots.add(a)
        merged.append((normalize_url(chosen_url), start, end))

    for a in annot_urls:
        if a in used_annots:
            continue
        try:
            parsed = urlparse(a)
        except Exception:
            continue
        anchor_pos = -1
        if parsed.netloc:
            anchor_pos = page_text.find(parsed.netloc)
        if anchor_pos < 0:
            anchor_pos = 0
        end_pos = anchor_pos + len(parsed.netloc) if parsed.netloc else anchor_pos
        merged.append((normalize_url(a), anchor_pos, end_pos))

    return merged


def upgrade_reference_urls_with_annotations(
    ref_map: Dict[str, List[str]],
    annot_urls: List[str],
) -> Dict[str, List[str]]:
    if not annot_urls:
        return ref_map

    annot_norm = [normalize_url(a) for a in annot_urls]
    upgraded: Dict[str, List[str]] = {}

    for cid, urls in ref_map.items():
        new_urls: List[str] = []
        for url in urls:
            text_url = normalize_url(url)
            try:
                p_text = urlparse(text_url)
            except Exception:
                if text_url not in new_urls:
                    new_urls.append(text_url)
                continue
            if p_text.scheme not in ("http", "https"):
                if text_url not in new_urls:
                    new_urls.append(text_url)
                continue

            truncated = is_probably_truncated_url(text_url, p_text)
            best = text_url
            extras: List[str] = []

            for a in annot_norm:
                try:
                    p_annot = urlparse(a)
                except Exception:
                    continue
                if p_annot.scheme not in ("http", "https"):
                    continue
                if not hosts_equivalent(p_text.netloc, p_annot.netloc):
                    continue

                text_full = p_text.geturl()
                annot_full = p_annot.geturl()

                if annot_full.startswith(text_full) or text_full.startswith(annot_full):
                    if truncated:
                        if len(annot_full) > len(best):
                            best = annot_full
                    else:
                        if annot_full != text_full and annot_full not in extras:
                            extras.append(annot_full)

            if best not in new_urls:
                new_urls.append(normalize_url(best))
            for e in extras:
                if e not in new_urls:
                    new_urls.append(normalize_url(e))

        upgraded[cid] = new_urls

    return upgraded


def upgrade_footnote_maps_with_annotations(
    page_maps: Dict[int, Dict[str, List[str]]],
    page_link_uris: Dict[int, List[str]],
) -> Dict[int, Dict[str, List[str]]]:
    if not page_maps:
        return page_maps
    upgraded: Dict[int, Dict[str, List[str]]] = {}
    for page_idx, entries in page_maps.items():
        annots = page_link_uris.get(page_idx, [])
        if not annots:
            upgraded[page_idx] = entries
            continue
        upgraded[page_idx] = upgrade_reference_urls_with_annotations(entries, annots)
    return upgraded


def token_index_for_pos(tokens: List[Tuple[str, int, int]], pos: int) -> int:
    for idx, (_, start, end) in enumerate(tokens):
        if start <= pos <= end:
            return idx
        if pos < start:
            return idx
    return len(tokens) - 1 if tokens else 0


def hits_from_nearby_urls(
    kw_span: Dict[str, Any],
    urls: List[Tuple[str, int, int]],
    tokens: List[Tuple[str, int, int]],
    page_index: int,
    cfg: Config,
    context: str,
    reason: str,
) -> List[UrlHit]:
    hits: List[UrlHit] = []
    keyword_term = kw_span.get("keyword", "")
    for url, start, _ in urls:
        token_idx = token_index_for_pos(tokens, start)
        if abs(token_idx - kw_span["center_token"]) > cfg.window_size:
            continue
        if not domain_whitelisted(url, cfg.whitelisted_services):
            continue
        hits.append(
            UrlHit(
                url=url,
                page_index=page_index,
                context=context,
                reason=reason,
                keyword=keyword_term,
            )
        )
    return hits


def detect_citation_style(pages_text: List[str]) -> str:
    joined = "\n".join(pages_text)
    counts = {
        "numeric_bracket": len(re.findall(r"\[\d{1,3}\]", joined)),
        "numeric_paren": len(re.findall(r"\(\d{1,3}\)", joined)),
        "numeric_superscript": len(re.findall(r"[\u00b9\u00b2\u00b3\u2070-\u2079]", joined)),
        "author_year": len(re.findall(r"[A-Z][A-Za-z]+(?: et al\.)?,?\s*\d{4}[a-z]?", joined)),
    }
    style = max(counts, key=counts.get)
    return style


def hits_from_citations(
    keyword_spans: List[Dict[str, Any]],
    citations: List[Dict[str, Union[str, int]]],
    tokens: List[Tuple[str, int, int]],
    text: str,
    page_index: int,
    cfg: Config,
    reference_map: Dict[str, List[str]],
    context_words: int,
) -> List[UrlHit]:
    hits: List[UrlHit] = []
    if not keyword_spans or not citations:
        return hits
    for kw in keyword_spans:
        keyword_term = kw.get("keyword", "")
        for citation in citations:
            cid = str(citation["id"])
            pos = int(citation["start"])
            token_idx = token_index_for_pos(tokens, pos)
            distance = abs(token_idx - kw["center_token"])
            if distance > cfg.window_size:
                continue
            start_tok_idx = token_index_for_pos(tokens, citation["start"])
            end_tok_idx = token_index_for_pos(tokens, citation["end"])
            cit_context = context_snippet(
                text, tokens, start_tok_idx, end_tok_idx, context_words
            )
            for url in reference_map.get(cid, []):
                if not domain_whitelisted(url, cfg.whitelisted_services):
                    continue
                hits.append(
                    UrlHit(
                        url=url,
                        page_index=page_index,
                        context=cit_context,
                        reason="citation-url",
                        keyword=keyword_term,
                    )
                )
    return hits


def hits_from_footnotes(
    keyword_spans: List[Dict[str, Any]],
    footnote_markers: List[Dict[str, Union[str, int]]],
    tokens: List[Tuple[str, int, int]],
    text: str,
    page_index: int,
    cfg: Config,
    footnotes_for_page: Dict[str, List[str]],
    context_words: int,
) -> List[UrlHit]:
    hits: List[UrlHit] = []
    if not keyword_spans or not footnote_markers:
        return hits
    for kw in keyword_spans:
        keyword_term = kw.get("keyword", "")
        for marker in footnote_markers:
            marker_id = str(marker["id"])
            pos = int(marker["start"])
            token_idx = token_index_for_pos(tokens, pos)
            distance = abs(token_idx - kw["center_token"])
            if distance > cfg.window_size:
                continue
            start_tok_idx = token_index_for_pos(tokens, marker["start"])
            end_tok_idx = token_index_for_pos(tokens, marker["end"])
            marker_context = context_snippet(
                text, tokens, start_tok_idx, end_tok_idx, context_words
            )
            for url in footnotes_for_page.get(marker_id, []):
                if not domain_whitelisted(url, cfg.whitelisted_services):
                    continue
                hits.append(
                    UrlHit(
                        url=url,
                        page_index=page_index,
                        context=marker_context,
                        reason="footnote-url",
                        keyword=keyword_term,
                    )
                )
    return hits


def dedup_hits(candidates: List[UrlHit], seen: set[str]) -> List[UrlHit]:
    unique: List[UrlHit] = []
    for hit in candidates:
        anchor = hit.url
        if anchor in seen:
            continue
        seen.add(anchor)
        unique.append(hit)
    return unique


def find_citation_markers(text: str, style: str) -> List[Dict[str, Union[str, int]]]:
    markers: List[Dict[str, Union[str, int]]] = []
    patterns: List[str] = []
    if style == "numeric_bracket":
        patterns = [r"\[(\d{1,3})(?:\s*[-–]\s*(\d{1,3}))?\]"]
    elif style == "numeric_paren":
        patterns = [r"\((\d{1,3})(?:\s*[-–]\s*(\d{1,3}))?\)"]
    elif style == "numeric_superscript":
        patterns = [r"([\u00b9\u00b2\u00b3\u2070-\u2079]+)"]
    else:
        patterns = [
            r"\(([A-Z][A-Za-z]+(?: et al\.)?(?:\s+and\s+[A-Z][A-Za-z]+|(?:,\s*[A-Z][A-Za-z]+)*)?,?\s*\d{4}[a-z]?)\)",
            r"\b([A-Z][A-Za-z]+(?:\s+et al\.)?(?:\s+and\s+[A-Z][A-Za-z]+|(?:,\s*[A-Z][A-Za-z]+)*)?,?\s*\d{4}[a-z]?)",
        ]

    for pattern in patterns:
        for match in re.finditer(pattern, text):
            if match.group(1):
                marker_id = (
                    normalize_author_year_label(match.group(1))
                    if style == "author_year"
                    else normalize_marker_id(match.group(1))
                )
                markers.append({"id": marker_id, "start": match.start(), "end": match.end()})
            if match.lastindex and match.lastindex >= 2 and match.group(2):
                try:
                    start_num = int(match.group(1))
                    end_num = int(match.group(2))
                    for num in range(start_num + 1, end_num + 1):
                        markers.append(
                            {"id": str(num), "start": match.start(), "end": match.end()}
                        )
                except ValueError:
                    pass
    return markers


def find_footnote_markers(
    text: str, citations: List[Dict[str, Union[str, int]]]
) -> List[Dict[str, Union[str, int]]]:
    citation_spans = {(c["start"], c["end"]) for c in citations}
    markers: List[Dict[str, Union[str, int]]] = []
    superscripts = "⁰¹²³⁴⁵⁶⁷⁸⁹"
    for match in re.finditer(r"(?<![\[\(])(\d{1,3})(?![\]\)])", text):
        span = (match.start(), match.end())
        if any(span[0] >= s and span[1] <= e for s, e in citation_spans):
            continue
        markers.append({"id": match.group(1), "start": match.start(), "end": match.end()})
    for match in re.finditer(rf"[{superscripts}]", text):
        marker_id = normalize_superscript(match.group(0))
        span = (match.start(), match.end())
        if any(span[0] >= s and span[1] <= e for s, e in citation_spans):
            continue
        markers.append({"id": marker_id, "start": match.start(), "end": match.end()})
    return markers


def build_reference_url_map(
    pages_text: List[str],
    style: str,
    annot_urls: Optional[List[str]] = None,
) -> Dict[str, List[str]]:
    mapping: Dict[str, List[str]] = {}
    all_text = "\n".join(pages_text)
    lines = all_text.splitlines()
    current_id: Optional[str] = None
    buffer: List[str] = []

    def flush():
        if current_id is None or not buffer:
            return
        snippet = " ".join(buffer)
        for url, _, _ in find_urls_and_dois(snippet):
            mapping.setdefault(current_id, []).append(url)

    if style in ("numeric_bracket", "numeric_paren", "numeric_superscript"):
        pattern = r"\s*(?:[\[\(](\d{1,3})[\]\)]|(\d{1,3})[.)]|([⁰¹²³⁴⁵⁶⁷⁸⁹]+))\s*(.*)"
        for line in lines:
            m = re.match(pattern, line)
            if m:
                flush()
                current_id = normalize_marker_id(m.group(1) or m.group(2) or m.group(3))
                buffer = [m.group(4)]
            elif current_id:
                if line.strip() == "":
                    flush()
                    current_id = None
                    buffer = []
                else:
                    buffer.append(line.strip())
        flush()
    else:
        for line in lines:
            m = re.match(r"\s*([A-Z][A-Za-z].*?\d{4}[a-z]?)\s+(.*)", line)
            if not m:
                continue
            cid = normalize_author_year_label(m.group(1).strip())
            rest = m.group(2)
            for url, _, _ in find_urls_and_dois(rest):
                mapping.setdefault(cid, []).append(url)

    if annot_urls:
        mapping = upgrade_reference_urls_with_annotations(mapping, annot_urls)

    return mapping


def build_footnote_maps(pages_text: List[str]) -> Dict[int, Dict[str, List[str]]]:
    page_maps: Dict[int, Dict[str, List[str]]] = {}
    for idx, text in enumerate(pages_text):
        entries: Dict[str, List[str]] = {}
        for line in text.splitlines():
            m = re.match(r"\s*([0-9]{1,3}|[⁰¹²³⁴⁵⁶⁷⁸⁹])\s*(.*)", line)
            if not m:
                continue
            marker = normalize_marker_id(m.group(1))
            rest = m.group(2)
            found_urls = list(find_urls_and_dois(rest))
            if not found_urls:
                continue
            for url, _, _ in found_urls:
                entries.setdefault(marker, []).append(url)
        if entries:
            page_maps[idx] = entries
    return page_maps


def find_reference_cutoffs(pages_text: List[str]) -> Dict[int, int]:
    cutoffs: Dict[int, int] = {}
    header_re = re.compile(r"^\s*(references|bibliography)\b", re.IGNORECASE | re.MULTILINE)
    first_page: Optional[int] = None

    for idx, text in enumerate(pages_text):
        if first_page is None:
            m = header_re.search(text)
            if m:
                first_page = idx
                cutoffs[idx] = m.start()
        else:
            cutoffs[idx] = 0

    return cutoffs


def domain_whitelisted(url: str, whitelist: List[str]) -> bool:
    if not whitelist:
        return True
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    return any(
        host == domain.lower()
        or host.endswith(f".{domain.lower()}")
        or host.endswith(domain.lower())
        for domain in whitelist
    )


def tokenize_with_positions(text: str) -> Iterable[Tuple[str, int, int]]:
    for match in re.finditer(r"[A-Za-z]{2,}", text):
        yield match.group(0), match.start(), match.end()


def normalize_superscript(char: str) -> str:
    mapping = {
        "⁰": "0",
        "¹": "1",
        "²": "2",
        "³": "3",
        "⁴": "4",
        "⁵": "5",
        "⁶": "6",
        "⁷": "7",
        "⁸": "8",
        "⁹": "9",
    }
    return mapping.get(char, char)


def normalize_marker_id(raw: str) -> str:
    if re.fullmatch(r"[\u00b9\u00b2\u00b3\u2070-\u2079]+", raw):
        return "".join(normalize_superscript(ch) for ch in raw)
    return raw


def normalize_author_year_label(label: str) -> str:
    cleaned = re.sub(r"[()]", " ", label)
    cleaned = re.sub(r"[;,]", " ", cleaned)
    return collapse_ws(cleaned)


def stem_word(word: str) -> str:
    return stemmer.stemWords([word])[0] if word else ""


def collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def safe_text(value: str) -> str:
    return value.encode("utf-8", "ignore").decode("utf-8", "ignore")


_LIGATURE_MAP = {
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "ﬅ": "ft",
    "ﬆ": "st",
}


def normalize_ligatures(text: str) -> str:
    return "".join(_LIGATURE_MAP.get(ch, ch) for ch in text)


def context_snippet(
    text: str,
    tokens: List[Tuple[str, int, int]],
    start_token_idx: int,
    end_token_idx: int,
    context_words: int,
) -> str:
    if not tokens:
        return ""
    left_idx = max(0, start_token_idx - context_words)
    right_idx = min(len(tokens) - 1, end_token_idx + context_words)
    start_char = tokens[left_idx][1]
    end_char = tokens[right_idx][2]
    snippet = text[start_char:end_char]
    snippet = normalize_ligatures(snippet)
    return safe_text(collapse_ws(snippet))


def emit_hits(hits: List[UrlHit], fmt: str, context_len: int) -> None:
    if fmt == "urls":
        for hit in hits:
            print(safe_text(hit.url))
        return

    for hit in hits:
        url = safe_text(hit.url)
        context = safe_text(collapse_ws(hit.context))
        if context_len > 0:
            context = context[:context_len]
        keyword = safe_text(hit.keyword or "-")
        if fmt == "tsv":
            print(f"{url}\t{hit.page_index}\t{hit.reason}\t{keyword}\t{context}")
        else:
            print(f"page={hit.page_index} reason={hit.reason} keyword={keyword} url={url}")
            if context:
                print(f"  context: {context}")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Find artefact URLs in a PDF.")
    p.add_argument(
        "pdf",
        nargs="?",
        help="PDF location (local path, file:// URI, HTTP(S) URL). Use '-' or omit to read PDF bytes from stdin.",
    )
    p.add_argument(
        "--config",
        "-c",
        help="YAML config path (overrides defaults)",
    )
    p.add_argument(
        "--format",
        "-f",
        choices=["urls", "tsv", "verbose"],
        default="urls",
        help="Output format. Default: urls (one URL per line).",
    )
    p.add_argument(
        "--context-chars",
        type=int,
        default=DEFAULT_CTX_SIZE,
        help="Max characters of context to emit (tsv/verbose formats).",
    )
    p.add_argument(
        "--dedup",
        action="store_true",
        help="Enable deduplication of identical URLs (based on full normalized URL).",
    )
    p.add_argument(
        "--context-words",
        type=int,
        default=DEFAULT_CONTEXT_WORDS,
        help="Number of words to include before and after the matched keyword or marker in the context snippet.",
    )
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    cfg = load_config(args.config)

    tmp_files: List[Path] = []
    try:
        if args.pdf is None or args.pdf == "-":
            if sys.stdin.buffer.isatty():
                print(
                    "Error: no PDF provided and stdin is empty. Pass a path/URL or pipe PDF bytes.",
                    file=sys.stderr,
                )
                return 1
            pdf_path = read_stdin_to_temp()
            tmp_files.append(pdf_path)
        elif is_probably_url(args.pdf):
            pdf_path = download_to_temp(args.pdf)
            tmp_files.append(pdf_path)
        elif is_file_uri(args.pdf):
            parsed = urlparse(args.pdf)
            pdf_path = Path(unquote(parsed.path)).expanduser().resolve()
            if not pdf_path.is_file():
                print(f"Error: PDF not found at {pdf_path}", file=sys.stderr)
                return 1
        else:
            pdf_path = Path(args.pdf).expanduser().resolve()
            if not pdf_path.is_file():
                print(f"Error: PDF not found at {pdf_path}", file=sys.stderr)
                return 1

        hits = process_pdf(
            pdf_path,
            cfg,
            dedup_enabled=args.dedup,
            context_words=args.context_words,
        )

        emit_hits(hits, fmt=args.format, context_len=args.context_chars)

        if not hits:
            print("No candidate artefact URLs found.", file=sys.stderr)
            return 2

        return 0
    finally:
        for tmp_file in tmp_files:
            try:
                tmp_file.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())