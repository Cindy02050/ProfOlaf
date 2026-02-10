import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from openrouter import OpenRouter
from pydantic import BaseModel, Field

# Add project root to Python path to enable imports
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from utils.article_processing.shared_utils import PDFProcessor


class TopicCriticResult(BaseModel):
    """Result from the LLM critic for a single topic assignment"""
    topic: str = Field(description="The topic being evaluated")
    keep: bool = Field(description="Whether to keep this topic assignment")
    reason: str = Field(description="The reason for the decision")


system_prompt = """
You are a helpful assistant that acts as a critic for topic assignments in academic articles.
You are responsible for evaluating whether a topic assignment is appropriate for a given article.

You'll be given:
- The title and content of an article
- A topic that was assigned to this article

Your task is to determine if the topic is relevant and appropriate for the article.

What you should REMOVE (set keep=False):
- Topics that are clearly not relevant to the article's content
- Topics that are too general or vague to be meaningful
- Topics that only tangentially relate to the article
- Topics that misrepresent the article's main focus

What you should KEEP (set keep=True):
- Topics that accurately represent the article's main themes or contributions
- Topics that are relevant even if they cover only part of the article
- Topics that are specific and meaningful

You should output a JSON object with the following fields:
- topic: The topic being evaluated
- keep: Whether to keep this topic assignment (true/false)
- reason: A brief explanation of your decision
"""

user_prompt_template = """
Article Title: {title}

Article Content:
{content}

Assigned Topic: {topic}

Please evaluate whether this topic assignment is appropriate for this article.
"""


def extract_topics_from_responses(responses: str) -> List[Tuple[str, str]]:
    """
    Extract topics from the responses field.
    Returns a list of (topic_name, full_description) tuples.
    """
    if not responses or not responses.strip():
        return []
    
    topics = []
    # Pattern to match [number] Topic Name: description
    # This handles cases where description might continue until next [number] or end of string
    pattern = r'\[(\d+)\]\s*([^:]+):\s*([^\[]+?)(?=\[\d+\]|$)'
    matches = re.finditer(pattern, responses, re.DOTALL)
    
    for match in matches:
        topic_num = match.group(1)
        topic_name = match.group(2).strip()
        topic_desc = match.group(3).strip()
        # Combine name and description for the full topic
        full_topic = f"{topic_name}: {topic_desc}"
        topics.append((topic_name, full_topic))
    
    return topics


def get_article_content(pdf_folder: str, filename: str) -> str:
    """
    Extract text content from a PDF file.
    Returns the extracted text or empty string if file not found.
    """
    pdf_path = Path(pdf_folder) / filename
    if not pdf_path.exists():
        print(f"Warning: PDF not found: {pdf_path}")
        return ""
    
    try:
        content = PDFProcessor.extract_text_from_pdf(str(pdf_path))
        if content.startswith("Error"):
            print(f"Warning: Error extracting text from {pdf_path}: {content}")
            return ""
        return content
    except Exception as e:
        print(f"Warning: Exception extracting text from {pdf_path}: {e}")
        return ""


def ask_model(
    system_prompt: str,
    user_prompt: str,
    model: str = "openai/gpt-4o",
    api_key: Optional[str] = None,
    temperature: float = 0.7,
) -> Dict[str, Any]:
    """
    Query the LLM using OpenRouter to evaluate a topic assignment.
    """
    client = OpenRouter(api_key=api_key or os.getenv("OPENAI_API_KEY"))
    schema = TopicCriticResult.model_json_schema()

    try:
        response = client.chat.send(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "TopicCriticResult",
                    "schema": schema,
                },
            },
            temperature=temperature,
        )
    except Exception as e:
        raise RuntimeError(f"Error calling OpenRouter API: {e}")

    raw_json = response.choices[0].message.content
    result = TopicCriticResult.model_validate_json(raw_json)
    return dict(result.model_dump())


