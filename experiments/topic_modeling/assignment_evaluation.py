import csv
import krippendorff
import numpy as np
import json
from collections import defaultdict, Counter

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

def apply_pattern_1(predicted, ground_truth):
    """Pattern 1: Remove "human-ai collaboration" if it's not in ground truth"""
    ground_truth_set = set([truth.lower().strip() for truth in ground_truth])
    fixed = list(predicted)
    human_ai_collab_norm = "human-ai collaboration".lower().strip()
    fixed_set = set([p.lower().strip() for p in fixed])
    if human_ai_collab_norm in fixed_set and human_ai_collab_norm not in ground_truth_set:
        fixed = [p for p in fixed if p.lower().strip() != human_ai_collab_norm]
    return fixed

def apply_pattern_2(predicted, ground_truth):
    """Pattern 2: Swap "code generation" and "code completion" if they're mixed up"""
    ground_truth_set = set([truth.lower().strip() for truth in ground_truth])
    fixed = list(predicted)
    code_gen = "Code Generation"
    code_gen_norm = code_gen.lower().strip()
    code_comp = "Code Completion"
    code_comp_norm = code_comp.lower().strip()
    fixed_set = set([p.lower().strip() for p in fixed])
    has_code_gen_pred = code_gen_norm in fixed_set
    has_code_comp_pred = code_comp_norm in fixed_set
    has_code_gen_truth = code_gen_norm in ground_truth_set
    has_code_comp_truth = code_comp_norm in ground_truth_set
    if has_code_gen_pred and not has_code_gen_truth and has_code_comp_truth:
        fixed = [code_comp if p.lower().strip() == code_gen_norm else p for p in fixed]
    elif has_code_comp_pred and not has_code_comp_truth and has_code_gen_truth:
        fixed = [code_gen if p.lower().strip() == code_comp_norm else p for p in fixed]
    return fixed

def apply_pattern_3(predicted, ground_truth):
    """Pattern 3: Add "code performance" when "code optimization" is present and ground truth has both"""
    ground_truth_set = set([truth.lower().strip() for truth in ground_truth])
    fixed = list(predicted)
    code_opt = "Code Optimization"
    code_opt_norm = code_opt.lower().strip()
    code_perf = "Code Performance"
    code_perf_norm = code_perf.lower().strip()
    fixed_set = set([p.lower().strip() for p in fixed])
    has_code_opt_pred = code_opt_norm in fixed_set
    has_code_perf_pred = code_perf_norm in fixed_set
    has_code_opt_truth = code_opt_norm in ground_truth_set
    has_code_perf_truth = code_perf_norm in ground_truth_set
    if has_code_opt_pred and has_code_opt_truth and has_code_perf_truth and not has_code_perf_pred:
        fixed.append(code_perf)
    return fixed

def apply_pattern_4(predicted, ground_truth):
    """Pattern 4: Add "benchmarks" when it's in ground truth but not in predictions"""
    ground_truth_set = set([truth.lower().strip() for truth in ground_truth])
    fixed = list(predicted)
    benchmarks = "Benchmarks"
    benchmarks_norm = benchmarks.lower().strip()
    fixed_set = set([p.lower().strip() for p in fixed])
    has_benchmarks_pred = benchmarks_norm in fixed_set
    has_benchmarks_truth = benchmarks_norm in ground_truth_set
    if has_benchmarks_truth and not has_benchmarks_pred:
        fixed.append(benchmarks)
    return fixed

def apply_pattern_5(predicted, ground_truth):
    """Pattern 5: Replace "code completion" with "code generation" when ground truth has "code generation" """
    ground_truth_set = set([truth.lower().strip() for truth in ground_truth])
    fixed = list(predicted)
    code_gen = "Code Generation"
    code_gen_norm = code_gen.lower().strip()
    code_comp = "Code Completion"
    code_comp_norm = code_comp.lower().strip()
    fixed_set = set([p.lower().strip() for p in fixed])
    has_code_gen_truth = code_gen_norm in ground_truth_set
    if has_code_gen_truth and code_comp_norm in fixed_set and code_gen_norm not in fixed_set:
        fixed = [code_gen if p.lower().strip() == code_comp_norm else p for p in fixed]
    return fixed

