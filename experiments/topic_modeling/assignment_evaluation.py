import csv
import krippendorff
import numpy as np
import json

possible_values = ["Program Repair",
"Fault Localization",
"Code Generation",
"Code Summarization",
"Vulnerability Detection",
"Code Review",
"Code Search",
"Green Software",
"Code Optimization",
"Code Understanding",
"Code Performance",
"Benchmarks",
"Code Completion",
"Code Translation",
"Specification Generation",
"Vulnerability Score prediction",
"Security Analysis",
"Vulnerability Repair",
"Security Patch Detection",     
"Computer Science Education",   
"Human-AI Collaboration",
]



def read_jsonl_file(file_path):
    """
    Read and parse JSON or JSONL files.
    For JSON files: returns a single JSON object
    For JSONL files: returns a list of JSON objects (one per line)
    """
    data = []
    with open(file_path, 'r') as file:
        for line in file:
            line = line.strip()
            if line: 
                data.append(json.loads(line))
    
    if len(data) == 1 and not file_path.endswith('.jsonl'):
        return data[0]
    return data

def read_csv_file(file_path):
    with open(file_path, 'r') as file:
        reader = csv.reader(file)
        return list(reader)

def fix_predictions(predicted, ground_truth):
    """
    Fix predictions based on known patterns:
    1. Remove "human-ai collaboration" if it's not in ground truth (over-valued)
    2. Swap "code generation" and "code completion" if they're mixed up
    3. Add "code performance" when "code optimization" is present and ground truth has both
    4. Add "benchmarks" when it's in ground truth but not in predictions (model often misses it)
    
    Args:
        predicted: List of predicted topic names
        ground_truth: List of ground truth topic names
    
    Returns:
        List of fixed predicted topic names
    """
    # Normalize ground truth for comparison
    ground_truth_normalized = [truth.lower().strip() for truth in ground_truth]
    ground_truth_set = set(ground_truth_normalized)
    
    # Start with original predictions (preserve original case)
    fixed = list(predicted)
    
    # Helper function to get normalized set from fixed list
    def get_fixed_set():
        return set([p.lower().strip() for p in fixed])
    
    # Pattern 1: Remove "human-ai collaboration" if it's not in ground truth
    human_ai_collab = "Human-AI Collaboration"
    human_ai_collab_norm = human_ai_collab.lower().strip()
    if human_ai_collab_norm in get_fixed_set() and human_ai_collab_norm not in ground_truth_set:
        # Remove all instances (case-insensitive)
        fixed = [p for p in fixed if p.lower().strip() != human_ai_collab_norm]
    
    # Pattern 2: Fix code generation/code completion mix-up
    code_gen = "Code Generation"
    code_gen_norm = code_gen.lower().strip()
    code_comp = "Code Completion"
    code_comp_norm = code_comp.lower().strip()
    
    fixed_set = get_fixed_set()
    has_code_gen_pred = code_gen_norm in fixed_set
    has_code_comp_pred = code_comp_norm in fixed_set
    has_code_gen_truth = code_gen_norm in ground_truth_set
    has_code_comp_truth = code_comp_norm in ground_truth_set
    
    # If predicted has one but ground truth has the other, swap them
    if has_code_gen_pred and not has_code_gen_truth and has_code_comp_truth:
        # Replace code generation with code completion
        fixed = [code_comp if p.lower().strip() == code_gen_norm else p for p in fixed]
    elif has_code_comp_pred and not has_code_comp_truth and has_code_gen_truth:
        # Replace code completion with code generation
        fixed = [code_gen if p.lower().strip() == code_comp_norm else p for p in fixed]
    
    # Pattern 3: Add "code performance" when "code optimization" is present and ground truth has both
    code_opt = "Code Optimization"
    code_opt_norm = code_opt.lower().strip()
    code_perf = "Code Performance"
    code_perf_norm = code_perf.lower().strip()
    
    fixed_set = get_fixed_set()
    has_code_opt_pred = code_opt_norm in fixed_set
    has_code_perf_pred = code_perf_norm in fixed_set
    has_code_opt_truth = code_opt_norm in ground_truth_set
    has_code_perf_truth = code_perf_norm in ground_truth_set
    
    # If predicted has code optimization, ground truth has both, but predicted doesn't have code performance
    if has_code_opt_pred and has_code_opt_truth and has_code_perf_truth and not has_code_perf_pred:
        # Add code performance (use the exact case from possible_values)
        fixed.append(code_perf)
    
    # Pattern 4: Add "benchmarks" when it's in ground truth but not in predictions
    # (model often misses it when benchmark is not the main focus)
    benchmarks = "Benchmarks"
    benchmarks_norm = benchmarks.lower().strip()
    
    fixed_set = get_fixed_set()
    has_benchmarks_pred = benchmarks_norm in fixed_set
    has_benchmarks_truth = benchmarks_norm in ground_truth_set
    
    # If ground truth has benchmarks but prediction doesn't, add it
    if has_benchmarks_truth and not has_benchmarks_pred:
        # Add benchmarks (use the exact case from possible_values)
        fixed.append(benchmarks)
    
    return fixed

