import argparse
import json
from enum import Enum
import random
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.db_management import (
    DBManager, 
    initialize_db, 
    ArticleData,
    SelectionStage,
)

class Phase(Enum):
    DEFAULT = "default"
    TITLE_SCREENED = "title_screened"
    TITLE_SOLVED = "title_solved"
    CONTENT_SCREENED = "content_screened"
    CONTENT_SOLVED = "content_solved"



def parse_args():
    parser = argparse.ArgumentParser(description='Generate DB example')
    parser.add_argument('--db_path', help='db path', type=str, required=True)
    parser.add_argument('--phase', help='phase', type=Phase, required=True)
    parser.add_argument('--length', help='length', type=int, required=True)
    parser.add_argument('--search_conf', help='search conf', type=str, required=True)
    parser.add_argument('--iterations', help='iterations', type=int, required=True)
    # multiple raters (each value is one rater name)
    parser.add_argument('--raters', help='raters', type=str, required=True, nargs='+')
    args = parser.parse_args()
    return args


def generate_empty_db(db_path: str, search_conf: dict):
    db_manager = initialize_db(db_path, search_conf)
    return db_manager

def add_iteration_data(db_manager: DBManager, index: int, iteration: int, search_conf: dict, selected: SelectionStage):
    db_manager.insert_iteration_data(
                [ArticleData(
                    id=f"article_{index}", 
                    title=f"title_{index}", 
                    authors=[f"authors_{index}"], 
                    venue=f"venue_{index}", 
                    pub_year=random.randint(2020, 2025), 
                    pub_url=f"https://www.example.com/article_{index}", 
                    num_citations=random.randint(0, 100), 
                    citedby_url=f"https://www.example.com/citedby_{index}", 
                    url_related_articles=f"https://www.example.com/related_{index}",
                    iteration=iteration,
                    selected=selected,
                    search_method=search_conf["search_method"],
                )]
            )

def add_screening_data(
    db_manager: DBManager,
    index: int,
    iteration: int,
    rater: str,
    screening_phase: str,
    settled: bool,
    keep: bool,
    reason: str,
    search_conf: dict,
    title: str | None = None,
    **annotations: str,
) -> None:
    db_manager.insert_screening_data(
        article_id=f"article_{index}",
        rater=rater,
        iteration=iteration,
        keep=keep,
        reason=reason,
        settled=settled,
        screening_phase=screening_phase,
        title=title if title is not None else f"title_{index}",
        **annotations
    )

def generate_annotations(search_conf: dict) -> dict:
    return {
        search_conf["annotations"][i]: random.choice(["annotation_1", "annotation_2", "annotation_3", "annotation_4", "annotation_5"]) 
        for i in range(len(search_conf["annotations"]))
    }

def populate_default(db_manager: DBManager, length: int, iterations: int, search_conf: dict):
    for iteration in range(iterations):
        for index in range(length):
            add_iteration_data(
                db_manager, 
                index=index, 
                iteration=iteration, 
                search_conf=search_conf,
                selected=SelectionStage.NOT_SELECTED,
            )

def populate_title_screened(db_manager: DBManager, length: int, raters: list[str], search_conf: dict):
    number_of_approved = int(input(f"Generating {length} articles for title screening. Enter number of articles approved: "))
    
    for i in range(number_of_approved):
        add_iteration_data(
            db_manager, 
            index=i, 
            iteration=1, 
            search_conf=search_conf,
            selected=SelectionStage.METADATA_APPROVED,
        )
        for rater in raters:
            add_screening_data(
                db_manager, 
                index=i, 
                iteration=1, 
                rater=rater, 
                screening_phase="title", 
                settled=False, 
                keep=random.choice([True, False]), 
                reason=random.choice(["reason_1", "reason_2", "reason_3"]),
                search_conf=search_conf,
            )

