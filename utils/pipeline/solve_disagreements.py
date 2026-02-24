import sys
import argparse
from enum import Enum
from typing import List, Dict, Any

from ..db_management import DBManager, SelectionStage, merge_databases
from ..cli.pretty_print_utils import pretty_print, format_color_string
from .screening import introduce_annotations
from rich import print

from prompt_toolkit import Application
from prompt_toolkit.layout import Layout, HSplit, Window, ScrollablePane
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import TextArea, Label
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.filters import has_focus

# Style names for prompt_toolkit FormattedTextControl (native terminal colors)
_STYLE_GREEN = "fg:green"
_STYLE_RED = "fg:red"
_STYLE_PURPLE = "bold purple"
_STYLE_DIM = "dim"  # for "-" (not yet decided)


def _keep_value(v: Any) -> bool:
    """Normalize keep_* so 1/'1'/True = keep, 0/'0'/False/None = reject."""
    if v in (1, True, "1"):
        return True
    return False


class DisagreementStage(Enum):
    TITLE = SelectionStage.TITLE_APPROVED.value
    CONTENT = SelectionStage.CONTENT_APPROVED.value

def settle_agreements(
    iteration,
    merged_db: DBManager,
    selection_stage: SelectionStage,
    raters: List[str] | None = None,
    annotation_list: List[str] | None = None,
):
    phase = "title" if selection_stage.value == SelectionStage.TITLE_APPROVED.value else "content"
    agreements = merged_db.get_agreements_screening_data(
        iteration=iteration, 
        title_settled=(selection_stage.value == SelectionStage.CONTENT_APPROVED.value),
        content_settled=False,
        phase=phase,
        raters=raters
    )

    previous_agreement_id = ""
    for agreement in agreements:
        if agreement["id"] == previous_agreement_id:
            continue
        previous_agreement_id = agreement["id"]
        merged_db.settle_screening_data(iteration, agreement["id"], True, phase="title" if selection_stage.value == SelectionStage.TITLE_APPROVED.value else "content")
        
        # Get keep value based on phase (convert to bool if it's an int from SQLite)
        keep_key = f"keep_{phase}"
        keep_value = agreement.get(keep_key, False)
        if isinstance(keep_value, int):
            keep_value = bool(keep_value)
        
        if not keep_value:
            # All raters agreed to reject - update iterations table accordingly
            merged_db.update_iteration_data(
                iteration,
                agreement["id"],
                selected=selection_stage.value - 1,
                keep_title=False if phase == "title" else agreement.get("keep_title", False),
                keep_content=False if phase == "content" else agreement.get("keep_content", False)
            )
            
        else:
            # All raters agreed to accept - update iterations table
            merged_db.update_iteration_data(
                iteration,
                agreement["id"],
                selected=selection_stage.value,
                keep_title=bool(agreement.get("keep_title", False)) if phase == "title" else None,
                keep_content=bool(agreement.get("keep_content", False)) if phase == "content" else None,
            )
            # Content phase, agreed to keep: let user edit final annotations (same as for disagreed articles)
            if phase == "content" and annotation_list:
                final_annotations = _resolve_content_annotations(
                    merged_db, agreement["id"], iteration, annotation_list
                )
                if final_annotations is not None:
                    merged_db.create_iterations_table(annotations=annotation_list)
                    merged_db.update_iteration_data(iteration, agreement["id"], **final_annotations)
                    merged_db.create_annotations_table(annotation_list)
                    merged_db.insert_annotations_data(agreement["id"], iteration, **final_annotations)


