import json
import click
from utils.db_management import DBManager, SelectionStage
from utils.cli.pretty_print_utils import pretty_print, format_color_string, prompt_input
from utils.pipeline.screening import choose_elements
from utils.pipeline.llm_screening import screen_papers

with open("confs/search_conf.json", "r") as f:
    search_conf = json.load(f)

@click.command()
@click.option('--iteration', type=int, required=True, help='Iteration number')
@click.option('--db-path', type=str, default=None, help='Database path (defaults to search_conf.json value)')
@click.option('--rater', type=str, required=True, help='Rater name')
@click.option('--llm', type=bool, default=False, help='Use LLM for screening')
@click.option('--model', type=str, default='gpt-4o', help='Model to use for screening')
@click.option('--api-key', type=str, default=None, help='API key for screening')
def main(iteration, db_path, rater, llm, model, api_key):
    """Filter articles by title with interactive CLI."""
    if db_path is None:
        db_path = search_conf["db_path"]
    
    db_manager = DBManager(db_path)
    articles = db_manager.get_iteration_data(
        iteration=iteration, 
        selected=SelectionStage.METADATA_APPROVED
    )
    if not llm:
        article_ids = [a.id for a in articles]
        existing_screening_data = db_manager.get_screening_data_for_rater(article_ids, iteration, rater, phase="title")
        choose_elements(
            articles,
            existing_screening_data,
            db_manager,
            iteration,
            rater,
            SelectionStage.TITLE_APPROVED,
            search_conf.get("annotations", []),
        )
    else:
        screen_papers(
            rater,
            search_conf["topic"],
            db_path,
            iteration,
            "title",
            model=model,
            api_key=api_key
        )


if __name__ == "__main__":
    main()
