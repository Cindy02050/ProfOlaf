import json
import click
from prompt_toolkit import Application
from prompt_toolkit.layout import Layout, HSplit
from prompt_toolkit.widgets import TextArea, Button, Label
from prompt_toolkit.key_binding import KeyBindings
from utils.db_management import DBManager, SelectionStage
from utils.pretty_print_utils import pretty_print, format_color_string, prompt_input
from utils.pipeline.screening import choose_elements

with open("search_conf.json", "r") as f:
    search_conf = json.load(f)


@click.command()
@click.option('--iteration', type=int, required=True, help='Iteration number')
@click.option('--db-path', type=str, default=None, help='Database path (defaults to search_conf.json value)')
@click.option('--rater', type=str, required=True, help='Rater ID')
@click.option('--llm', type=bool, default=False, help='Use LLM for screening')
@click.option('--model', type=str, default='gpt-4o', help='Model to use for screening')
def main(iteration, db_path):
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
        #TODO: Implement LLM screening
        pass
    
if __name__ == "__main__":
    main()
