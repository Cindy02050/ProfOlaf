import json
import click
from utils.db_management import DBManager, SelectionStage
from utils.pretty_print_utils import pretty_print, format_color_string, prompt_input


with open("search_conf.json", "r") as f:
    search_conf = json.load(f)

def get_selected_stage(article):
    return SelectionStage(article.selected)

def process_article(article, db_manager, iteration, i, total):
    """
    Process a single article and return the decision made.
    Returns: tuple (decision, reason) where decision is 'y', 'n', 's', or 'b'
    """
    print(f"\n({i}/{total})")
    title_string = format_color_string(article.title, "magenta", "bold")
    
    if get_selected_stage(article).value >= SelectionStage.TITLE_APPROVED.value or article.title_filtered_out == True:
        skip_reason = format_color_string("Article already selected", "green", "bold") if article.selected >= SelectionStage.TITLE_APPROVED.value else format_color_string("Article already filtered out", "red", "bold")
        pretty_print(f"Skipping Article {title_string}: {skip_reason}")
        return None, None
    
    while True:
        pretty_print(f"Title: {title_string}")
        user_input = prompt_input(f"Do you want to keep this element? (y/n/s for skip/b for back)").strip().lower()
        
        if user_input == 'y':
            user_reason = prompt_input(f"Please enter the reason for the selection (enter to skip)").strip()
            return 'y', user_reason
        elif user_input == 'n':
            user_reason = prompt_input(f"Please enter the reason for the rejection (enter to skip)").strip()
            return 'n', user_reason
        elif user_input == 's':
            return 's', None
        elif user_input == 'b':
            return 'b', None
        else:
            pretty_print("Please enter 'y' for yes, 'n' for no, 's' for skip, or 'b' for back.")


def apply_decision(article, decision, reason, db_manager, iteration):
    """
    Apply a decision to an article and update the database.
    """
    updated_data = []
    if decision == 'y':
        article.selected = SelectionStage.TITLE_APPROVED
        updated_data.append((article.id, article.selected, "selected"))
        updated_data.append((article.id, reason, "title_reason"))
    elif decision == 'n':
        article.title_filtered_out = True
        updated_data.append((article.id, article.title_filtered_out, "title_filtered_out"))
        updated_data.append((article.id, reason, "title_reason"))
    # 's' (skip) doesn't require any database update
    
    if updated_data:
        db_manager.update_batch_iteration_data(iteration, updated_data)


def undo_decision(article, db_manager, iteration):
    """
    Undo the previous decision for an article.
    Updates both the in-memory article object and the database.
    """
    updated_data = []
    if get_selected_stage(article).value >= SelectionStage.TITLE_APPROVED.value:
        article.selected = SelectionStage.METADATA_APPROVED
        updated_data.append((article.id, article.selected, "selected"))
        updated_data.append((article.id, "", "title_reason"))
    elif article.title_filtered_out:
        article.title_filtered_out = False
        updated_data.append((article.id, article.title_filtered_out, "title_filtered_out"))
        updated_data.append((article.id, "", "title_reason"))
    
    if updated_data:
        db_manager.update_batch_iteration_data(iteration, updated_data)


def choose_elements(articles, db_manager, iteration): 
    """
    Choose the elements by title with ability to go back.
    """
    i = 0
    decisions = []  
    while i < len(articles):
        article = articles[i]
        decision, reason = process_article(article, db_manager, iteration, i + 1, len(articles))
        if decision == 'b':
            if i > 0:
                prev_index = i - 1
                prev_article = articles[prev_index]
                undo_decision(prev_article, db_manager, iteration)
                
                if decisions and decisions[-1][0] == prev_index:
                    decisions.pop()
                
                i -= 1
                pretty_print(format_color_string("Going back to previous article...", "yellow", "bold"))
            else:
                pretty_print(format_color_string("Cannot go back: already at the first article.", "red", "bold"))
        elif decision is not None:
            if decision != 's':
                apply_decision(article, decision, reason, db_manager, iteration)
                decisions.append((i, decision, reason))
            i += 1
        else:
            i += 1


@click.command()
@click.option('--iteration', type=int, required=True, help='Iteration number')
@click.option('--db-path', type=str, default=None, help='Database path (defaults to search_conf.json value)')
def main(iteration, db_path):
    """Filter articles by title with interactive CLI."""
    if db_path is None:
        db_path = search_conf["db_path"]
    
    db_manager = DBManager(db_path)
    articles = db_manager.get_iteration_data(
        iteration=iteration, 
        selected=SelectionStage.METADATA_APPROVED
    )
  
    choose_elements(articles, db_manager, iteration)


if __name__ == "__main__":
    main()
