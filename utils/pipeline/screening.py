import json
from utils.cli.pretty_print_utils import (
    pretty_print, 
    format_color_string, 
    prompt_input
)

from ..db_management import SelectionStage, ArticleData


# ================================ Manual Screening ================================

# -------------------------- Checker Functions --------------------------

def get_selected_stage(article):
    return SelectionStage(int(article.selected))

def is_correct_article_stage(article: ArticleData, selection_stage: SelectionStage) -> bool:
    article_kept = article.keep_title if selection_stage == SelectionStage.TITLE_APPROVED else article.keep_content
    # if the article is not yet kept and the last stage the article went through was the stage before the current stage
    return get_selected_stage(article).value == selection_stage.value - 1 and not article_kept

def is_annotations_to_fill(annotation_list: list[str], selection_stage: SelectionStage) -> bool:
    return len(annotation_list) > 0 and\
        selection_stage == SelectionStage.CONTENT_APPROVED

# -------------------------- Main Functions --------------------------

def introduce_annotations(user_data: dict, annotations: list) -> dict:
    """
    Collect annotation data from the user using an interactive form.
    All fields are displayed at once, user can navigate with Tab/Shift+Tab,
    fill fields in any order, and submit at the end.
    """
    if not annotations or len(annotations) == 0:
        return user_data
    
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
        user_data.update(data)
        pretty_print(format_color_string("\nAnnotations saved!", "green", "bold"))
    else:
        pretty_print(format_color_string("\nAnnotations cancelled.", "yellow", "bold"))
    
    return user_data

def process_article(article, db_manager, iteration, rater, selection_stage, annotation_list: list[str]):
    """
    Process a single article and return the decision made.
    Returns: tuple (decision, reason) where decision is 'y', 'n', 's', or 'b'
    """
    title_string = format_color_string(article.title, "magenta", "bold")
    
    if not is_correct_article_stage(article, selection_stage):
        pretty_print(f"Skipping Article {title_string}")
        return None, None
    

    article_info_string = f"Title: {title_string}\n"
    article_info_string += f"ID: {article.id}\n"
    article_info_string += f"Url: {article.pub_url}\n" if selection_stage == SelectionStage.CONTENT_APPROVED else ""
    
    while True:
        pretty_print(article_info_string)
        user_input = prompt_input(f"Do you want to keep this element? (y/n/s for skip/b for back)").strip().lower()
        if user_input == 'y':
            user_reason = prompt_input(f"Please enter the reason for the selection (enter to skip)").strip()
            user_data = {"reason": user_reason}
            if is_annotations_to_fill(annotation_list, selection_stage):
                user_data = introduce_annotations(user_data, search_conf.get("annotations", []))
            return 'y', user_data
        elif user_input == 'n':
            user_reason = prompt_input(f"Please enter the reason for the rejection (enter to skip)").strip()
            user_data = {"reason": user_reason}
            return 'n', user_data
        elif user_input == 's':
            return 's', None
        elif user_input == 'b':
            return 'b', None
        else:
            pretty_print("Please enter 'y' for yes, 'n' for no, 's' for skip, or 'b' for back.")

def apply_decision(db_manager, article, iteration, rater, decision, reason, screening_phase: str="title", **annotations: str):
    """
    Apply a decision to an article and update the database.
    If screening_phase is "title", no annotations are needed.
    """
    keep = decision == 'y'
    if decision != 's':
        db_manager.insert_screening_data(
            article_id=article.id, 
            rater=rater, 
            iteration=iteration, 
            keep=keep, 
            reason=reason, 
            settled=False, 
            screening_phase=screening_phase,
            title=article.title,
            **annotations
        )

def undo_decision(db_manager, article, iteration, rater, screening_phase: str="title", annotations: list[str]=[]):
    """
    Undo the previous decision for an article.
    """
    if screening_phase == "title":
        keep_arg = "keep_title"
        reason_arg = "reason_title"
        settled_arg = "title_settled"
    else:
        keep_arg = "keep_content"
        reason_arg = "reason_content"
        settled_arg = "content_settled"
    
    # Build kwargs dictionary with the appropriate field names based on screening_phase
    update_kwargs = {
        keep_arg: False,
        reason_arg: "",
        settled_arg: False,
        **{annotation: "" for annotation in annotations}
    }
    
    db_manager.update_screening_data(
        iteration=iteration, 
        article_id=article.id, 
        **update_kwargs
    )

def choose_elements(articles, db_manager, iteration, rater, selection_stage: SelectionStage, annotation_list: list[str]): 
    """
    Choose the elements by title with ability to go back.
    selection_stage: SelectionStage - the stage of the selection - either TITLE_APPROVED or CONTENT_APPROVED
    """
    i = 0
    decisions = []  
    screening_phase = "title" if selection_stage == SelectionStage.TITLE_APPROVED else "content"
    while i < len(articles):
        print(f"\n({i+1}/{len(articles)})")
        article = articles[i]
        decision, rater_data = process_article(article, db_manager, iteration, rater, selection_stage, annotation_list)
        if decision == 'b':
            if i > 0:
                prev_index = i - 1
                prev_article = articles[prev_index]
                undo_decision(db_manager, prev_article, iteration, rater, screening_phase, annotation_list)
                
                if decisions and decisions[-1][0] == prev_index:
                    decisions.pop()
                
                i -= 1
                pretty_print(format_color_string("Going back to previous article...", "yellow", "bold"))
            else:
                pretty_print(format_color_string("Cannot go back: already at the first article.", "red", "bold"))
        elif decision is not None:
            if decision != 's':
                reason = rater_data.pop("reason")
                apply_decision(db_manager, article, iteration, rater, decision, reason, screening_phase, **rater_data)
                decisions.append((i, decision, reason, rater_data))
            i += 1
        else:
            i += 1