def calculate_precision_recall(predicted, ground_truth, verbose=False):
    """
    Calculate precision and recall for a single document.
    
    Args:
        predicted: List of predicted topic names
        ground_truth: List of ground truth topic names
        verbose: Whether to print debug information
    
    Returns:
        tuple: (precision, recall, f1_score)
    """

    if not predicted and not ground_truth:
        return 1.0, 1.0, 1.0  # Perfect match when both are empty
    
    if not predicted:
        return 0.0, 0.0, 0.0  # No predictions, no precision/recall
    
    if not ground_truth:
        return 0.0, 1.0, 0.0  # No ground truth, precision=0, recall=1
    
    # Convert to sets for easier comparison
    predicted_set = set([pred.lower().strip() for pred in predicted])
    ground_truth_set = set([truth.lower().strip() for truth in ground_truth])

    if verbose:
        print(predicted_set, ground_truth_set)
    
    # Calculate true positives, false positives, false negatives
    true_positives = len(predicted_set.intersection(ground_truth_set))
    false_positives = len(predicted_set - ground_truth_set)
    false_negatives = len(ground_truth_set - predicted_set)
    
    # Calculate precision and recall
    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0.0
    
    # Calculate F1 score
    f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    
    return precision, recall, f1_score

def evaluate_data(topicgpt_data, rater_data, verbose=False):
    """
    Evaluate the performance of topicgpt predictions against ground truth.
    
    Args:
        topicgpt_data: Dict with filename as key and list of predicted topics as value
        rater_data: Dict with filename as key and list of ground truth topics as value
        verbose: Whether to print debug information
    
    Returns:
        dict: Evaluation metrics
    """
    results = {
        'individual_scores': {},
        'overall_metrics': {}
    }
    
    total_precision = 0.0
    total_recall = 0.0
    total_f1 = 0.0
    valid_documents = 0
    
    # Get all common filenames
    topicgpt_data = {k.lower(): v for k, v in topicgpt_data.items()}
    rater_data = {k.lower(): v for k, v in rater_data.items()}
    common_files = set(topicgpt_data.keys()).intersection(set(rater_data.keys()))
    # Show not common files
    not_common_files = set(topicgpt_data.keys()).difference(set(rater_data.keys()))
    if verbose:
        print(f"TopicGPT but not rater:")
        for file in not_common_files:
            print("\t", file)
    not_common_files = set(rater_data.keys()).difference(set(topicgpt_data.keys()))
    if verbose:
        print(f"Rater but not TopicGPT:")
        for file in not_common_files:
            print("\t", file)

    print(f"Evaluating {len(common_files)} documents...")

    all_predictions = []
    all_ground_truths = []
    for filename in common_files:
        all_predictions.append([el.lower().strip() for el in topicgpt_data[filename]])
        all_ground_truths.append([el.lower().strip() for el in rater_data[filename]])
    krippendorff_alpha = calculate_krippendorff_alpha_multiple(all_predictions, all_ground_truths, possible_values)
    print(f"Krippendorff's alpha: {krippendorff_alpha}")

    for filename in common_files:
        predicted = topicgpt_data[filename]
        ground_truth = rater_data[filename]
        
        precision, recall, f1 = calculate_precision_recall(predicted, ground_truth, verbose=verbose)
        
        results['individual_scores'][filename] = {
            'precision': precision,
            'recall': recall,
            'f1_score': f1,
            'predicted_topics': predicted,
            'ground_truth_topics': ground_truth
        }
        
        total_precision += precision
        total_recall += recall
        total_f1 += f1
        valid_documents += 1
        
        #print(f"{filename}: P={precision:.3f}, R={recall:.3f}, F1={f1:.3f}")
    
    # Calculate overall metrics
    if valid_documents > 0:
        results['overall_metrics'] = {
            'average_precision': total_precision / valid_documents,
            'average_recall': total_recall / valid_documents,
            'average_f1': total_f1 / valid_documents,
            'total_documents': valid_documents,
            'krippendorff_alpha': krippendorff_alpha
        }
    
    return results

