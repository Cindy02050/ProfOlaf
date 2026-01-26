import argparse
import json
from typing import List, Tuple, Dict
from difflib import SequenceMatcher
import sys

from utils.db_management import DBManager, SelectionStage
from utils.pipeline.remove_duplicates import remove_duplicates


with open("confs/search_conf.json", "r") as f:
    search_conf = json.load(f)


def parse_args():
    parser = argparse.ArgumentParser(description='Remove duplicate articles')
    parser.add_argument('--db_path', help='db path', type=str, default=search_conf["db_path"])
    parser.add_argument('--iterations', help='iterations', type=int, nargs='+')
    parser.add_argument('--similarity_threshold', help='Title similarity threshold (0.0-1.0)', 
                       type=float, default=0.8)
    parser.add_argument('--auto_remove', help='Automatically remove duplicates without user confirmation', 
                       action='store_true')
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    db_manager = DBManager(args.db_path)
    remove_duplicates(db_manager, args.iterations, args.similarity_threshold, args.auto_remove)

