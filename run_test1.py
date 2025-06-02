import glob
import json
import os
from robust_extractor import RobustPDFExtractor

def main():
    pdf_dir = os.path.join(os.path.dirname(__file__), 'pdfs', 'test1')
    out_dir = os.path.join(os.path.dirname(__file__), 'test1results')
    gt_dir = os.path.join(os.path.dirname(__file__), 'ground_truth')

    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(gt_dir, exist_ok=True)

    extractor = RobustPDFExtractor(os.path.join(gt_dir, 'ground_truth.json'))
    results = []

    for pdf_file in sorted(glob.glob(os.path.join(pdf_dir, '*.pdf'))):
        res = extractor.extract_metadata(pdf_file)
        results.append(res)
        out_file = os.path.join(out_dir, os.path.basename(pdf_file) + '_extraction.json')
        with open(out_file, 'w', encoding='utf-8') as f:
            json.dump(res, f, indent=2, ensure_ascii=False)

    with open(os.path.join(gt_dir, 'ground_truth.json'), 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

if __name__ == '__main__':
    main()