def populate_title_solved(db_manager: DBManager, length: int, raters: list[str], search_conf: dict):
    for i in range(length):
        selected = random.choice([SelectionStage.METADATA_APPROVED, SelectionStage.TITLE_APPROVED])
        add_iteration_data(
            db_manager, 
            index=i, 
            iteration=1, 
            search_conf=search_conf,
            selected=selected,
        )

        one_rater_approved = False
        one_rater_rejected = False
        for rater in raters:
            if selected == SelectionStage.TITLE_APPROVED and not one_rater_approved:
                keep = True
                one_rater_approved = True
            elif selected == SelectionStage.METADATA_APPROVED and not one_rater_rejected:
                keep = False
                one_rater_rejected = True
            else:
                keep = random.choice([True, False])
            add_screening_data(
                db_manager, 
                index=i, 
                iteration=1, 
                rater=rater, 
                screening_phase="title", 
                settled=True, 
                keep=keep, 
                reason=random.choice(["reason_1", "reason_2", "reason_3"]),
                search_conf=search_conf,
            )

def populate_content_screened(db_manager: DBManager, length: int, raters: list[str], search_conf: dict):
    number_of_approved = int(input(f"Generating {length} articles for title screening. Enter number of articles approved: "))
    
    for i in range(number_of_approved):
        add_iteration_data(
            db_manager, 
            index=i, 
            iteration=1, 
            search_conf=search_conf,
            selected=SelectionStage.TITLE_APPROVED,
        )
        for rater in raters:
            keep = random.choice([True, False])
            if keep:
                annotations = generate_annotations(search_conf)
            else:
                annotations = {}
            add_screening_data(
                db_manager, 
                index=i, 
                iteration=1, 
                rater=rater, 
                screening_phase="title", 
                settled=False, 
                keep=keep, 
                reason=random.choice(["reason_1", "reason_2", "reason_3"]),
                search_conf=search_conf,
                **annotations
            )

def populate_content_solved(db_manager: DBManager, length: int, raters: list[str], search_conf: dict):
    for i in range(length):
        selected = random.choice([SelectionStage.METADATA_APPROVED, SelectionStage.TITLE_APPROVED])
        add_iteration_data(
            db_manager, 
            index=i, 
            iteration=1, 
            search_conf=search_conf,
            selected=selected,
        )

        one_rater_approved = False
        one_rater_rejected = False
        all_annotations = []
        for rater in raters:
            if selected == SelectionStage.TITLE_APPROVED and not one_rater_approved:
                keep = True
                one_rater_approved = True
            elif selected == SelectionStage.METADATA_APPROVED and not one_rater_rejected:
                keep = False
                one_rater_rejected = True
            else:
                keep = random.choice([True, False])
            if keep:
                annotations = generate_annotations(search_conf)
            else:
                annotations = {}
            all_annotations.append(annotations)
            add_screening_data(
                db_manager, 
                index=i, 
                iteration=1, 
                rater=rater, 
                screening_phase="title", 
                settled=True, 
                keep=keep, 
                reason=random.choice(["reason_1", "reason_2", "reason_3"]),
                search_conf=search_conf,
                **annotations
            )
        final_annotations = {}
        if selected == SelectionStage.CONTENT_APPROVED:
            final_annotations = {
                search_conf["annotations"][i]: random.choice([annotation[i] for annotation in all_annotations])
                for i in range(len(search_conf["annotations"]))
            }
        db_manager.update_iteration_data(
            iteration=1, 
            article_id=f"article_{i}", 
            **final_annotations
        )
    
def populate_db(db_manager: DBManager, phase: Phase, length: int, iterations: int, raters: list[str], search_conf: dict):
    match phase:
        case Phase.DEFAULT:
            populate_default(db_manager, length, iterations, search_conf)
        case Phase.TITLE_SCREENED:
            populate_title_screened(db_manager, length, raters, search_conf)
        case Phase.TITLE_SOLVED:
            populate_title_solved(db_manager, length, raters, search_conf)
        case Phase.CONTENT_SCREENED:
            populate_content_screened(db_manager, length, raters, search_conf)
        case Phase.CONTENT_SOLVED:
            populate_content_solved(db_manager, length, raters, search_conf)

if __name__ == "__main__":
    args = parse_args()
    with open(args.search_conf, "r") as f:
        search_conf = json.load(f)
    db_manager = generate_empty_db(args.db_path, search_conf)
    populate_db(db_manager, args.phase, args.length, args.iterations, args.raters, search_conf)
    print("Database populated successfully: ", args.db_path)
    db_manager.conn.close()