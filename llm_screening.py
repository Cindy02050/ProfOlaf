import sqlite3
import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from openai import OpenAI

from pydantic import BaseModel, Field

# Add project root to Python path to enable imports
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from paper_analysis.shared_utils import (
    PDFProcessor,
    load_config,
    create_llm,
    get_use_chat_model,
    truncate_text,
)
from paper_analysis.download_pdfs import download_pdf

class ScreeningResult(BaseModel):
    title: str = Field(description="The title of the paper")
    keep: bool = Field(description="Whether to keep the paper")
    reason: str = Field(description="The reason for the decision")

title_system_prompt = """
You are a helpful assistant that screens papers during the snowballing process.
You are responsible for an initial screen of the papers based on their title.
Therefore, you should only remove the papers that are clearly not relevant to the current topic.
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
You are responsible for an initial screen of the papers based on their content.
You should read the content of the paper and decide if it is relevant to the current topic.
You'll be given the title of the paper, the content of the paper and the desired topic. 
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

def get_content_from_pdf(url: str):
    result = download_pdf(url, "temp.pdf")
    if not result:
        while not os.path.exists("temp.pdf"):
            input(f"Failed to download. \nDownload the pdf with name 'temp.pdf' ({url}) and then press Enter to continue...")
    else:
        print("PDF downloaded successfully")
    content = PDFProcessor.extract_text_from_pdf("temp.pdf")
    return content

def get_articles_from_db(db_path: str, iteration: int, stage="title"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if stage == "title":
        select_nums = (1, 2)
    elif stage == "content":
        select_nums = (2, 3)
    else:
        return -1

    query = f"SELECT title, pub_url, title_filtered_out, abstract_filtered_out, selected FROM iterations WHERE iteration = {iteration} AND selected IN {select_nums}"
    print(query)
    cursor.execute(query)
    rows = cursor.fetchall()
    return rows

def ask_model(
    system_prompt: str,
    user_prompt: str,
    model: str = "gpt-4o",
    api_key: Optional[str] = None,
    temperature: float = 0.7,
):
    client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
    try:
        response = client.responses.parse(
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            text_format=ScreeningResult,
        )
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON response: {e}\nResponse: {response_text}")
    except Exception as e:
        raise RuntimeError(f"Error calling OpenAI API: {e}")

    return dict(response.output_parsed)

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
    results = []
    for row in rows:
        title = row[0]
        if phase == "content":
            content = get_content_from_pdf(row[1])
        system_prompt = title_system_prompt if phase == "title" else content_system_prompt
        user_prompt = title_user_prompt.format(title=title, topic=topic) if phase == "title" else content_user_prompt.format(title=title, content=content, topic=topic)

        result = ask_model(system_prompt, user_prompt, model, api_key, temperature)
        phase = row[2] if phase == "title" else row[3]
        result["ground_truth"] = not phase
        results.append(result)
    
    return results

if __name__ == "__main__":
    results = screen_papers(topic="Machine Learning for Code", db_path="evaluation.db", iteration=1, phase="content")
    with open(f"results_{phase}.jsonl", "w") as f:
        for result in results:
            f.write(json.dumps(result) + "\n")

