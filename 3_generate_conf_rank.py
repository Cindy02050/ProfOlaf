import json
import argparse

from utils.cli.pretty_print_utils import pretty_print, format_color_string, prompt_input
from tabulate import tabulate

from utils.db_management import (
    ArticleData,
    SelectionStage,
    get_iteration_setup,
)
from utils.pipeline.generate_conf_rank_utils import get_venues, get_unindexed_venues

with open("confs/search_conf.json", "r") as f:
    search_conf = json.load(f)

def parse_args():
    parser = argparse.ArgumentParser(description='Generate conf rank')
    parser.add_argument('--iteration', help='iteration number', type=int)
    parser.add_argument('--db_path', help='db path', type=str, default=search_conf["db_path"])
    args = parser.parse_args()
    return args

if __name__ == "__main__":
    args = parse_args()

    db_manager, articles = get_iteration_setup(
        args.db_path, 
        iteration=args.iteration, 
        bibtex__not_empty=True, 
        bibtex__ne="NO_BIBTEX", 
        selected=SelectionStage.NOT_SELECTED
    )

    venues = get_venues(articles)
    print("Number of Venues to process: ", len(venues))

    conf_rank = db_manager.get_conf_rank_data()
    conf_rank = {venue: rank for venue, rank in conf_rank}
    get_unindexed_venues(venues, conf_rank, db_manager, search_conf)
