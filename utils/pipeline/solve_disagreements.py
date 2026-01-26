import sys
import argparse
from enum import Enum
from ..db_management import DBManager, SelectionStage, merge_databases
from ..cli.pretty_print_utils import pretty_print, format_color_string

class DisagreementStage(Enum):
    TITLE = SelectionStage.TITLE_APPROVED.value
    CONTENT = SelectionStage.CONTENT_APPROVED.value

def settle_agreements(iteration, merged_db: DBManager, selection_stage: SelectionStage):
    phase = "title" if selection_stage == SelectionStage.TITLE_APPROVED else "content"
    agreements = merged_db.get_agreements_screening_data(
        iteration=iteration, 
        title_settled=(selection_stage == SelectionStage.CONTENT_APPROVED),
        content_settled=False,
        phase=phase
    )

    previous_agreement_id = ""
    for agreement in agreements:
        if agreement["id"] == previous_agreement_id:
            continue
        previous_agreement_id = agreement["id"]
        merged_db.settle_screening_data(iteration, agreement["id"], True, phase="title" if selection_stage == SelectionStage.TITLE_APPROVED else "content")
        
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
                keep_title=False if phase == "title" else bool(agreement.get("keep_title", False)),
                keep_content=False if phase == "content" else bool(agreement.get("keep_content", False))
            )
            continue
        
        # All raters agreed to accept - update iterations table
        merged_db.update_iteration_data(
            iteration, 
            agreement["id"], 
            selected=selection_stage.value, 
            keep_title=bool(agreement.get("keep_title", False)), 
            keep_content=bool(agreement.get("keep_content", False))
        )
            
def solve_disagreements(iteration, merged_db: DBManager, selection_stage: SelectionStage):
    phase = "title" if selection_stage.value == SelectionStage.TITLE_APPROVED.value else "content"

    # Check if there's only one rater in the whole database
    table_name = "screening"
    merged_db.cursor.execute(f"SELECT COUNT(DISTINCT rater) FROM {table_name}")
    unique_rater_count = merged_db.cursor.fetchone()[0]
    
    if unique_rater_count == 1:
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
                    keep_title=False if phase == "title" else bool(screening_entry.get("keep_title", False)),
                    keep_content=False if phase == "content" else bool(screening_entry.get("keep_content", False))
                )
            else:
                # Rater accepted - update iterations table
                merged_db.update_iteration_data(
                    iteration,
                    article_id,
                    selected=selection_stage.value,
                    keep_title=bool(screening_entry.get("keep_title", False)),
                    keep_content=bool(screening_entry.get("keep_content", False))
                )
        
        # Skip manual disagreement resolution since there's only one rater
        return

    settle_agreements(iteration, merged_db, selection_stage)

    disagreements = merged_db.get_disagreements_screening_data(
        iteration=iteration, 
        title_settled=(selection_stage == SelectionStage.CONTENT_APPROVED),
        content_settled=False,
        phase=phase
    )
    
    clustered_disagreements = {}
    for disagreement in disagreements:
        if disagreement["id"] not in clustered_disagreements:
            clustered_disagreements[disagreement["id"]] = [disagreement]
        else:
            clustered_disagreements[disagreement["id"]].append(disagreement)
                
    for article_id, disagreements in clustered_disagreements.items():
        selected_by, not_selected_by = [], []
        for disagreement in disagreements:
            if disagreement[f"keep_{phase}"]:
                selected_by.append(disagreement)
            else:
                not_selected_by.append(disagreement)
        
        print(f"Article ID: {article_id}")
        title_string = format_color_string(disagreement["title"], "magenta", "bold")
        print(f"Title: {title_string}")
        selected_by_raters = [disagreement["rater"] for disagreement in selected_by]
        print(f"Selected by: {selected_by_raters}")

        for disagreement in selected_by:
            reason = disagreement[f"reason_{phase}"] if disagreement[f"reason_{phase}"] != "" else "No reason provided"
            rater = disagreement["rater"]
            disagreement_string = format_color_string(rater, "green", "bold")
            reason_string = format_color_string(reason, "green", "")
            pretty_print(f"{disagreement_string}: {reason_string}")
        print("\n--------------------------------")
        not_selected_by_raters = [disagreement["rater"] for disagreement in not_selected_by]
        print(f"Not selected by: {not_selected_by_raters}")
        for disagreement in not_selected_by:
            rater = disagreement["rater"]
            reason = disagreement[f"reason_{phase}"] if disagreement[f"reason_{phase}"] != "" else "No reason provided"
            disagreement_string = format_color_string(rater, "red", "bold")
            reason_string = format_color_string(reason, "red", "")
            pretty_print(f"{disagreement_string}: {reason_string}")
        
        while True:
            user_input = input(f"Do you want to keep this element? (y/n/s for skip): ").strip().lower()
            if user_input == 'y':
                if phase == "title":
                    merged_db.update_iteration_data(iteration, article_id, selected=selection_stage.value, keep_title=True)
                else:
                    merged_db.update_iteration_data(iteration, article_id, selected=selection_stage.value, keep_content=True)
                break
            elif user_input == 'n':
                if phase == "title":
                    merged_db.update_iteration_data(iteration, article_id, selected=selection_stage.value-1, keep_title=False)
                else:
                    merged_db.update_iteration_data(iteration, article_id, selected=selection_stage.value-1, keep_content=False)
                break
            elif user_input == 's':
                break
            else:
                print("Please enter 'y' for yes, 'n' for no, or 's' for skip.")