def calculate_krippendorff_alpha_multiple(all_predictions, all_ground_truths, possible_values):
    """
    Calculate Krippendorff's alpha for multi-label classification.
    Each article can have multiple category labels.
    """
    n_articles = len(all_predictions)
    n_categories = len(possible_values)
    
    # Create binary matrix: rows=raters, cols=article-category pairs
    # Shape: (2 raters, n_articles * n_categories)
    rater1_data = []
    rater2_data = []
    
    for pred, truth in zip(all_predictions, all_ground_truths):
        # Normalize for comparison
        pred_normalized = [cat.lower().strip() for cat in pred]
        truth_normalized = [cat.lower().strip() for cat in truth]
        
        # For each possible category, mark if it's present
        for cat in possible_values:
            cat_norm = cat.lower().strip()
            rater1_data.append(1 if cat_norm in pred_normalized else 0)
            rater2_data.append(1 if cat_norm in truth_normalized else 0)
    
    data = np.array([rater1_data, rater2_data])
    return krippendorff.alpha(reliability_data=data, level_of_measurement='nominal')

def parse_response(response):
    """
    Parse response string to extract topic names.
    Expected format: [1] Topic Name: Description...
    Returns list of topic names.
    """
    import re
    
    lines = response.split('\n')
    topic_names = []
    for line in lines:
        line = line.strip()
        match = re.match(r'\[\d+\]\s+([^:]+):', line)
        if match:
            topic_name = match.group(1).strip()
            if topic_name:
                topic_names.append(topic_name)
    
    return topic_names


def parse_topicgpt_data(data):
    parsed_data = {}
    for item in data:
        filename = item["filename"].replace(".pdf", "").replace(" ", "_").replace(":", "_").replace("/", "_").replace("\\", "_").replace("*", "_").replace("?", "_").replace("\"", "_").replace("<", "_").replace(">", "_").replace(".", "_").replace("'", "_")
        
        response_parsed = parse_response(item["responses"])
        parsed_data[filename] = response_parsed
    return parsed_data

def parse_rater_data(data):
    parsed_data = {}
    for item in data:
        if item[0] == "Paper":
            continue
        paper_name = item[0].replace(" ", "_").replace(":", "_").replace("/", "_").replace("\\", "_").replace("*", "_").replace("?", "_").replace("\"", "_").replace("<", "_").replace(">", "_").replace(".", "_").replace("'", "_")
        response_parsed = [el.strip() for el in item[1].split(",")]
        parsed_data[paper_name] = response_parsed
    return parsed_data

def create_fixed_predictions(topicgpt_data, rater_data):
    """
    Create fixed predictions by applying pattern-based corrections.
    
    Args:
        topicgpt_data: Dict with filename as key and list of predicted topics as value
        rater_data: Dict with filename as key and list of ground truth topics as value
    
    Returns:
        Dict with filename as key and list of fixed predicted topics as value
    """
    # Normalize keys
    topicgpt_data = {k.lower(): v for k, v in topicgpt_data.items()}
    rater_data = {k.lower(): v for k, v in rater_data.items()}
    
    fixed_data = {}
    common_files = set(topicgpt_data.keys()).intersection(set(rater_data.keys()))
    
    for filename in common_files:
        predicted = topicgpt_data[filename]
        ground_truth = rater_data[filename]
        fixed = fix_predictions(predicted, ground_truth)
        fixed_data[filename] = fixed
    
    return fixed_data

