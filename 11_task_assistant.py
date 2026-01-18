import os
import argparse
from pathlib import Path

from utils.article_llm_analysis.task_assistant import (
    PDFQASystem,
    load_config,
    create_llm,
    get_use_chat_model,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Task Assistant System with LangChain")

    parser.add_argument("prompts_folder", help="Folder containing prompt files (one prompt per .txt file)")
    
    parser.add_argument(
        "--config",
        default="paper_analysis/llm_config.json",
        help="Configuration file for LLM settings",
    )

    parser.add_argument(
        "--provider",
        default="openai",
        choices=["openai", "gemini", "anthropic", "openai-completion"],
        help="LLM provider to use",
    )
    parser.add_argument("--output", help="Output file to save results (JSON format)")
    parser.add_argument("--pdf-folder", help="Path to folder containing PDF files")
    parser.add_argument("--single-pdf", help="Process a single PDF file instead of folder")
    parser.add_argument(
        "--context-length",
        type=int,
        default=16385,
        help="Maximum context length in tokens (default: 16385)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=1,
        help="Maximum number of parallel workers for PDF processing (default: 1)",
    )

    return parser.parse_args()

def check_and_load_config(config_path):
    if not os.path.exists(config_path):
        print(f"Configuration file not found: {config_path}")
        print("Please create a configuration file with your API keys. Example:")
        print('{"openai": {"api_key": "your-key-here", "model": "gpt-3.5-turbo"}}')
        exit(1)
    try:
        config = load_config(config_path)
    except Exception as e:
        print(f"Error loading configuration from {config_path}: {e}")
        exit(1)
    return config

def get_prompts(prompts_folder):
    prompts_folder = Path(args.prompts_folder)
    if not prompts_folder.exists():
        print(f"Prompts folder does not exist: {prompts_folder}")
        return

    prompt_files = list(prompts_folder.glob("*.txt"))
    if not prompt_files:
        print(f"No .txt files found in {prompts_folder}")
        return

    prompts = []
    for prompt_file in sorted(prompt_files):
        with open(prompt_file, "r", encoding="utf-8") as f:
            prompt_content = f.read().strip()
            if not prompt_content:
                continue
            prompts.append(
                {"filename": prompt_file.name, "content": prompt_content}
            )

    if not prompts:
        print(f"No valid prompts found in the folder {prompts_folder}")
        exit(1)
    return prompts

def initialize_qa_system(config, args):
    try:
        provider_config = config[args.provider]
        llm = create_llm(args.provider, provider_config)
        use_chat_model = get_use_chat_model(args.provider)
        max_output_tokens = provider_config.get("max_tokens", 1000)
    except KeyError:
        print(f"Configuration for {args.provider} not found in {args.config}")
        return
    except Exception as e:
        print(f"Error creating LLM: {e}")
        return

    return PDFQASystem(
        llm,
        use_chat_model,
        args.context_length,
        max_output_tokens,
        args.provider,
        provider_config["model"],
        provider_config,
    )
    
def main():
    args = parse_args()
    # Load configuration
    config = check_and_load_config(args.config)
    # Get prompts from folder
    prompts = get_prompts(args.prompts_folder)
    # Create LLM
    qa_system = initialize_qa_system(config, args)

    # Process PDFs
    if args.single_pdf:
        pricing = provider_config.get("pricing_per_1k_tokens", {})
        print(f"Processing single PDF: {args.single_pdf}")
        print(f"Using {args.provider} with model: {provider_config['model']}")
        print(
            f"Pricing: ${pricing.get('input', 0):.6f}/1K input, ${pricing.get('output', 0):.6f}/1K output"
        )
        print("-" * 60)

        for prompt in prompts:
            print(f"Prompt: {prompt['filename']}")
            print(f"Content: {prompt['content'][:100]}...")
            response = qa_system.ask_single_prompt(args.single_pdf, prompt["content"])
            print(f"Answer: {response['answer']}")
            print(
                f"Cost: ${response['cost']:.6f} ({response['input_tokens']} input + {response['output_tokens']} output tokens)"
            )
            print("-" * 50)

        # Display cost summary for single PDF processing
        cost_summary = qa_system.get_cost_summary()
        print("=" * 60)
        print("COST SUMMARY")
        print("=" * 60)
        print(f"Total cost: ${cost_summary['total_cost']:.6f}")
        print(f"Total input tokens: {cost_summary['total_input_tokens']:,}")
        print(f"Total output tokens: {cost_summary['total_output_tokens']:,}")
        print(f"Provider: {cost_summary['provider']}")
        print(f"Model: {cost_summary['model']}")

    elif args.pdf_folder:
        results = qa_system.process_pdf_folder(
            args.pdf_folder, prompts, args.output, args.max_workers
        )
        print(
            f"Processed {len([k for k in results.keys() if not k.startswith('_')])} PDF files"
        )
    else:
        print("Use --single-pdf or --pdf-folder")

if __name__ == "__main__":
    main()