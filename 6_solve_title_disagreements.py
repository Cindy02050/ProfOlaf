import sys
import argparse
from enum import Enum
from utils.db_management import DBManager, SelectionStage, merge_databases
from utils.pretty_print_utils import pretty_print, format_color_string
from utils.pipeline.solve_disagreements import solve_disagreements, DisagreementStage

def parse_args():
    parser = argparse.ArgumentParser(description='Filter by title')
    parser.add_argument('--iteration', help='iteration number', type=int)
    parser.add_argument('--search_dbs', help='search dbs', type=str, nargs='+')

if __name__ == "__main__":
    args = parse_args()
    iteration = args.iteration
    search_dbs = args.search_dbs
    selection_stage = DisagreementStage.CONTENT
    merged_db = merge_databases(search_dbs)
    solve_disagreements(iteration, merged_db, selection_stage)