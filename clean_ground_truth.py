#!/usr/bin/env python3
"""
Clean ground truth JSON by removing extraction metadata and keeping only 
filename -> extracted_fields mappings.
"""

import json
from pathlib import Path

def clean_ground_truth():
    """Remove extraction metadata from ground_truth.json"""
    input_file = Path("ground_truth/ground_truth.json")
    output_file = Path("ground_truth/ground_truth_clean.json")
    backup_file = Path("ground_truth/ground_truth_backup.json")
    
    # Read current ground truth
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Create backup
    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"Created backup at {backup_file}")
    
    # Clean the data - keep only filename and extracted_fields
    cleaned_data = {}
    
    for entry in data:
        filename = entry["filename"]
        extracted_fields = entry["extracted_fields"]
        cleaned_data[filename] = extracted_fields
    
    # Write cleaned data to new file first
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(cleaned_data, f, indent=2, ensure_ascii=False)
    
    print(f"Created cleaned version at {output_file}")
    print(f"Original had {len(data)} entries, cleaned has {len(cleaned_data)} entries")
    
    # Show sample of cleaned format
    sample_filename = list(cleaned_data.keys())[0]
    print(f"\nSample cleaned entry for {sample_filename}:")
    print(f"Fields: {list(cleaned_data[sample_filename].keys())}")
    
    return cleaned_data

if __name__ == "__main__":
    clean_ground_truth()