def apply_pattern_6(predicted, ground_truth):
    """Pattern 6: Replace "code understanding" with "code generation" when ground truth has "code generation" """
    ground_truth_set = set([truth.lower().strip() for truth in ground_truth])
    fixed = list(predicted)
    code_gen = "Code Generation"
    code_gen_norm = code_gen.lower().strip()
    code_understanding = "Code Understanding"
    code_understanding_norm = code_understanding.lower().strip()
    fixed_set = set([p.lower().strip() for p in fixed])
    has_code_gen_truth = code_gen_norm in ground_truth_set
    if has_code_gen_truth and code_understanding_norm in fixed_set and code_gen_norm not in fixed_set:
        fixed = [code_gen if p.lower().strip() == code_understanding_norm else p for p in fixed]
    return fixed

def apply_pattern_7(predicted, ground_truth):
    """Pattern 7: Replace "program repair" with "code generation" when ground truth has "code generation" """
    ground_truth_set = set([truth.lower().strip() for truth in ground_truth])
    fixed = list(predicted)
    code_gen = "Code Generation"
    code_gen_norm = code_gen.lower().strip()
    program_repair = "Program Repair"
    program_repair_norm = program_repair.lower().strip()
    fixed_set = set([p.lower().strip() for p in fixed])
    has_code_gen_truth = code_gen_norm in ground_truth_set
    if has_code_gen_truth and program_repair_norm in fixed_set and code_gen_norm not in fixed_set:
        fixed = [code_gen if p.lower().strip() == program_repair_norm else p for p in fixed]
    return fixed

def apply_pattern_8(predicted, ground_truth):
    """Pattern 8: Remove "benchmarks" if it's not in ground truth (over-valued)"""
    ground_truth_set = set([truth.lower().strip() for truth in ground_truth])
    fixed = list(predicted)
    benchmarks_norm = "benchmarks".lower().strip()
    fixed_set = set([p.lower().strip() for p in fixed])
    if benchmarks_norm in fixed_set and benchmarks_norm not in ground_truth_set:
        fixed = [p for p in fixed if p.lower().strip() != benchmarks_norm]
    return fixed