def _show_disagreements_index(
    items: List[Dict[str, Any]],
    current_i: int,
    phase: str,
    decisions: Dict[str, str],
) -> int:
    """Show scrollable index: article title, final decision (y/n/-), and color-coded raters. Returns index to go to (0-based)."""
    max_title_len = 55
    n = len(items)
    # Header row
    header_fragments: List[tuple] = [("", "--- Index ---  [y]=keep [n]=reject [-]=pending  (↑/↓ scroll, Enter pick)\n\n")]
    header_control = FormattedTextControl(text=header_fragments, focusable=True)
    header_window = Window(content=header_control, wrap_lines=False)

    # One focusable row per item so arrow keys move focus and pane scrolls to follow
    item_windows: List[Any] = []
    for idx, item in enumerate(items):
        article_id = item.get("article_id", "")
        dec = decisions.get(article_id) or item.get("settled_decision")
        if dec == "y":
            box_style, box_text = _STYLE_GREEN, "[y]"
        elif dec == "n":
            box_style, box_text = _STYLE_RED, "[n]"
        else:
            box_style, box_text = _STYLE_DIM, "[-]"
        title = (item.get("title") or "").strip()
        if len(title) > max_title_len:
            title = title[: max_title_len - 1] + "…"
        selected_raters = [r["rater"] for r in item.get("selected_by", [])]
        rejected_raters = [r["rater"] for r in item.get("not_selected_by", [])]
        title_style = _STYLE_PURPLE if idx == current_i else ""
        row_fragments: List[tuple] = []
        row_fragments.append(("", f"  {idx + 1:3d}/{n}  "))
        row_fragments.append((box_style, box_text))
        row_fragments.append((title_style, f"  {title}"))
        row_fragments.append(("", " (screenings: "))
        for i, rater in enumerate(selected_raters):
            if i > 0:
                row_fragments.append(("", ", "))
            row_fragments.append((_STYLE_GREEN, rater))
        if selected_raters and rejected_raters:
            row_fragments.append(("", " | "))
        for i, rater in enumerate(rejected_raters):
            if i > 0:
                row_fragments.append(("", ", "))
            row_fragments.append((_STYLE_RED, rater))
        row_fragments.append(("", "\n"))
        row_control = FormattedTextControl(text=row_fragments, focusable=True)
        item_windows.append(Window(content=row_control, wrap_lines=False))

    list_height = min(12, max(6, n + 2))
    inner = HSplit([header_window] + item_windows)
    list_area = ScrollablePane(inner, height=list_height)
    go_to_prompt = f"Go to disagreement (1-{n}) or Enter to return: "
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

    @kb.add("enter", filter=has_focus(input_area))
    def _enter_in_input(event):
        raw = input_area.text.strip()
        if not raw:
            event.app.exit(result=current_i)
            return
        try:
            num = int(raw)
            if 1 <= num <= n:
                event.app.exit(result=num - 1)
        except ValueError:
            pass

    # Enter on a list row: go to that item
    for idx, win in enumerate(item_windows):
        def _make_enter_handler(go_to_index: int):
            def _handler(event: Any) -> None:
                event.app.exit(result=go_to_index)
            return _handler
        kb.add("enter", filter=has_focus(win))(_make_enter_handler(idx))

    # When focus is elsewhere (e.g. header), Enter returns without changing
    kb.add("enter", filter=has_focus(header_window))(lambda e: e.app.exit(result=current_i))

    @kb.add(Keys.Up)
    def _up(event: Any) -> None:
        event.app.layout.focus_previous()

    @kb.add(Keys.Down)
    def _down(event: Any) -> None:
        event.app.layout.focus_next()

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
        focused_element=item_windows[current_i] if n else input_area,
    )
    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=False,
        mouse_support=True,
    )

    def on_input_accept():
        raw = input_area.text.strip()
        if not raw:
            app.exit(result=current_i)
        else:
            try:
                num = int(raw)
                if 1 <= num <= n:
                    app.exit(result=num - 1)
            except ValueError:
                pass

    input_area.buffer.accept_handler = on_input_accept

    out = app.run()
    return out if out is not None else current_i


def _gather_annotations_default(rows: List[Dict[str, Any]], annotation_list: List[str]) -> Dict[str, str]:
    """Build default annotation values by merging all raters' values per field (unique, comma-joined)."""
    result = {}
    for field in annotation_list:
        parts = []
        seen = set()
        for row in rows:
            val = (row.get(field) or "").strip()
            if not val:
                continue
            for part in (p.strip() for p in val.replace(";", ",").split(",") if p.strip()):
                if part not in seen:
                    seen.add(part)
                    parts.append(part)
        result[field] = ", ".join(parts) if parts else ""
    return result


def _resolve_content_annotations(
    merged_db: DBManager,
    article_id: str,
    iteration: int,
    annotation_list: List[str],
) -> Dict[str, str] | None:
    """
    Show all raters' annotations for this article and let the user decide final values.
    Returns final annotation dict to save, or None if user cancelled.
    """
    if not annotation_list:
        return None
    rows = merged_db.get_screening_rows_for_article(article_id, iteration)
    if not rows:
        return _gather_annotations_default([], annotation_list)

    title = (rows[0].get("title") or "").strip() or article_id
    pretty_print(format_color_string("\n--- Annotations from raters ---", "magenta", "bold"))
    pretty_print(format_color_string(f"Article: {article_id}", "cyan", ""))
    pretty_print(format_color_string(f"Title: {title}", "magenta", "bold"))
    pretty_print("")
    # Show each field with each rater's value
    for field in annotation_list:
        pretty_print(format_color_string(f"\n{field}:", "cyan", "bold"))
        for row in rows:
            rater = row.get("rater") or "?"
            val = (row.get(field) or "").strip()
            rater_str = format_color_string(rater, "green", "")
            pretty_print(f"  {rater_str}: {val or '(empty)'}")
    pretty_print("")

    default_values = _gather_annotations_default(rows, annotation_list)
    result = introduce_annotations({}, annotation_list, initial_values=default_values)
    # On cancel, introduce_annotations returns {} (falsy); on save it returns dict with keys
    if not result:
        return None
    return {k: (result.get(k) or "").strip() for k in annotation_list}


