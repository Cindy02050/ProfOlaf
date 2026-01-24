import argparse
import json
import os
import sqlite3
import sys

from openai import OpenAI
from openrouter import OpenRouter
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

# Add project root to Python path to enable imports
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from utils.article_processing.shared_utils import (
    PDFProcessor,
    load_config,
    create_llm,
    get_use_chat_model,
    truncate_text,
)
from utils.article_processing.download_pdfs import download_pdf


title_system_prompt = """
You are a helpful assistant that screens papers during the snowballing process.
You are responsible for an initial screen of the papers based on their title.
Therefore, you should only remove the papers that are clearly not relevant to the current topic.
What you should remove:
- Articles that clearly do not fit the topic. You need to be 100% sure that the paper cannot be related to the topic.
- Articles that are surveys or literature reviews.
What you should keep:
- Articles that are clearly related to the topic.
- Articles that might be related to the topic, even if only in part.
- Some titles can be too general or only seem relevant in part to the topic. In this case, you should keep the paper.
Since this is the first phase of screening, you are encouraged to adopt a more lenient approach when deciding whether to keep the paper.
You'll be given the title of the paper and the desired topic. 
You should output a JSON object with the following fields:
- title: The title of the paper
- keep: Whether to keep the paper
- reason: The reason for the decision
"""

title_user_prompt = """
Title: {title}
Desired topic: {topic}
"""

content_system_prompt = """
You are a helpful assistant that screens papers during the snowballing process.
You are responsible for screeningthe papers based on their content.
You should read the content of the paper and decide if it is relevant to the current topic.
You'll be given the title of the paper, the content of the paper and the desired topic. 
What you should remove:
- Articles that clearly do not fit the topic.
- Articles that are surveys or literature reviews.
What you should keep:
- Articles that are related to the topic.
- Case studies that are related to the topic.
- Articles that introduce a new method or approach that is clearly related to the topic.
- Articles that have as a main contribution a new dataset or benchmark that is clearly related to the topic.
You should output a JSON object with the following fields:
- title: The title of the paper
- keep: Whether to keep the paper
- reason: The reason for the decision
"""

content_user_prompt = """
Title: {title}
Content: {content}
Desired topic: {topic}
"""


class ScreeningResult(BaseModel):
    title: str = Field(description="The title of the paper")
    keep: bool = Field(description="Whether to keep the paper")
    reason: str = Field(description="The reason for the decision")

def process_ieee_urls(url: str):
    pdf_url = "https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber={url_id}"
    url_parts = url.split("/")
    url_id = ""
    for part in url_parts:
        if part.isdigit():
            url_id = part
            break
    print(f"URL ID: {url_id}")
    print(f"PDF URL: {pdf_url.format(url_id=url_id)}")
    return pdf_url.format(url_id=url_id)

def process_arxiv_urls(url: str):
    return url.replace("/abs/", "/pdf/")

def download_all_articles(article_rows: list):
    failed_downloads = []
    for row in article_rows:
        print(row[5])
        if os.path.exists(f"articles/{row[5]}.pdf"):
            continue
        
        url = row[1]
        article_id = row[5]
        res = download_pdf(url, f"articles/{article_id}.pdf")
        if not res and "https://ieeexplore.ieee.org/abstract" in url:
            print(f"Failed to download. Processing IEEE URL: {url}")
            url = process_ieee_urls(url)
            res = download_pdf(url, f"articles/{article_id}.pdf")
        elif not res and "https://arxiv.org/abs/" in url or "dl.acm.org":
            print(f"Failed to download. Processing Arxiv URL: {url}")
            url = process_arxiv_urls(url)
            res = download_pdf(url, f"articles/{article_id}.pdf")
        if not res:
            print(f"Failed to download. Adding to failed downloads: {url}")
            failed_downloads.append(row)
            continue
        print("Successfully downloaded")

    for download in failed_downloads:      
        url = download[1]
        article_id = download[5]
        title = download[0]
        
        while not os.path.exists(f"articles/{article_id}.pdf"):
            input(f"Failed to download {title}. \nDownload the pdf in {url} with name 'articles/{article_id}.pdf' ({url}) and then press Enter to continue...")


def get_content_from_pdf(row: tuple, iteration: int):
    _id = row[-1]
    content = PDFProcessor.extract_text_from_pdf(f"articles/iteration{iteration}/{_id}.pdf")
    return content

def get_articles_from_db(db_path: str, iteration: int, stage="title"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if stage == "title":
        select_nums = (1, 2, 3)
    elif stage == "content":
        select_nums = (2, 3)
    else:
        return -1

    query = f"SELECT title, pub_url, title_filtered_out, abstract_filtered_out, selected, id FROM iterations WHERE iteration = {iteration} AND selected IN {select_nums}"
    print(query)
    cursor.execute(query)
    rows = cursor.fetchall()
    return rows

def ask_model(
    system_prompt: str,
    user_prompt: str,
    model: str = "open-ai/gpt-5.2",
    api_key: Optional[str] = None,
    temperature: float = 0.7,
):
    client = OpenRouter(api_key=api_key or os.getenv("OPENAI_API_KEY"))
    schema = ScreeningResult.model_json_schema()

    try:
        response = client.chat.send(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "ScreeningResult",
                    "schema": schema,
                },
            },
            temperature=temperature,
        )
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON response: {e}\nResponse: {response_text}")
    except Exception as e:
        raise RuntimeError(f"Error calling OpenAI API: {e}")

    raw_json = response.choices[0].message.content
    result = ScreeningResult.model_validate_json(raw_json)
    return dict(result.model_dump())

def screen_papers(
    topic: str, 
    db_path: str, 
    iteration: int, 
    phase: str,
    model: str = "gpt-4o",
    api_key: Optional[str] = None,
    temperature: float = 0.7,
    ):
    rows = get_articles_from_db(db_path, iteration, phase)
    print("Number of articles to screen", len(rows))
    
    results = []
    for row in rows:
        title = row[0]
        topic = topic
        content = ""
        if phase == "content":
            content = get_content_from_pdf(row, iteration)
        if len(content) == 0 and phase == "content":
            print(f"Content is empty for {title}")
            continue
        system_prompt = title_system_prompt if phase == "title" else content_system_prompt
        user_prompt = title_user_prompt.format(title=title, topic=topic) if phase == "title" else content_user_prompt.format(title=title, content=content, topic=topic)

        result = ask_model(system_prompt, user_prompt, model, api_key, temperature)
        article_phase = row[2] if phase == "title" else row[3]
        print(row[2], row[3], article_phase)
        result["ground_truth"] = False if article_phase == 1 else True
        results.append(result)
        
    with open(f"results/it{iteration}_{phase}_results.jsonl", "w") as f:
        for result in results:
            f.write(json.dumps(result) + "\n")
    return results


def parse_args():
    parser = argparse.ArgumentParser(description="Screen papers")
    parser.add_argument("--topic", type=str, required=True)
    parser.add_argument("--db-path", type=str, required=True)
    parser.add_argument("--iteration", type=int, required=True)
    parser.add_argument("--phase", type=str, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    print("Args", args)
    screen_papers(args.topic, args.db_path, args.iteration, args.phase)

