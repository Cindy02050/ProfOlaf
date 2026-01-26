import json
import click
from prompt_toolkit import Application
from prompt_toolkit.layout import Layout, HSplit
from prompt_toolkit.widgets import TextArea, Button, Label
from prompt_toolkit.key_binding import KeyBindings
from utils.db_management import DBManager, SelectionStage
from utils.cli.pretty_print_utils import pretty_print, format_color_string, prompt_input
from utils.pipeline.screening import choose_elements

with open("confs/search_conf.json", "r") as f:
    search_conf = json.load(f)


@click.command()
@click.option('--iteration', type=int, required=True, help='Iteration number')
@click.option('--db-path', type=str, default=None, help='Database path (defaults to search_conf.json value)')
@click.option('--rater', type=str, required=True, help='Rater ID')
@click.option('--llm', type=bool, default=False, help='Use LLM for screening')
@click.option('--model', type=str, default='gpt-4o', help='Model to use for screening')
@click.option('--api-key', type=str, default=None, help='API key for screening')
@click.option('--article_folder', type=str, default=None, help='Folder to store the articles')
def main(iteration, db_path, rater, llm, model, api_key, article_folder):
    """Filter articles by content (abstract and introduction) with interactive CLI."""
    if db_path is None:
        db_path = search_conf["db_path"]
    
    db_manager = DBManager(db_path)
    articles = db_manager.get_iteration_data(
        iteration=iteration,
        selected=SelectionStage.TITLE_APPROVED,
    )
    if not llm:
        choose_elements(
            articles, 
            db_manager, 
            iteration, 
            rater, 
            SelectionStage.CONTENT_APPROVED, 
            search_conf.get("annotations", [])
        )
    else:
        confirm = input(f"Filtering by content with an LLM requires downloading all the PDFs. Are you sure you want to continue? (y/n): ")
        if confirm == "y":
            if article_folder is None:
                print("Please provide a folder to store the articles")
                sys.exit(1)
            if not os.path.exists(article_folder):
                os.makedirs(article_folder)
            download_pdfs(articles, article_folder)
            screen_papers(
                rater,
                search_conf["topic"],
                db_path,
                iteration,
                "content",
                article_folder=article_folder,
                model=model,
                api_key=api_key
            )
    
if __name__ == "__main__":
    main()
