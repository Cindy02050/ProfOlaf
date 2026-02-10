#!/usr/bin/env python3
"""
Script to fix nested quotation marks in CSV file.
Replaces inner double quotes (") with single quotes (') in quoted fields.
"""

import sys
from pathlib import Path


def fix_nested_quotes(line: str) -> str:
    """
    Fix nested quotation marks in a CSV line.
    Replaces inner double quotes with single quotes in quoted fields.
    
    Example: "Ltd "Integration: Education and Science"" -> "Ltd 'Integration: Education and Science'"
    """
    # Process the line character by character to handle CSV quoting correctly
    result = []
    i = 0
    in_quotes = False
    
    while i < len(line):
        char = line[i]
        
        if char == '"':
            if not in_quotes:
                # Starting a quoted field - always keep the opening quote
                in_quotes = True
                result.append(char)
            else:
                # We're inside a quoted field
                # Check what comes after this quote
                if i + 1 >= len(line):
                    # End of line - this closes the field
                    result.append(char)
                    in_quotes = False
                elif line[i + 1] in (';', '\n', '\r'):
                    # Quote followed by delimiter - this closes the field
                    result.append(char)
                    in_quotes = False
                elif line[i + 1] == '"':
                    # Two quotes in a row - need to determine if it's escaped or nested+closing
                    # Check the character after the second quote
                    if i + 2 >= len(line) or line[i + 2] in (';', '\n', '\r'):
                        # Pattern: ""; or ""\n - this is nested quote closing + field closing
                        # First quote closes nested (replace with '), second closes field (keep as ")
                        result.append("'")
                        result.append('"')
                        i += 1  # Skip the second quote
                        in_quotes = False
                    else:
                        # Pattern: ""X where X is not delimiter - this is escaped quote (literal quote)
                        result.append('""')
                        i += 1  # Skip next quote
                else:
                    # Quote followed by non-quote, non-delimiter - this is a nested quote
                    result.append("'")
        else:
            result.append(char)
        
        i += 1
    
    return ''.join(result)


def fix_csv_file(input_path: str, output_path: str = None):
    """
    Fix nested quotation marks in a CSV file.
    
    Args:
        input_path: Path to input CSV file
        output_path: Path to output CSV file (if None, overwrites input file)
    """
    input_file = Path(input_path)
    if not input_file.exists():
        print(f"Error: File {input_path} not found", file=sys.stderr)
        sys.exit(1)
    
    if output_path is None:
        output_path = input_path
    
    output_file = Path(output_path)
    
    print(f"Reading {input_file}...")
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    print(f"Processing {len(lines)} lines...")
    fixed_lines = []
    for i, line in enumerate(lines, 1):
        fixed_line = fix_nested_quotes(line)
        fixed_lines.append(fixed_line)
        if i % 1000 == 0:
            print(f"Processed {i} lines...")
    
    print(f"Writing to {output_file}...")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.writelines(fixed_lines)
    
    print("Done!")


if __name__ == "__main__":
    # Default to scimagojr.csv in the same directory
    script_dir = Path(__file__).parent
    default_input = script_dir / "scimagojr.csv"
    
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
        output_file = sys.argv[2] if len(sys.argv) > 2 else None
    else:
        input_file = str(default_input)
        output_file = None
    
    fix_csv_file(input_file, output_file)