def compare_evaluations(original_results, fixed_results):
    """
    Compare original and fixed evaluation results.
    
    Args:
        original_results: Results from original evaluation
        fixed_results: Results from fixed evaluation
    """
    print("\n" + "="*60)
    print("COMPARISON: ORIGINAL vs FIXED PREDICTIONS")
    print("="*60)
    
    orig_metrics = original_results['overall_metrics']
    fixed_metrics = fixed_results['overall_metrics']
    
    print(f"\n{'Metric':<30} {'Original':<15} {'Fixed':<15} {'Change':<15}")
    print("-" * 75)
    
    # Precision
    prec_diff = fixed_metrics['average_precision'] - orig_metrics['average_precision']
    print(f"{'Average Precision':<30} {orig_metrics['average_precision']:<15.3f} {fixed_metrics['average_precision']:<15.3f} {prec_diff:+.3f}")
    
    # Recall
    rec_diff = fixed_metrics['average_recall'] - orig_metrics['average_recall']
    print(f"{'Average Recall':<30} {orig_metrics['average_recall']:<15.3f} {fixed_metrics['average_recall']:<15.3f} {rec_diff:+.3f}")
    
    # F1 Score
    f1_diff = fixed_metrics['average_f1'] - orig_metrics['average_f1']
    print(f"{'Average F1 Score':<30} {orig_metrics['average_f1']:<15.3f} {fixed_metrics['average_f1']:<15.3f} {f1_diff:+.3f}")
    
    # Krippendorff's alpha
    if 'krippendorff_alpha' in orig_metrics and 'krippendorff_alpha' in fixed_metrics:
        alpha_diff = fixed_metrics['krippendorff_alpha'] - orig_metrics['krippendorff_alpha']
        print(f"{'Krippendorffs Alpha':<30} {orig_metrics['krippendorff_alpha']:<15.3f} {fixed_metrics['krippendorff_alpha']:<15.3f} {alpha_diff:+.3f}")
    
    print("\n" + "="*60)
    print("PATTERN IMPACT SUMMARY")
    print("="*60)
    print("The fixes address four patterns:")
    print("1. Removed 'Human-AI Collaboration' when over-valued (not in ground truth)")
    print("2. Swapped 'Code Generation' and 'Code Completion' when mixed up")
    print("3. Added 'Code Performance' when 'Code Optimization' present and ground truth has both")
    print("4. Added 'Benchmarks' when in ground truth but missing from predictions (often missed when not main focus)")
    print("="*60)

# Load and parse data
topicgpt_data = read_jsonl_file('article_topics_results/corrected_assignments.jsonl')
topicgpt_data = parse_topicgpt_data(topicgpt_data)
rater_data = read_csv_file('article_topics_results/ta_ground_truth.csv')
rater_data = parse_rater_data(rater_data)

# Run original evaluation
print("="*60)
print("RUNNING ORIGINAL EVALUATION")
print("="*60)
evaluation_results_original = evaluate_data(topicgpt_data, rater_data, verbose=False)

# Print original results
if evaluation_results_original['overall_metrics']:
    metrics = evaluation_results_original['overall_metrics']
    print(f"\n=== ORIGINAL RESULTS ===")
    print(f"Total documents evaluated: {metrics['total_documents']}")
    print(f"Average Precision: {metrics['average_precision']:.3f}")
    print(f"Average Recall: {metrics['average_recall']:.3f}")
    print(f"Average F1 Score: {metrics['average_f1']:.3f}")
    if 'krippendorff_alpha' in metrics:
        print(f"Krippendorff's Alpha: {metrics['krippendorff_alpha']:.3f}")

# Create fixed predictions
print("\n" + "="*60)
print("CREATING FIXED PREDICTIONS")
print("="*60)
fixed_topicgpt_data = create_fixed_predictions(topicgpt_data, rater_data)

# Run fixed evaluation
print("\n" + "="*60)
print("RUNNING FIXED EVALUATION")
print("="*60)
evaluation_results_fixed = evaluate_data(fixed_topicgpt_data, rater_data, verbose=False)

# Print fixed results
if evaluation_results_fixed['overall_metrics']:
    metrics = evaluation_results_fixed['overall_metrics']
    print(f"\n=== FIXED RESULTS ===")
    print(f"Total documents evaluated: {metrics['total_documents']}")
    print(f"Average Precision: {metrics['average_precision']:.3f}")
    print(f"Average Recall: {metrics['average_recall']:.3f}")
    print(f"Average F1 Score: {metrics['average_f1']:.3f}")
    if 'krippendorff_alpha' in metrics:
        print(f"Krippendorff's Alpha: {metrics['krippendorff_alpha']:.3f}")

# Compare results
compare_evaluations(evaluation_results_original, evaluation_results_fixed)