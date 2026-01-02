import json
import click
from prompt_toolkit import Application
from prompt_toolkit.layout import Layout, HSplit
from prompt_toolkit.widgets import TextArea, Button, Label
from prompt_toolkit.key_binding import KeyBindings
from utils.db_management import DBManager, SelectionStage
from utils.pretty_print_utils import pretty_print, format_color_string, prompt_input


with open("search_conf.json", "r") as f:
    search_conf = json.load(f)


def get_selected_stage(article):
    return SelectionStage(article.selected)


def introduce_annotations(user, annotations):
    """
    Collect annotation data from the user using an interactive form.
    All fields are displayed at once, user can navigate with Tab/Shift+Tab,
    fill fields in any order, and submit at the end.
    """
    if not annotations or len(annotations) == 0:
        return user
    
    # Create key bindings
    kb = KeyBindings()
    
    @kb.add("tab")
    def _(event):
        event.app.layout.focus_next()
    
    @kb.add("s-tab")
    def _(event):
        event.app.layout.focus_previous()
    
    @kb.add("c-c")
    def _(event):
        event.app.exit(result=None)
    
    # Create form fields for each annotation
    fields = {}
    field_widgets = []
    
    for annotation in annotations:
        field = TextArea(
            prompt=f"{annotation}: ",
            multiline=False,
            focusable=True,
        )
        fields[annotation] = field
        field_widgets.append(field)
    
    # Result dictionary to store form data
    form_result = {}
    
    def save():
        """Collect all form data and exit."""
        for annotation, field in fields.items():
            form_result[annotation] = field.text.strip()
        app.exit(result=form_result)
    
    def cancel():
        """Cancel the form."""
        app.exit(result=None)
    
    save_button = Button(text="Save", handler=save)
    cancel_button = Button(text="Cancel", handler=cancel)
    
    # Create layout
    layout = Layout(
        HSplit([
            Label(text="Fill the annotation form (TAB / SHIFT+TAB to navigate, Ctrl+C to cancel)"),
            *field_widgets,
            save_button,
            cancel_button,
        ]),
        focused_element=field_widgets[0] if field_widgets else None,  # Focus first TextArea
    )
    
    # Create and run application
    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=False,
    )
    
    data = app.run()
    
    # Update user dict with form results
    if data:
        user.update(data)
        pretty_print(format_color_string("\nAnnotations saved!", "green", "bold"))
    else:
        pretty_print(format_color_string("\nAnnotations cancelled.", "yellow", "bold"))
    
    return user


def process_article(article, db_manager, iteration, i, total):
    """
    Process a single article and return the decision made.
    Returns: tuple (decision, user_data) where decision is 'y', 'n', 's', or 'b'
    user_data is a dict with 'reason' and any annotations.
    """
    print(f"\n({i}/{total})")
    
    title = article.title
    url = article.pub_url
    preprint = article.eprint_url
    
    title_string = format_color_string(title, "magenta", "bold")
    
    # Check if article was already processed
    if get_selected_stage(article).value >= SelectionStage.CONTENT_APPROVED.value or article.abstract_filtered_out == True:
        skip_reason = format_color_string("Article already selected", "green", "bold") if get_selected_stage(article).value >= SelectionStage.CONTENT_APPROVED.value else format_color_string("Article already filtered out", "red", "bold")
        pretty_print(f"Skipping Article {title_string}: {skip_reason}")
        return None, None
    
    while True:
        pretty_print(f"\nTitle: {title_string}")
        pretty_print(f"ID: {article.id}")
        pretty_print(f"Url: {url}")
        pretty_print(f"Preprint: {preprint}")
        
        user_input = prompt_input(f"Do you want to keep this element? (y/n/s for skip/b for back)").strip().lower()
        
        if user_input == 'y':
            user_reason = prompt_input(f"Please enter the reason for the selection (enter to skip): ").strip()
            user = {"reason": user_reason}
            if search_conf.get("annotations", []) != "" and len(search_conf.get("annotations", [])) > 0:
                user = introduce_annotations(user, search_conf.get("annotations", []))
            return 'y', user
        elif user_input == 'n':
            user_reason = prompt_input(f"Please enter the reason for the rejection (enter to skip): ").strip()
            user = {"reason": user_reason}
            return 'n', user
        elif user_input == 's':
            return 's', None
        elif user_input == 'b':
            return 'b', None
        else:
            pretty_print("Please enter 'y' for yes, 'n' for no, 's' for skip, or 'b' for back.")


def apply_decision(article, decision, user_data, db_manager, iteration):
    """
    Apply a decision to an article and update the database.
    """
    updated_data = []
    if decision == 'y':
        article.selected = SelectionStage.CONTENT_APPROVED
        updated_data.append((article.id, article.selected, "selected"))
        updated_data.append((article.id, json.dumps(user_data), "content_reason"))
    elif decision == 'n':
        article.abstract_filtered_out = True
        updated_data.append((article.id, article.abstract_filtered_out, "abstract_filtered_out"))
        updated_data.append((article.id, json.dumps(user_data), "content_reason"))
    # 's' (skip) doesn't require any database update
    
    if updated_data:
        db_manager.update_batch_iteration_data(iteration, updated_data)


def undo_decision(article, db_manager, iteration):
    """
    Undo the previous decision for an article.
    Updates both the in-memory article object and the database.
    """
    updated_data = []
    if get_selected_stage(article).value >= SelectionStage.CONTENT_APPROVED.value:
        article.selected = SelectionStage.TITLE_APPROVED
        updated_data.append((article.id, article.selected, "selected"))
        updated_data.append((article.id, "", "content_reason"))
    elif article.abstract_filtered_out:
        article.abstract_filtered_out = False
        updated_data.append((article.id, article.abstract_filtered_out, "abstract_filtered_out"))
        updated_data.append((article.id, "", "content_reason"))
    
    if updated_data:
        db_manager.update_batch_iteration_data(iteration, updated_data)


def choose_elements(articles, db_manager, iteration):
    """
    Choose the elements by abstract and introduction with ability to go back.
    """
    i = 0
    decisions = []
    
    while i < len(articles):
        article = articles[i]
        decision, user_data = process_article(article, db_manager, iteration, i + 1, len(articles))
        
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
                apply_decision(article, decision, user_data, db_manager, iteration)
                decisions.append((i, decision, user_data))
            i += 1
        else:
            i += 1


@click.command()
@click.option('--iteration', type=int, required=True, help='Iteration number')
@click.option('--db-path', type=str, default=None, help='Database path (defaults to search_conf.json value)')
def main(iteration, db_path):
    """Filter articles by content (abstract and introduction) with interactive CLI."""
    if db_path is None:
        db_path = search_conf["db_path"]
    
    db_manager = DBManager(db_path)
    articles = db_manager.get_iteration_data(
        iteration=iteration,
        selected=SelectionStage.TITLE_APPROVED,
    )
    choose_elements(articles, db_manager, iteration)


if __name__ == "__main__":
    main()