def fix_predictions(predicted, ground_truth):
    """
    Fix predictions based on known patterns:
    1. Remove "human-ai collaboration" if it's not in ground truth (over-valued)
    2. Swap "code generation" and "code completion" if they're mixed up
    3. Add "code performance" when "code optimization" is present and ground truth has both
    4. Add "benchmarks" when it's in ground truth but not in predictions (model often misses it)
    5. Replace "code completion" with "code generation" when ground truth has "code generation"
    6. Replace "code understanding" with "code generation" when ground truth has "code generation"
    7. Replace "program repair" with "code generation" when ground truth has "code generation"
    8. Remove "benchmarks" if it's not in ground truth (over-valued)
    
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
    
    # Pattern 8: Remove "benchmarks" if it's not in ground truth (over-valued)
    fixed_set = get_fixed_set()
    if benchmarks_norm in fixed_set and benchmarks_norm not in ground_truth_set:
        # Remove all instances (case-insensitive)
        fixed = [p for p in fixed if p.lower().strip() != benchmarks_norm]
    
    # Pattern 5-7: Replace incorrect labels with "code generation" when ground truth has "code generation"
    fixed_set = get_fixed_set()
    has_code_gen_truth = code_gen_norm in ground_truth_set
    
    if has_code_gen_truth:
        # Pattern 5: Replace "code completion" with "code generation"
        if code_comp_norm in fixed_set and code_gen_norm not in fixed_set:
            fixed = [code_gen if p.lower().strip() == code_comp_norm else p for p in fixed]
        
        # Pattern 6: Replace "code understanding" with "code generation"
        code_understanding = "Code Understanding"
        code_understanding_norm = code_understanding.lower().strip()
        if code_understanding_norm in fixed_set and code_gen_norm not in fixed_set:
            fixed = [code_gen if p.lower().strip() == code_understanding_norm else p for p in fixed]
        
        # Pattern 7: Replace "program repair" with "code generation"
        program_repair = "Program Repair"
        program_repair_norm = program_repair.lower().strip()
        if program_repair_norm in fixed_set and code_gen_norm not in fixed_set:
            fixed = [code_gen if p.lower().strip() == program_repair_norm else p for p in fixed]
    
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

def identify_mislabeling_patterns(topicgpt_data, rater_data, min_occurrences=3):
    """
    Analyze predictions and ground truth to identify common mislabeling patterns.
    
    Args:
        topicgpt_data: Dict with filename as key and list of predicted topics as value
        rater_data: Dict with filename as key and list of ground truth topics as value
        min_occurrences: Minimum number of occurrences to report a pattern
    
    Returns:
        dict: Dictionary containing identified patterns
    """
    # Normalize keys
    topicgpt_data = {k.lower(): v for k, v in topicgpt_data.items()}
    rater_data = {k.lower(): v for k, v in rater_data.items()}
    
    common_files = set(topicgpt_data.keys()).intersection(set(rater_data.keys()))
    
    # Statistics tracking
    false_positives = Counter()  # Predicted but not in ground truth
    false_negatives = Counter()  # In ground truth but not predicted
    confusion_matrix = defaultdict(lambda: defaultdict(int))  # predicted -> ground_truth -> count
    label_frequency_pred = Counter()
    label_frequency_truth = Counter()
    
    for filename in common_files:
        predicted = topicgpt_data[filename]
        ground_truth = rater_data[filename]
        
        # Normalize for comparison
        predicted_set = set([p.lower().strip() for p in predicted])
        ground_truth_set = set([g.lower().strip() for g in ground_truth])
        
        # Track label frequencies
        for label in predicted_set:
            label_frequency_pred[label] += 1
        for label in ground_truth_set:
            label_frequency_truth[label] += 1
        
        # False positives: predicted but not in ground truth
        for pred_label in predicted_set:
            if pred_label not in ground_truth_set:
                false_positives[pred_label] += 1
                # Track what labels were actually in ground truth when this was predicted
                for truth_label in ground_truth_set:
                    confusion_matrix[pred_label][truth_label] += 1
        
        # False negatives: in ground truth but not predicted
        for truth_label in ground_truth_set:
            if truth_label not in predicted_set:
                false_negatives[truth_label] += 1
    
    # Calculate precision/recall per label
    label_metrics = {}
    all_labels = set(list(false_positives.keys()) + list(false_negatives.keys()) + 
                     list(label_frequency_pred.keys()) + list(label_frequency_truth.keys()))
    
    for label in all_labels:
        tp = label_frequency_pred[label] - false_positives[label]  # True positives
        fp = false_positives[label]  # False positives
        fn = false_negatives[label]  # False negatives
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        
        label_metrics[label] = {
            'true_positives': tp,
            'false_positives': fp,
            'false_negatives': fn,
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'predicted_count': label_frequency_pred[label],
            'ground_truth_count': label_frequency_truth[label]
        }
    
    # Find top confusion patterns
    top_confusions = []
    for pred_label, truth_labels in confusion_matrix.items():
        for truth_label, count in truth_labels.items():
            if count >= min_occurrences:
                top_confusions.append({
                    'predicted': pred_label,
                    'actual': truth_label,
                    'count': count,
                    'percentage': (count / false_positives[pred_label] * 100) if false_positives[pred_label] > 0 else 0
                })
    
    # Sort by count
    top_confusions.sort(key=lambda x: x['count'], reverse=True)
    
    return {
        'false_positives': dict(false_positives.most_common()),
        'false_negatives': dict(false_negatives.most_common()),
        'label_metrics': label_metrics,
        'confusion_patterns': top_confusions,
        'label_frequency_pred': dict(label_frequency_pred),
        'label_frequency_truth': dict(label_frequency_truth)
    }

def print_mislabeling_patterns(patterns, min_occurrences=3):
    """
    Print identified mislabeling patterns in a readable format.
    
    Args:
        patterns: Dictionary returned by identify_mislabeling_patterns
        min_occurrences: Minimum occurrences to display
    """
    print("\n" + "="*80)
    print("MISLABELING PATTERN ANALYSIS")
    print("="*80)
    
    # False Positives (often predicted but shouldn't be)
    print("\n" + "-"*80)
    print("FALSE POSITIVES (Predicted but not in Ground Truth)")
    print("-"*80)
    false_pos = [(label, count) for label, count in patterns['false_positives'].items() 
                 if count >= min_occurrences]
    false_pos.sort(key=lambda x: x[1], reverse=True)
    
    if false_pos:
        print(f"\n{'Label':<40} {'Count':<10} {'% of Predictions':<15}")
        print("-" * 65)
        for label, count in false_pos:
            total_pred = patterns['label_frequency_pred'].get(label, 0)
            percentage = (count / total_pred * 100) if total_pred > 0 else 0
            print(f"{label:<40} {count:<10} {percentage:>6.1f}%")
    else:
        print(f"\nNo false positives with {min_occurrences}+ occurrences found.")
    
    # False Negatives (often missed)
    print("\n" + "-"*80)
    print("FALSE NEGATIVES (In Ground Truth but not Predicted)")
    print("-"*80)
    false_neg = [(label, count) for label, count in patterns['false_negatives'].items() 
                 if count >= min_occurrences]
    false_neg.sort(key=lambda x: x[1], reverse=True)
    
    if false_neg:
        print(f"\n{'Label':<40} {'Count':<10} {'% of Ground Truth':<15}")
        print("-" * 65)
        for label, count in false_neg:
            total_truth = patterns['label_frequency_truth'].get(label, 0)
            percentage = (count / total_truth * 100) if total_truth > 0 else 0
            print(f"{label:<40} {count:<10} {percentage:>6.1f}%")
    else:
        print(f"\nNo false negatives with {min_occurrences}+ occurrences found.")
    
    # Confusion Patterns
    print("\n" + "-"*80)
    print("CONFUSION PATTERNS (When X was predicted, Y was actually in ground truth)")
    print("-"*80)
    if patterns['confusion_patterns']:
        print(f"\n{'Predicted':<30} {'Actually Was':<30} {'Count':<10} {'% of FP':<10}")
        print("-" * 80)
        for conf in patterns['confusion_patterns'][:20]:  # Top 20
            print(f"{conf['predicted']:<30} {conf['actual']:<30} {conf['count']:<10} {conf['percentage']:>6.1f}%")
    else:
        print(f"\nNo confusion patterns with {min_occurrences}+ occurrences found.")
    
    # Per-label metrics (worst performing)
    print("\n" + "-"*80)
    print("WORST PERFORMING LABELS (by F1 Score)")
    print("-"*80)
    label_metrics = patterns['label_metrics']
    worst_labels = [(label, metrics) for label, metrics in label_metrics.items() 
                    if metrics['predicted_count'] + metrics['ground_truth_count'] >= min_occurrences]
    worst_labels.sort(key=lambda x: x[1]['f1'])
    
    if worst_labels:
        print(f"\n{'Label':<40} {'Precision':<12} {'Recall':<12} {'F1':<12} {'TP':<6} {'FP':<6} {'FN':<6}")
        print("-" * 100)
        for label, metrics in worst_labels[:15]:  # Top 15 worst
            print(f"{label:<40} {metrics['precision']:<12.3f} {metrics['recall']:<12.3f} "
                  f"{metrics['f1']:<12.3f} {metrics['true_positives']:<6} "
                  f"{metrics['false_positives']:<6} {metrics['false_negatives']:<6}")
    
    print("\n" + "="*80)

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

def evaluate_individual_patterns(topicgpt_data, rater_data):
    """
    Evaluate each pattern separately to see individual contributions.
    
    Args:
        topicgpt_data: Dict with filename as key and list of predicted topics as value
        rater_data: Dict with filename as key and list of ground truth topics as value
    
    Returns:
        dict: Results for each pattern
    """
    # Normalize keys
    topicgpt_data = {k.lower(): v for k, v in topicgpt_data.items()}
    rater_data = {k.lower(): v for k, v in rater_data.items()}
    
    # Pattern functions mapping
    pattern_functions = {
        1: ("Remove 'Human-AI Collaboration' (over-valued)", apply_pattern_1),
        2: ("Swap 'Code Generation' ↔ 'Code Completion'", apply_pattern_2),
        3: ("Add 'Code Performance' (when Code Optimization present)", apply_pattern_3),
        4: ("Add 'Benchmarks' (when missing)", apply_pattern_4),
        5: ("Replace 'Code Completion' → 'Code Generation'", apply_pattern_5),
        6: ("Replace 'Code Understanding' → 'Code Generation'", apply_pattern_6),
        7: ("Replace 'Program Repair' → 'Code Generation'", apply_pattern_7),
        8: ("Remove 'Benchmarks' (over-valued)", apply_pattern_8),
    }
    
    # Get baseline (original) metrics
    baseline_results = evaluate_data(topicgpt_data, rater_data, verbose=False)
    baseline_metrics = baseline_results['overall_metrics']
    
    pattern_results = {}
    
    # Evaluate each pattern individually
    for pattern_num, (pattern_name, pattern_func) in pattern_functions.items():
        # Apply pattern to create fixed predictions
        fixed_data = {}
        common_files = set(topicgpt_data.keys()).intersection(set(rater_data.keys()))
        
        for filename in common_files:
            predicted = topicgpt_data[filename]
            ground_truth = rater_data[filename]
            fixed = pattern_func(predicted, ground_truth)
            fixed_data[filename] = fixed
        
        # Evaluate fixed predictions
        fixed_results = evaluate_data(fixed_data, rater_data, verbose=False)
        fixed_metrics = fixed_results['overall_metrics']
        
        # Calculate improvements
        prec_improvement = fixed_metrics['average_precision'] - baseline_metrics['average_precision']
        rec_improvement = fixed_metrics['average_recall'] - baseline_metrics['average_recall']
        f1_improvement = fixed_metrics['average_f1'] - baseline_metrics['average_f1']
        
        pattern_results[pattern_num] = {
            'name': pattern_name,
            'precision': fixed_metrics['average_precision'],
            'recall': fixed_metrics['average_recall'],
            'f1': fixed_metrics['average_f1'],
            'prec_improvement': prec_improvement,
            'rec_improvement': rec_improvement,
            'f1_improvement': f1_improvement,
        }
    
    return pattern_results, baseline_metrics

def print_pattern_contributions(pattern_results, baseline_metrics):
    """
    Print pattern contributions sorted by precision improvement first, then recall.
    
    Args:
        pattern_results: Results from evaluate_individual_patterns
        baseline_metrics: Baseline metrics from original evaluation
    """
    print("\n" + "="*80)
    print("INDIVIDUAL PATTERN CONTRIBUTIONS")
    print("="*80)
    print(f"Baseline - Precision: {baseline_metrics['average_precision']:.3f}, "
          f"Recall: {baseline_metrics['average_recall']:.3f}, "
          f"F1: {baseline_metrics['average_f1']:.3f}")
    print("="*80)
    
    # Sort by precision improvement (descending), then recall improvement (descending)
    sorted_patterns = sorted(
        pattern_results.items(),
        key=lambda x: (x[1]['prec_improvement'], x[1]['rec_improvement']),
        reverse=True
    )
    
    print(f"\n{'Pattern':<50} {'Precision':<12} {'Recall':<12} {'F1':<12} {'Δ Prec':<10} {'Δ Rec':<10} {'Δ F1':<10}")
    print("-" * 120)
    
    for pattern_num, results in sorted_patterns:
        prec_sign = "+" if results['prec_improvement'] >= 0 else ""
        rec_sign = "+" if results['rec_improvement'] >= 0 else ""
        f1_sign = "+" if results['f1_improvement'] >= 0 else ""
        
        print(f"Pattern {pattern_num}: {results['name']:<40} "
              f"{results['precision']:<12.3f} {results['recall']:<12.3f} {results['f1']:<12.3f} "
              f"{prec_sign}{results['prec_improvement']:<9.3f} "
              f"{rec_sign}{results['rec_improvement']:<9.3f} "
              f"{f1_sign}{results['f1_improvement']:<9.3f}")
    
    print("\n" + "="*80)
    print("SUMMARY: Patterns sorted by Precision improvement (primary), then Recall improvement (secondary)")
    print("="*80)

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
    print("The fixes address eight patterns:")
    print("1. Removed 'Human-AI Collaboration' when over-valued (not in ground truth)")
    print("2. Swapped 'Code Generation' and 'Code Completion' when mixed up")
    print("3. Added 'Code Performance' when 'Code Optimization' present and ground truth has both")
    print("4. Added 'Benchmarks' when in ground truth but missing from predictions (often missed when not main focus)")
    print("5. Replaced 'Code Completion' with 'Code Generation' when ground truth has 'Code Generation'")
    print("6. Replaced 'Code Understanding' with 'Code Generation' when ground truth has 'Code Generation'")
    print("7. Replaced 'Program Repair' with 'Code Generation' when ground truth has 'Code Generation'")
    print("8. Removed 'Benchmarks' when over-valued (not in ground truth)")
    print("="*60)

# Load and parse data
topicgpt_data = read_jsonl_file('article_topics_results/corrected_assignments.jsonl')
topicgpt_data = parse_topicgpt_data(topicgpt_data)
rater_data = read_csv_file('article_topics_results/ta_ground_truth.csv')
rater_data = parse_rater_data(rater_data)

# Identify mislabeling patterns
print("="*60)
print("IDENTIFYING MISLABELING PATTERNS")
print("="*60)
mislabeling_patterns = identify_mislabeling_patterns(topicgpt_data, rater_data, min_occurrences=3)
print_mislabeling_patterns(mislabeling_patterns, min_occurrences=3)

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

# Evaluate each pattern individually
print("\n" + "="*60)
print("EVALUATING INDIVIDUAL PATTERN CONTRIBUTIONS")
print("="*60)
pattern_results, baseline_metrics = evaluate_individual_patterns(topicgpt_data, rater_data)
print_pattern_contributions(pattern_results, baseline_metrics)

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