def synchronize_screenings(iteration, merged_db: DBManager, selection_stage: SelectionStage):
    """
    Solve the disagreements between multiple raters.
    """
    if selection_stage not in [DisagreementStage.TITLE, DisagreementStage.CONTENT]:
        raise ValueError(f"Selection stage {selection_stage} is not valid")
    
    settle_agreements(iteration, merged_db, selection_stage)

    selected_pubs = merged_db.get_selected_pubs(iteration)

    disagreements = {}
    for rater, pubs in selected_pubs.items():
        rater_unique_pubs = []
        for pub in pubs:
            selected_by_all = all(pub in selected_pubs[other_rater] for other_rater in search_dbs if other_rater != rater)
            if not selected_by_all:
                rater_unique_pubs.append(pub)
            else:
                for _, db_manager in db_managers.items():
                    db_manager.settle_screening_data(iteration, pub["id"], settle_title, settle_content)
        if rater_unique_pubs:
            disagreements[rater] = rater_unique_pubs
    
    all_disagreements = []
    for pubs in disagreements.values():
        all_disagreements.extend(pubs)
    all_disagreements = list(set(all_disagreements))
    
    for i, disagreement in enumerate(all_disagreements):
        print(f"({i + 1}/{len(all_disagreements)})")
        selected_by = []
        not_selected_by = []
        reasons = {}
        for rater in search_dbs:
            original_rating = db_managers[rater].get_iteration_data(iteration=iteration, id=disagreement.id)[0]
            reasons[rater.replace(".db", "")] = original_rating.title_reason if selection_stage == DisagreementStage.TITLE else original_rating.content_reason
            if int(original_rating.selected) == int(selection_stage.value):
                selected_by.append(rater.replace(".db", ""))
            else:
                not_selected_by.append(rater.replace(".db", ""))

        print("selected by: ", selected_by)
        print("not selected by: ", not_selected_by)
        print("\n--------------------------------")
        title_string = format_color_string(disagreement.title, "magenta", "bold")
        url_string = format_color_string(disagreement.pub_url, "blue", "bold")
        selected_by_string = format_color_string('Selected by:', 'green', 'bold')
        pretty_print(f"Title: {title_string}")
        pretty_print(f"Url: {url_string}")
        pretty_print(f"{selected_by_string}")
        for rater in selected_by:
            reason = reasons[rater] if reasons[rater] != "" else "No reason provided"
            rater_string = format_color_string(rater, "green", "bold")
            reason_string = format_color_string(reason, "green", "")
            pretty_print(f"{rater_string}: {reason_string}")
        not_selected_by_string = format_color_string('Not selected by:', 'red', 'bold')
        pretty_print(f"{not_selected_by_string}:")
        for rater in not_selected_by:
            reason = reasons[rater] if reasons[rater] != "" else "No reason provided"
            rater_string = format_color_string(rater, "red", "bold")
            reason_string = format_color_string(reason, "red", "")
            pretty_print(f"{rater_string}: {reason_string}")

        while True:
            user_input = input(f"Do you want to keep this element? (y/n/s for skip): ").strip().lower()
            if user_input == 'y':
                for rater in search_dbs:
                    reasonings = {rater.replace(".db", ""): reasons[rater.replace(".db", "")] for rater in search_dbs}
                    if selection_stage == DisagreementStage.TITLE:
                        db_managers[rater].update_iteration_data(iteration, disagreement.id, selected=selection_stage.value, title_reason=reasonings)
                    else:
                        db_managers[rater].update_iteration_data(iteration, disagreement.id, selected=selection_stage.value, content_reason=reasonings)
                    db_managers[rater].settle_screening_data(iteration, disagreement.id, True, False)
                break
            elif user_input == 'n':
                for rater in search_dbs:
                    db_managers[rater].update_iteration_data(iteration, disagreement.id, selected=selection_stage.value-1)
                    db_managers[rater].settle_screening_data(iteration, disagreement.id, settle_title, settle_content)
                break
            elif user_input == 's':
                break
            else:
                print("Please enter 'y' for yes, 'n' for no, or 's' for skip.")
