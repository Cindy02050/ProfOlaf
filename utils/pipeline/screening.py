import json
from utils.cli.pretty_print_utils import (
    pretty_print, 
    format_color_string, 
    prompt_input
)
from prompt_toolkit import Application
from prompt_toolkit.layout import Layout, HSplit
from prompt_toolkit.widgets import TextArea, Button, Label
from prompt_toolkit.key_binding import KeyBindings

from ..db_management import SelectionStage, ArticleData
from typing import List, Optional

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

def introduce_annotations(user_data: dict, annotations: list, initial_values: Optional[dict] = None) -> dict:
    """
    Collect annotation data from the user using an interactive form.
    All fields are displayed at once, user can navigate with Tab/Shift+Tab,
    fill fields in any order, and submit at the end.
    If initial_values is provided (e.g. from previous screening), fields are pre-filled for editing.
    """
    if not annotations or len(annotations) == 0:
        return user_data
    
    initial_values = initial_values or {}
    
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
    
    # Create form fields for each annotation (pre-fill when editing)
    fields = {}
    field_widgets = []
    
    for annotation in annotations:
        initial_text = (initial_values.get(annotation) or "").strip()
        if isinstance(initial_text, bytes):
            initial_text = initial_text.decode("utf-8", errors="replace")
        field = TextArea(
            prompt=f"{annotation}: ",
            text=initial_text,
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

def _previous_data_from_row(row: dict, selection_stage: SelectionStage, annotation_list: list[str]) -> Optional[dict]:
    """Build a previous_data dict from a screening row for pre-filling the form."""
    if not row:
        return None
    phase = "title" if selection_stage == SelectionStage.TITLE_APPROVED else "content"
    keep_key = f"keep_{phase}"
    reason_key = f"reason_{phase}"
    keep_val = row.get(keep_key)
    keep = None
    if keep_val is not None:
        keep = bool(keep_val) if isinstance(keep_val, (bool, int)) else (str(keep_val).strip() in ("1", "true", "yes"))
    reason = (row.get(reason_key) or "") or ""
    if hasattr(reason, "decode"):
        reason = reason.decode("utf-8", errors="replace") if isinstance(reason, bytes) else str(reason)
    out = {"keep": keep, "reason": reason}
    for ann in annotation_list:
        v = row.get(ann) or ""
        if hasattr(v, "decode"):
            v = v.decode("utf-8", errors="replace") if isinstance(v, bytes) else str(v)
        out[ann] = v
    return out


def process_article(
    article: ArticleData,
    previously_screened: bool,
    selection_stage: SelectionStage,
    annotation_list: list[str],
    previous_data: Optional[dict] = None,
):
    """
    Process a single article and return the decision made.
    If previous_data is provided (article was previously screened), the form is shown with
    previous keep/reason/annotations pre-filled so the user can edit.
    Returns: tuple (decision, reason) where decision is 'y', 'n', 's', or 'b'
    """
    title_string = format_color_string(article.title, "magenta", "bold")

    # When editing previous screening, show the article regardless of stage
    if previous_data is None and not is_correct_article_stage(article, selection_stage):
        pretty_print(f"Skipping Article {title_string}")
        return None, None

    article_info_string = f"Title: {title_string}\n"
    article_info_string += f"ID: {article.id}\n"
    article_info_string += f"Url: {article.pub_url}\n" if selection_stage == SelectionStage.CONTENT_APPROVED else ""

    if previous_data:
        prev_keep = "y" if previous_data.get("keep") else "n"
        prev_reason = (previous_data.get("reason") or "").strip() or "(none)"
        article_info_string += format_color_string(f"\n[Previously screened] Keep: {prev_keep}  Reason: {prev_reason}\n", "cyan", "")

    # Default keep/reason from previous screening (so they show as pre-filled and Enter keeps them)
    default_keep = None
    default_reason = ""
    if previous_data:
        if previous_data.get("keep") is not None:
            default_keep = "y" if previous_data.get("keep") else "n"
        default_reason = (previous_data.get("reason") or "").strip()

    while True:
        pretty_print(article_info_string)
        prompt_keep = "Do you want to keep this element? (y/n/s for skip/b for back/i for index)"
        user_input = prompt_input(prompt_keep, default=default_keep).strip().lower() if default_keep else prompt_input(prompt_keep).strip().lower()
        if user_input == "i":
            return "i", None
        if user_input == "y":
            reason_prompt = "Please enter the reason for the selection (enter to keep previous or skip)"
            user_reason = prompt_input(reason_prompt, default=default_reason).strip() if default_reason else prompt_input(reason_prompt).strip()
            if not user_reason and default_reason:
                user_reason = default_reason
            user_data = {"reason": user_reason}
            if is_annotations_to_fill(annotation_list, selection_stage):
                initial_ann = {k: v for k, v in (previous_data or {}).items() if k in annotation_list} or None
                user_data = introduce_annotations(user_data, annotation_list, initial_values=initial_ann)
            return "y", user_data
        elif user_input == "n":
            reason_prompt = "Please enter the reason for the rejection (enter to keep previous or skip)"
            user_reason = prompt_input(reason_prompt, default=default_reason).strip() if default_reason else prompt_input(reason_prompt).strip()
            if not user_reason and default_reason:
                user_reason = default_reason
            user_data = {"reason": user_reason}
            return "n", user_data
        elif user_input == "s":
            return "s", None
        elif user_input == "b":
            return "b", None
        else:
            pretty_print("Please enter 'y' for yes, 'n' for no, 's' for skip, 'b' for back, or 'i' for index.")

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

def _previously_screened_article(article: ArticleData, existing_screening_data: List[dict], current_run_data: Optional[dict] = None) -> bool:
    """True if article was screened before (in DB at start or in current run)."""
    if current_run_data and article.id in current_run_data:
        return True
    return article.id in [screening_data["id"] for screening_data in existing_screening_data]

def _previous_data_for_article(
    article_id: str,
    existing_screening_data: List[dict],
    selection_stage: SelectionStage,
    annotation_list: list[str],
    current_run_data: Optional[dict] = None,
) -> Optional[dict]:
    """Get previous_data for an article: prefer current-run entry, else from existing_screening_data."""
    if current_run_data and article_id in current_run_data:
        return current_run_data[article_id]
    for row in existing_screening_data:
        if row.get("id") == article_id:
            return _previous_data_from_row(row, selection_stage, annotation_list)
    return None


def _decision_for_article(
    article_id: str,
    existing_screening_data: List[dict],
    current_run_data: Optional[dict],
    screening_phase: str,
) -> str:
    """Return 'y', 'n', or '-' for the article's current decision."""
    if current_run_data and article_id in current_run_data:
        keep = current_run_data[article_id].get("keep")
        return "y" if keep else "n" if keep is False else "-"
    for row in existing_screening_data:
        if row.get("id") == article_id:
            keep_val = row.get(f"keep_{screening_phase}")
            if keep_val is None:
                return "-"
            return "y" if (keep_val == 1 or keep_val is True) else "n"
    return "-"


def _show_index_and_jump(
    articles: List[ArticleData],
    existing_screening_data: List[dict],
    current_run_data: dict,
    screening_phase: str,
    current_i: int,
) -> int:
    """Show scrollable index (position, title, decision) and prompt to jump. Returns index to go to (0-based)."""
    max_title_len = 70
    n_articles = len(articles)
    lines = ["--- Index ---", ""]
    for idx, a in enumerate(articles):
        title = (a.title or "").strip()
        if len(title) > max_title_len:
            title = title[: max_title_len - 1] + "…"
        dec = _decision_for_article(a.id, existing_screening_data, current_run_data, screening_phase)
        marker = " ←" if idx == current_i else ""
        lines.append(f"  {idx + 1:3d}/{n_articles}  [{dec}]  {title}{marker}")
    index_text = "\n".join(lines)

    # Scrollable list (read-only) + input at bottom; keep height small so it fits small terminals
    list_height = min(8, max(4, n_articles + 2))
    list_area = TextArea(
        text=index_text,
        read_only=True,
        scrollbar=True,
        multiline=True,
        focusable=True,
        height=list_height,
    )
    go_to_prompt = f"Go to article (1-{n_articles}) or Enter to return: "
    input_area = TextArea(
        prompt=go_to_prompt,
        multiline=False,
        focusable=True,
        height=1,
    )

    kb = KeyBindings()

    @kb.add("c-c")
    def _(event):
        event.app.exit(result=current_i)

    @kb.add("enter")
    def _(event):
        if event.app.layout.current_control == input_area:
            raw = input_area.text.strip()
            if not raw:
                event.app.exit(result=current_i)
                return
            try:
                num = int(raw)
                if 1 <= num <= n_articles:
                    event.app.exit(result=num - 1)
            except ValueError:
                pass

    @kb.add("tab")
    def _(event):
        event.app.layout.focus_next()

    @kb.add("s-tab")
    def _(event):
        event.app.layout.focus_previous()

    layout = Layout(
        HSplit([
            list_area,
            Label(text=""),
            input_area,
        ]),
        focused_element=list_area,
    )
    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=False,
        mouse_support=True,
    )
    out = app.run()
    return out if out is not None else current_i