def evaluate_topics(
    assignments_file: str,
    pdf_folder: str,
    output_file: str,
    model: str = "openai/gpt-4o",
    api_key: Optional[str] = None,
    temperature: float = 0.7,
):
    """
    Main function to evaluate topic assignments.
    
    Reads assignments.jsonl, evaluates each (article, topic) pair,
    and writes results to output_file with only approved topics.
    """
    pdf_folder_path = Path(pdf_folder)
    
    results = []
    total_evaluations = 0
    kept_topics = 0
    removed_topics = 0
    
    print(f"Reading assignments from: {assignments_file}")
    print(f"PDF folder: {pdf_folder}")
    print(f"Output file: {output_file}")
    print(f"Model: {model}")
    print()
    
    with open(assignments_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            
            try:
                article_data = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"Warning: Skipping line {line_num} due to JSON decode error: {e}")
                continue
            
            article_id = article_data.get('id', f'article_{line_num}')
            filename = article_data.get('filename', '')
            # Try to get title from text field, or use filename as fallback
            text_content = article_data.get('text', '')
            if text_content:
                # Use first line or first 200 chars as title
                title = text_content.split('\n')[0][:200] if '\n' in text_content else text_content[:200]
            else:
                # Fallback to filename without extension
                title = Path(filename).stem if filename else article_id
            responses = article_data.get('responses', '')
            
            print(f"Processing article {line_num}: {filename or article_id}")
            
            # Extract topics from responses
            topics = extract_topics_from_responses(responses)
            if not topics:
                print(f"  No topics found, skipping...")
                results.append(article_data)
                continue
            
            print(f"  Found {len(topics)} topics to evaluate")
            
            # Get article content
            content = get_article_content(pdf_folder, filename)
            if not content:
                print(f"  Warning: Could not extract content, using title only")
                content = title
            
            # Truncate content if too long (to avoid token limits)
            max_content_length = 50000  # Adjust based on model context window
            if len(content) > max_content_length:
                content = content[:max_content_length] + "... [truncated]"
            
            # Evaluate each topic
            approved_topics = []
            topic_evaluations = []
            
            for topic_name, full_topic in topics:
                total_evaluations += 1
                print(f"  Evaluating topic: {topic_name}")
                
                user_prompt = user_prompt_template.format(
                    title=title,
                    content=content,
                    topic=full_topic
                )
                
                try:
                    evaluation = ask_model(
                        system_prompt,
                        user_prompt,
                        model=model,
                        api_key=api_key,
                        temperature=temperature
                    )
                    
                    if evaluation['keep']:
                        approved_topics.append(full_topic)
                        kept_topics += 1
                        print(f"    ✓ KEPT: {evaluation['reason'][:100]}")
                    else:
                        removed_topics += 1
                        print(f"    ✗ REMOVED: {evaluation['reason'][:100]}")
                    
                    topic_evaluations.append({
                        'topic': full_topic,
                        'evaluation': evaluation
                    })
                    
                except Exception as e:
                    print(f"    ERROR evaluating topic: {e}")
                    # On error, keep the topic to be safe
                    approved_topics.append(full_topic)
                    kept_topics += 1
            
            # Reconstruct the responses field with only approved topics
            if approved_topics:
                # Format: [1] Topic Name: Description, [2] Topic Name: Description, etc.
                new_responses = "\n".join([
                    f"[{i+1}] {topic}" for i, topic in enumerate(approved_topics)
                ])
            else:
                new_responses = ""
            
            # Create output entry with same structure as input
            output_entry = {
                'id': article_data.get('id'),
                'text': article_data.get('text'),
                'filename': article_data.get('filename'),
                'prompted_docs': article_data.get('prompted_docs'),
                'responses': new_responses,
                'evaluations': topic_evaluations  # Store evaluations for reference
            }
            
            results.append(output_entry)
            print()
    
    # Write results to output file
    print(f"\nWriting results to: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        for result in results:
            # Remove evaluations field before writing (optional - comment out if you want to keep it)
            output_result = {k: v for k, v in result.items() if k != 'evaluations'}
            f.write(json.dumps(output_result, ensure_ascii=False) + '\n')
    
    print(f"\nSummary:")
    print(f"  Total articles processed: {len(results)}")
    print(f"  Total topic evaluations: {total_evaluations}")
    print(f"  Topics kept: {kept_topics}")
    print(f"  Topics removed: {removed_topics}")
    if total_evaluations > 0:
        print(f"  Keep rate: {kept_topics/total_evaluations*100:.1f}%")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Evaluate topic assignments using an LLM critic"
    )
    parser.add_argument(
        "--assignments-file",
        type=str,
        required=True,
        help="Path to the assignments.jsonl file"
    )
    parser.add_argument(
        "--pdf-folder",
        type=str,
        required=True,
        help="Path to folder containing PDF files"
    )
    parser.add_argument(
        "--output-file",
        type=str,
        required=True,
        help="Path to output jsonl file with filtered topics"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="openai/gpt-4o",
        help="OpenRouter model to use (default: openai/gpt-4o)"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="OpenRouter API key (default: uses OPENAI_API_KEY env var)"
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.7,
        help="Temperature for LLM (default: 0.7)"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    evaluate_topics(
        assignments_file=args.assignments_file,
        pdf_folder=args.pdf_folder,
        output_file=args.output_file,
        model=args.model,
        api_key=args.api_key,
        temperature=args.temperature,
    )