def solve_disagreements(
    iteration,
    merged_db: DBManager,
    selection_stage: SelectionStage,
    annotation_list: List[str] | None = None,
):
    phase = "title" if selection_stage.value == SelectionStage.TITLE_APPROVED.value else "content"
    print(f"Phase: {phase}")
    # Check if there's only one rater in the whole database
    table_name = "screening"
    # Get the unique raters for this iteration and phase
    merged_db.cursor.execute(f"SELECT DISTINCT rater FROM {table_name} WHERE iteration = ? AND keep_{phase} IS NOT NULL AND keep_{phase} != ''", (iteration,))
    raters = merged_db.cursor.fetchall()
    raters = [r[0] for r in raters]
    if len(raters) == 1:
        # Only one rater - skip manual disagreements and update iterations table directly
        # Get all screening data for this iteration and phase
        screening_data = merged_db.get_screening_data(
            iteration=iteration,
            title_settled=(selection_stage == SelectionStage.CONTENT_APPROVED),
            content_settled=False
        )
        
        # Group by article ID (should only be one entry per article since there's only one rater)
        for screening_entry in screening_data:
            article_id = screening_entry["id"]
            keep_key = f"keep_{phase}"
            keep_value = screening_entry.get(keep_key, False)
            if isinstance(keep_value, int):
                keep_value = bool(keep_value)
            
            # Settle the screening data
            merged_db.settle_screening_data(iteration, article_id, True, phase=phase)
            
            # Update iterations table based on the single rater's decision
            if not keep_value:
                # Rater rejected - update iterations table accordingly
                merged_db.update_iteration_data(
                    iteration,
                    article_id,
                    selected=selection_stage.value - 1,
                    keep_title=False if phase == "title" else bool(screening_entry.get("keep_title", False)) if phase == "title" else None,
                    keep_content=False if phase == "content" else bool(screening_entry.get("keep_content", False)) if phase == "content" else None
                )
            else:
                # Rater accepted - update iterations table
                merged_db.update_iteration_data(
                    iteration,
                    article_id,
                    selected=selection_stage.value,
                    keep_title=bool(screening_entry.get("keep_title", False)) if phase == "title" else None,
                    keep_content=bool(screening_entry.get("keep_content", False)) if phase == "content" else None
                )
        
        # Skip manual disagreement resolution since there's only one rater
        return

    # Sync iterations from screening for all already-settled articles (fixes out-of-sync DBs)
    merged_db.sync_iteration_from_settled_screening(iteration, phase, selection_stage)
    settle_agreements(iteration, merged_db, selection_stage, raters=raters, annotation_list=annotation_list)

    # Fetch all disagreement articles (unsettled and already settled) so we can show full list and allow changing settled ones
    disagreements_raw = merged_db.get_all_disagreements_screening_data(iteration=iteration, phase=phase)

    clustered_disagreements: Dict[str, List[Dict[str, Any]]] = {}
    for disagreement in disagreements_raw:
        aid = disagreement["id"]
        if aid not in clustered_disagreements:
            clustered_disagreements[aid] = []
        clustered_disagreements[aid].append(disagreement)

    # Build a list of items (one per article) for index-based navigation. Include both unsettled and already-settled.
    disagreement_items: List[Dict[str, Any]] = []
    for article_id, rows in clustered_disagreements.items():
        selected_by = [r for r in rows if _keep_value(r.get(f"keep_{phase}"))]
        not_selected_by = [r for r in rows if not _keep_value(r.get(f"keep_{phase}"))]
        if not selected_by or not not_selected_by:
            continue  # all agreed (all keep or all reject) – skip
        title = (rows[0].get("title") or "").strip() if rows else ""
        phase_settled_key = f"{phase}_settled"
        is_settled = bool(rows[0].get(phase_settled_key) in (1, True, "1") if rows else False)
        # Already-settled decision from iterations (so we can show it and allow changing via index)
        settled_decision: str | None = None
        if is_settled:
            if phase == "title":
                keep = merged_db.get_keep_title(article_id, iteration)
            else:
                keep = merged_db.get_keep_content(article_id, iteration)
            if keep is not None:
                settled_decision = "y" if keep else "n"
        disagreement_items.append({
            "article_id": article_id,
            "title": title,
            "selected_by": selected_by,
            "not_selected_by": not_selected_by,
            "is_settled": is_settled,
            "settled_decision": settled_decision,
        })

    disagreement_items.sort(key=lambda x: (not x["is_settled"], x["article_id"]))   
    first_unsettled_i = next((idx for idx, it in enumerate(disagreement_items) if not it["is_settled"]), 0)
    i = first_unsettled_i
    current_run_decisions: Dict[str, str] = {}
    while i < len(disagreement_items):
        item = disagreement_items[i]
        article_id = item["article_id"]
        selected_by = item["selected_by"]
        not_selected_by = item["not_selected_by"]

        print(f"\n({i + 1}/{len(disagreement_items)})")
        # Show settled decision: from this run or from DB (already settled in a previous run)
        settled_dec = current_run_decisions.get(article_id) or item.get("settled_decision")
        if settled_dec:
            current_decision_color = "green" if settled_dec == "y" else "red"
            current_decision_text = "Keep" if settled_dec == "y" else "Reject"
            current_decision = format_color_string(current_decision_text, current_decision_color, "bold")
            print(f"Currently Settled Decision: {current_decision}")
        print(f"Article ID: {article_id}")
        title_string = format_color_string(item["title"], "magenta", "bold")
        print(f"Title: {title_string}")
        selected_by_raters = [r["rater"] for r in selected_by]
        print("=================================")
        print(f"Selected by: {selected_by_raters}")
        for disagreement in selected_by:
            reason = disagreement.get(f"reason_{phase}") or "No reason provided"
            rater = disagreement["rater"]
            disagreement_string = format_color_string(rater, "green", "bold")
            reason_string = format_color_string(reason, "green", "")
            pretty_print(f"{disagreement_string}: {reason_string}")
        print("--------------------------------")
        not_selected_by_raters = [r["rater"] for r in not_selected_by]
        print(f"Not selected by: {not_selected_by_raters}")
        for disagreement in not_selected_by:
            rater = disagreement["rater"]
            reason = disagreement.get(f"reason_{phase}") or "No reason provided"
            disagreement_string = format_color_string(rater, "red", "bold")
            reason_string = format_color_string(reason, "red", "")
            pretty_print(f"{disagreement_string}: {reason_string}")
        print("=================================\n")
        while True:
            user_input = input(
                "Do you want to keep this element? (y/n/s for skip/i for index/b for back): "
            ).strip().lower()
            if user_input == "i":
                i = _show_disagreements_index(
                    disagreement_items, i, phase, current_run_decisions
                )
                break
            if user_input == "b":
                i = max(0, i - 1)
                break
            if user_input == "y":
                current_run_decisions[article_id] = "y"
                merged_db.settle_screening_data(iteration, article_id, True, phase=phase)
                if phase == "title":
                    merged_db.update_iteration_data(
                        iteration, article_id, selected=selection_stage.value, keep_title=True
                    )
                else:
                    merged_db.update_iteration_data(
                        iteration, article_id, selected=selection_stage.value, keep_content=True
                    )
                    # Content phase: let user see raters' annotations and decide final values (CLI equivalent of webapp step)
                    if annotation_list:
                        final_annotations = _resolve_content_annotations(
                            merged_db, article_id, iteration, annotation_list
                        )
                        if final_annotations is not None:
                            merged_db.create_iterations_table(annotations=annotation_list)
                            merged_db.update_iteration_data(iteration, article_id, **final_annotations)
                            merged_db.create_annotations_table(annotation_list)
                            merged_db.insert_annotations_data(article_id, iteration, **final_annotations)
                i += 1
                break
            if user_input == "n":
                current_run_decisions[article_id] = "n"
                merged_db.settle_screening_data(iteration, article_id, True, phase=phase)
                if phase == "title":
                    merged_db.update_iteration_data(
                        iteration, article_id, selected=selection_stage.value - 1, keep_title=False
                    )
                else:
                    merged_db.update_iteration_data(
                        iteration, article_id, selected=selection_stage.value - 1, keep_content=False
                    )
                i += 1
                break
            if user_input == "s":
                i += 1
                break
            print("Please enter 'y' for yes, 'n' for no, 's' for skip, 'i' for index, or 'b' for back.")