def choose_elements(articles: List[ArticleData], existing_screening_data: List[dict], db_manager, iteration, rater, selection_stage: SelectionStage, annotation_list: list[str]):
    """
    Choose the elements by title with ability to go back.
    Previously screened articles (from DB or from current run) are shown with options pre-filled for editing.
    When you go back (b), the article you return to shows the data you just entered in this run.
    """
    # Deduplicate by article id (iterations table can have duplicate rows for same id); keep first occurrence
    seen_ids: set[str] = set()
    deduped: List[ArticleData] = []
    for a in articles:
        if a.id in seen_ids:
            continue
        seen_ids.add(a.id)
        deduped.append(a)
    articles = deduped
    decisions = []
    # article_id -> { keep, reason, **annotations } for decisions made in this run (so "go back" shows them)
    current_run_data: dict[str, dict] = {}
    screening_phase = "title" if selection_stage == SelectionStage.TITLE_APPROVED else "content"
    # Sort so previously screened articles come first (for editing)
    articles.sort(key=lambda x: (0 if _previously_screened_article(x, existing_screening_data, None) else 1))
    # Start at the first not-previously-evaluated article (at start, only DB data counts)
    i = 0
    while i < len(articles) and _previously_screened_article(articles[i], existing_screening_data, None):
        i += 1
    while i < len(articles):
        print(f"\n({i+1}/{len(articles)})")
        article = articles[i]
        previously_screened = _previously_screened_article(article, existing_screening_data, current_run_data)
        previous_data = _previous_data_for_article(
            article.id, existing_screening_data, selection_stage, annotation_list, current_run_data
        )
        decision, rater_data = process_article(article, previously_screened, selection_stage, annotation_list, previous_data=previous_data)
        if decision == "b":
            if i > 0:
                # Just move back to edit the previous article; do not undo (so DB and next run keep that decision)
                i -= 1
                pretty_print(format_color_string("Going back to previous article...", "yellow", "bold"))
            else:
                pretty_print(format_color_string("Cannot go back: already at the first article.", "red", "bold"))
        elif decision == "i":
            i = _show_index_and_jump(articles, existing_screening_data, current_run_data, screening_phase, i)
        elif decision is not None:
            if decision != "s":
                reason = rater_data.pop("reason")
                apply_decision(db_manager, article, iteration, rater, decision, reason, screening_phase, **rater_data)
                current_run_data[article.id] = {"keep": decision == "y", "reason": reason, **rater_data}
                decisions.append((i, decision, reason, rater_data))
            i += 1
        else:
            i += 1