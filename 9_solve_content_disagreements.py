import sys
import argparse
from enum import Enum
from utils.db_management import DBManager, SelectionStage, merge_databases
from utils.cli.pretty_print_utils import pretty_print, format_color_string
from utils.pipeline.solve_disagreements import solve_disagreements, DisagreementStage

def parse_args():
    parser = argparse.ArgumentParser(description='Filter by title')
    parser.add_argument('--iteration', help='iteration number', type=int, required=True)
    # allow multiple search dbs
    parser.add_argument('--search_dbs', help='search dbs', type=str, nargs='+')
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    iteration = args.iteration
    search_dbs = args.search_dbs
    selection_stage = DisagreementStage.CONTENT
    if len(search_dbs) == 0:
        print("No search dbs provided")
        exit(1)
    if len(search_dbs) > 1:
        merged_db = merge_databases(search_dbs)
    else:
        merged_db = DBManager(search_dbs[0])
    solve_disagreements(iteration, merged_db, selection_stage)