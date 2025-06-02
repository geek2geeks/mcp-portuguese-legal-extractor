#!/usr/bin/env python3
"""
Production-Ready PDF Metadata Extractor for Portuguese Legal Documents

Features:
- Works with or without ground truth data
- User-friendly interface with clear feedback
- Robust error handling and validation
- Comprehensive confidence scoring
- Clean, maintainable code structure
"""

import pdfplumber
import json
import os
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union, Any
from pathlib import Path


class PortugueseLegalPDFExtractor:
    """
    Production-ready extractor for Portuguese legal document metadata.
    
    Features:
    - Automatic field structure detection
    - Flexible confidence calculation (with/without ground truth)
    - Comprehensive error handling
    - User-friendly progress reporting
    """
    
    def __init__(self, ground_truth_path: Optional[str] = None, verbose: bool = True):
        """
        Initialize the extractor.
        
        Args:
            ground_truth_path: Optional path to ground truth JSON file for accuracy validation
            verbose: Whether to print progress messages
        """
        self.verbose = verbose
        self.ground_truth = {}
        
        # Load ground truth if provided
        if ground_truth_path:
            self._load_ground_truth(ground_truth_path)
        
        # Expected field order as discovered in document analysis
        self.FIELD_ORDER = [
            # Left column (top to bottom)
            "Relator", "Apenso", "Data de decisão sumária", "Tribunal de recurso", 
            "Data", "Referência de processo de recurso", "Meio Processual", 
            "Indicações eventuais",
            # Right column (top to bottom)  
            "Nº do Documento", "Data do Acordão", "Votação", "Processo de recurso",
            "Recurso", "Nível de acesso", "Decisão", "Área Temática",
            # Full-width fields (bottom)
            "Referências Internacionais", "Jurisprudência Nacional", 
            "Legislação Comunitária", "Legislação Estrangeira", "Descritores"        ]
        
        # Field pairs that should be synchronized (left-right columns)
        self.FIELD_PAIRS = [
            ("Relator", "Nº do Documento"),
            ("Apenso", "Data do Acordão"),
            ("Data de decisão sumária", "Votação"),
            ("Tribunal de recurso", "Processo de recurso"),
            ("Data", "Área Temática"),
        ]
        
        # Layout constants
        self.LEFT_COLUMN_X = 50
        self.RIGHT_COLUMN_X = 300
        self.COORDINATE_TOLERANCE = 10
    
    def _load_ground_truth(self, ground_truth_path: str) -> None:
        """Load ground truth data for accuracy validation."""
        try:
            with open(ground_truth_path, 'r', encoding='utf-8') as f:
                gt_data = json.load(f)
                
                # Handle both old format (list) and new format (dict)
                if isinstance(gt_data, list):
                    # Old format: list of items with ECLI field
                    for item in gt_data:
                        ecli = item.get('ECLI', '')
                        if ecli:
                            self.ground_truth[ecli] = item
                elif isinstance(gt_data, dict):
                    # New format: filename -> fields mapping
                    for filename, fields in gt_data.items():
                        # Use ECLI from fields as key, fallback to filename
                        ecli = fields.get('ECLI', filename)
                        self.ground_truth[ecli] = fields
            
            if self.verbose:
                print(f"✓ Loaded ground truth for {len(self.ground_truth)} documents")
        
        except Exception as e:
            if self.verbose:
                print(f"⚠ Could not load ground truth: {e}")
    
    def _log(self, message: str, level: str = "info") -> None:
        """Log message if verbose mode is enabled."""
        if self.verbose:
            prefix = {"info": "ℹ", "success": "✓", "warning": "⚠", "error": "✗"}
            print(f"{prefix.get(level, 'ℹ')} {message}")
    
    def clean_field_value(self, raw_value: str) -> str:
        """Clean and normalize extracted field values."""
        if not raw_value:
            return ""
        
        # Remove excessive whitespace and normalize
        cleaned = re.sub(r'\s+', ' ', raw_value.strip())
        
        # Remove common extraction artifacts
        cleaned = re.sub(r'^[:\-\s]+', '', cleaned)  # Leading punctuation        cleaned = re.sub(r'[:\-\s]+$', '', cleaned)  # Trailing punctuation
        
        return cleaned
    
    def extract_ecli_from_text(self, text: str) -> str:
        """Extract ECLI identifier from document text."""
        ecli_pattern = r'ECLI:PT:[A-Z]{2,4}:\d{4}:[A-Za-z0-9\.\-]+'
        match = re.search(ecli_pattern, text, re.IGNORECASE)
        return match.group(0) if match else ""
    
    def calculate_field_confidence(self, field_name: str, extracted_value: str, 
                                 ground_truth_value: Optional[str] = None) -> Dict[str, Any]:
        """
        Calculate confidence for a single field.
        
        Returns detailed confidence information including match type and status.
        """
        if ground_truth_value is None:
            # Population-based confidence when no ground truth available
            return {
                "confidence": 1.0 if extracted_value.strip() else 0.0,
                "match_type": "populated" if extracted_value.strip() else "empty",
                "status": "populated" if extracted_value.strip() else "empty",
                "method": "population_based"
            }
        
        # Accuracy-based confidence with ground truth
        extracted = extracted_value.strip()
        expected = ground_truth_value.strip()
        
        if not expected and not extracted:
            return {"confidence": 1.0, "match_type": "both_empty", "status": "correct", "method": "accuracy_based"}
        
        if not expected and extracted:
            return {"confidence": 0.8, "match_type": "extra_extracted", "status": "extra", "method": "accuracy_based"}
        
        if expected and not extracted:
            return {"confidence": 0.0, "match_type": "missing_extracted", "status": "missing", "method": "accuracy_based"}
        
        # Both have content - compare quality
        if extracted == expected:
            return {"confidence": 1.0, "match_type": "exact", "status": "correct", "method": "accuracy_based"}
        
        if extracted.lower() == expected.lower():
            return {"confidence": 0.95, "match_type": "case_diff", "status": "acceptable", "method": "accuracy_based"}
        
        # Check for punctuation differences
        extracted_clean = re.sub(r'[^\w\s]', '', extracted.lower())
        expected_clean = re.sub(r'[^\w\s]', '', expected.lower())
        
        if extracted_clean == expected_clean:
            return {"confidence": 0.9, "match_type": "punctuation_diff", "status": "acceptable", "method": "accuracy_based"}
        
        # Check for partial matches
        if extracted_clean in expected_clean or expected_clean in extracted_clean:
            return {"confidence": 0.7, "match_type": "partial", "status": "partial", "method": "accuracy_based"}
        
        return {"confidence": 0.0, "match_type": "mismatch", "status": "incorrect", "method": "accuracy_based"}
    
    def extract_from_tables(self, tables: List) -> Dict[str, str]:
        """Extract metadata using PDF table structure (primary method)."""
        extracted = {}
        
        if not tables:
            return extracted
        
        for table in tables:
            if len(table) >= 2 and len(table[0]) >= 1 and len(table[1]) >= 1:
                field_name_raw = table[0][0] if table[0][0] else ""
                field_value_raw = table[1][0] if table[1][0] else ""
                
                field_name = self.clean_field_value(field_name_raw)
                field_value = self.clean_field_value(field_value_raw)
                
                if field_name and field_name in self.FIELD_ORDER:
                    extracted[field_name] = field_value
        
        return extracted
    
    def extract_from_coordinates(self, page, words: List[Dict], text: str) -> Dict[str, str]:
        """Fallback extraction using coordinate analysis."""
        extracted = {}
        if not words or page is None:
            return extracted
        
        # Simplified coordinate-based extraction
        # This is a fallback method - implement as needed
        for field_name in self.FIELD_ORDER:
            search_results = page.search(field_name, regex=False, case=False)
            if search_results:
                # Simple extraction logic - can be enhanced
                extracted[field_name] = ""
        
        return extracted
    
    def validate_extraction(self, extracted: Dict[str, str], text: str) -> Dict[str, str]:
        """Validate and enhance extraction results."""
        validated = extracted.copy()
        
        # Always try to extract ECLI
        ecli = self.extract_ecli_from_text(text)
        if ecli:
            validated['ECLI'] = ecli
        
        # Ensure all expected fields are present
        for field in self.FIELD_ORDER:
            if field not in validated:
                validated[field] = ""
        
        # Validate date format for "Data do Acordão"
        if 'Data do Acordão' in validated and validated['Data do Acordão']:
            date_value = validated['Data do Acordão']
            if not re.match(r'\d{2}/\d{2}/\d{4}', date_value):                # Try to find a valid date in the text
                date_match = re.search(r'\d{2}/\d{2}/\d{4}', text)
                if date_match:
                    validated['Data do Acordão'] = date_match.group(0)
        
        return validated
    
    def calculate_overall_confidence(self, extracted_fields: Dict[str, str], 
                                   ecli: Optional[str] = None) -> Dict[str, Any]:
        """Calculate overall confidence and detailed metrics."""
        
        # Get ground truth if available
        ground_truth_data = self.ground_truth.get(ecli) if ecli else None
        
        confidence_result = {
            "overall_confidence": 0.0,
            "field_confidences": {},
            "method": "population_based",
            "metrics": {
                "total_fields": len(self.FIELD_ORDER) + 1,  # +1 for ECLI
                "populated_fields": 0,
                "empty_fields": 0
            }
        }
        
        if ground_truth_data:
            # Accuracy-based confidence
            confidence_result["method"] = "accuracy_based"
            total_confidence = 0.0
            populated_in_gt = 0
            correct_extractions = 0
            acceptable_extractions = 0
            
            all_fields = set(self.FIELD_ORDER + ['ECLI'])
            
            for field in all_fields:
                extracted_value = extracted_fields.get(field, "")
                gt_value = ground_truth_data.get(field, "")
                
                field_conf = self.calculate_field_confidence(field, extracted_value, gt_value)
                confidence_result["field_confidences"][field] = field_conf
                total_confidence += field_conf["confidence"]
                
                if gt_value.strip():
                    populated_in_gt += 1
                    if field_conf["status"] == "correct":
                        correct_extractions += 1
                    if field_conf["status"] in ["correct", "acceptable"]:
                        acceptable_extractions += 1
            
            # Overall confidence based on populated fields in ground truth
            if populated_in_gt > 0:
                confidence_result["overall_confidence"] = acceptable_extractions / populated_in_gt
            else:
                confidence_result["overall_confidence"] = total_confidence / len(all_fields)
            
            confidence_result["metrics"].update({
                "populated_in_ground_truth": populated_in_gt,
                "correct_extractions": correct_extractions,
                "acceptable_extractions": acceptable_extractions,
                "exact_match_rate": correct_extractions / populated_in_gt if populated_in_gt > 0 else 0,
                "acceptable_match_rate": acceptable_extractions / populated_in_gt if populated_in_gt > 0 else 0
            })
        
        else:
            # Population-based confidence (fallback)
            populated_count = sum(1 for v in extracted_fields.values() if v.strip())
            confidence_result["overall_confidence"] = populated_count / (len(self.FIELD_ORDER) + 1)
            confidence_result["metrics"]["populated_fields"] = populated_count
            confidence_result["metrics"]["empty_fields"] = (len(self.FIELD_ORDER) + 1) - populated_count
              # Add field-level population confidence
            for field in self.FIELD_ORDER + ['ECLI']:
                value = extracted_fields.get(field, "")
                confidence_result["field_confidences"][field] = self.calculate_field_confidence(field, value)
        
        return confidence_result
    
    def extract_metadata(self, pdf_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Main extraction method that processes a single PDF.
        
        Returns comprehensive extraction results with confidence analysis.
        """
        pdf_path = Path(pdf_path)
        result = {
            'filename': pdf_path.name,
            'extraction_timestamp': datetime.now().isoformat(),
            'extracted_fields': {},
            'extraction_method': 'unknown',
            'confidence_analysis': {},
            'issues': [],
            'success': False
        }
        
        try:
            self._log(f"Processing {pdf_path.name}...")
            
            with pdfplumber.open(pdf_path) as pdf:
                if not pdf.pages:
                    result['issues'].append("No pages found in PDF")
                    return result
                
                # Process first page (contains all metadata)
                page = pdf.pages[0]
                text = page.extract_text() or ""
                words = page.extract_words(keep_blank_chars=True) or []
                tables = page.extract_tables() or []
                
                # Method 1: Try table-based extraction (primary)
                table_extracted = self.extract_from_tables(tables)
                
                # Method 2: Try coordinate-based extraction (fallback)
                coord_extracted = self.extract_from_coordinates(page, words, text)
                
                # Choose best extraction method
                min_fields_threshold = len(self.FIELD_ORDER) * 0.3
                if len(table_extracted) >= min_fields_threshold or len(table_extracted) >= len(coord_extracted):
                    extracted = table_extracted
                    result['extraction_method'] = 'table_based'
                else:
                    extracted = coord_extracted
                    result['extraction_method'] = 'coordinate_based'
                
                # Validate and enhance
                validated = self.validate_extraction(extracted, text)
                result['extracted_fields'] = validated
                
                # Calculate confidence
                ecli = validated.get('ECLI', '')
                confidence_analysis = self.calculate_overall_confidence(validated, ecli)
                result['confidence_analysis'] = confidence_analysis                # Log extraction results
                total_extracted_fields = len(validated)
                populated_count = sum(1 for v in validated.values() if v.strip())
                
                if confidence_analysis['method'] == 'accuracy_based':
                    # When we have ground truth, show accuracy-based metrics
                    ecli = validated.get('ECLI', '')
                    gt_data = self.ground_truth.get(ecli, {}) if ecli else {}
                    expected_total_fields = len(gt_data) if gt_data else 0
                    
                    if expected_total_fields > 0:
                        self._log(f"Extracted {total_extracted_fields} fields ({populated_count} populated, expected: {expected_total_fields})", "success")
                    else:
                        self._log(f"Extracted {total_extracted_fields} fields ({populated_count} populated)", "success")
                else:
                    # When no ground truth, show total extracted and populated counts
                    self._log(f"Extracted {total_extracted_fields} fields ({populated_count} populated)", "success")
                
                if confidence_analysis['method'] == 'accuracy_based':
                    accuracy = confidence_analysis['overall_confidence']
                    self._log(f"Accuracy: {accuracy:.1%}", "success")
                else:
                    population = confidence_analysis['overall_confidence']
                    self._log(f"Population coverage: {population:.1%}", "success")
                
                # Add warnings for common issues
                if len(tables) == 0:
                    result['issues'].append("No tables found - used fallback method")
                if not ecli:
                    result['issues'].append("ECLI not found in document")
                
                result['success'] = True
                
        except Exception as e:
            result['issues'].append(f"Extraction error: {str(e)}")
            self._log(f"Error processing {pdf_path.name}: {str(e)}", "error")
        
        return result
    
    def extract_batch(self, pdf_directory: Union[str, Path], output_directory: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
        """
        Extract metadata from all PDFs in a directory.
        
        Args:
            pdf_directory: Directory containing PDF files
            output_directory: Directory to save results (optional)
        
        Returns:
            Summary of batch extraction results
        """
        pdf_dir = Path(pdf_directory)
        if not pdf_dir.exists():
            raise ValueError(f"PDF directory does not exist: {pdf_directory}")
        
        # Find all PDF files
        pdf_files = list(pdf_dir.glob("*.pdf"))
        if not pdf_files:
            raise ValueError(f"No PDF files found in: {pdf_directory}")
        
        self._log(f"Found {len(pdf_files)} PDF files to process", "info")
          # Setup output directory
        output_dir = None
        if output_directory:
            output_dir = Path(output_directory)
            output_dir.mkdir(exist_ok=True)
        
        # Process all PDFs
        results = []
        successful_extractions = 0
        
        for pdf_file in pdf_files:
            result = self.extract_metadata(pdf_file)
            results.append(result)
            
            if result['success']:
                successful_extractions += 1
              # Save individual result if output directory provided
            if output_directory and output_dir:
                output_file = output_dir / f"{pdf_file.stem}_extraction.json"
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
        
        # Generate summary
        summary = self._generate_batch_summary(results)
          # Save summary if output directory provided
        if output_directory and output_dir:
            summary_file = output_dir / "extraction_summary.json"
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
        
        # Print summary
        self._print_batch_summary(summary)
        
        return summary
    
    def _generate_batch_summary(self, results: List[Dict]) -> Dict[str, Any]:
        """Generate comprehensive summary of batch extraction."""
        
        successful_results = [r for r in results if r['success']]
        
        summary = {
            'total_processed': len(results),
            'successful_extractions': len(successful_results),
            'failed_extractions': len(results) - len(successful_results),
            'success_rate': len(successful_results) / len(results) if results else 0,
            'extraction_methods': {
                'table_based': sum(1 for r in successful_results if r['extraction_method'] == 'table_based'),
                'coordinate_based': sum(1 for r in successful_results if r['extraction_method'] == 'coordinate_based')
            },
            'confidence_statistics': {},
            'field_analysis': {},
            'timestamp': datetime.now().isoformat()
        }
        
        if successful_results:
            # Calculate confidence statistics
            confidences = [r['confidence_analysis']['overall_confidence'] for r in successful_results]
            summary['confidence_statistics'] = {
                'average_confidence': sum(confidences) / len(confidences),
                'min_confidence': min(confidences),
                'max_confidence': max(confidences),
                'method_distribution': {}
            }
            
            # Method distribution
            methods = [r['confidence_analysis']['method'] for r in successful_results]
            for method in set(methods):
                summary['confidence_statistics']['method_distribution'][method] = methods.count(method)
            
            # Field analysis
            field_stats = {}
            for field in self.FIELD_ORDER + ['ECLI']:
                populated_count = sum(1 for r in successful_results 
                                    if r['extracted_fields'].get(field, '').strip())
                field_stats[field] = {
                    'population_rate': populated_count / len(successful_results),
                    'populated_documents': populated_count,
                    'total_documents': len(successful_results)
                }
            
            summary['field_analysis'] = field_stats
            
            # Accuracy metrics (if ground truth available)
            accuracy_based_results = [r for r in successful_results 
                                    if r['confidence_analysis']['method'] == 'accuracy_based']
            
            if accuracy_based_results:
                total_correct = sum(r['confidence_analysis']['metrics'].get('correct_extractions', 0) 
                                  for r in accuracy_based_results)
                total_acceptable = sum(r['confidence_analysis']['metrics'].get('acceptable_extractions', 0) 
                                     for r in accuracy_based_results)
                total_populated = sum(r['confidence_analysis']['metrics'].get('populated_in_ground_truth', 0) 
                                    for r in accuracy_based_results)
                
                summary['accuracy_metrics'] = {
                    'documents_with_ground_truth': len(accuracy_based_results),
                    'total_populated_fields': total_populated,
                    'exact_match_rate': total_correct / total_populated if total_populated > 0 else 0,
                    'acceptable_match_rate': total_acceptable / total_populated if total_populated > 0 else 0
                }
        
        return summary
    
    def _print_batch_summary(self, summary: Dict) -> None:
        """Print user-friendly batch summary."""
        print("\n" + "="*60)
        print("📊 EXTRACTION SUMMARY")
        print("="*60)
        
        # Basic statistics
        print(f"📁 Total documents processed: {summary['total_processed']}")
        print(f"✅ Successful extractions: {summary['successful_extractions']}")
        print(f"❌ Failed extractions: {summary['failed_extractions']}")
        print(f"📈 Success rate: {summary['success_rate']:.1%}")
        
        if summary['successful_extractions'] > 0:
            # Method distribution
            methods = summary['extraction_methods']
            print(f"\n🔧 Extraction methods:")
            print(f"   Table-based: {methods['table_based']}")
            print(f"   Coordinate-based: {methods['coordinate_based']}")
            
            # Confidence statistics
            conf_stats = summary['confidence_statistics']
            print(f"\n📊 Confidence statistics:")
            print(f"   Average: {conf_stats['average_confidence']:.1%}")
            print(f"   Range: {conf_stats['min_confidence']:.1%} - {conf_stats['max_confidence']:.1%}")
            
            # Accuracy metrics (if available)
            if 'accuracy_metrics' in summary:
                acc_metrics = summary['accuracy_metrics']
                print(f"\n🎯 Accuracy metrics (with ground truth):")
                print(f"   Documents validated: {acc_metrics['documents_with_ground_truth']}")
                print(f"   Exact match rate: {acc_metrics['exact_match_rate']:.1%}")
                print(f"   Acceptable match rate: {acc_metrics['acceptable_match_rate']:.1%}")
            
            # Field statistics
            field_analysis = summary['field_analysis']
            high_population_fields = sum(1 for stats in field_analysis.values() 
                                       if stats['population_rate'] > 0.8)
            
            print(f"\n📝 Field analysis:")
            print(f"   Fields with >80% population: {high_population_fields}/{len(field_analysis)}")
            print(f"   Most populated field: {max(field_analysis.keys(), key=lambda k: field_analysis[k]['population_rate'])}")
        
        print("="*60)


def main():
    """Command-line interface for the extractor."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Extract metadata from Portuguese legal PDFs")
    parser.add_argument("pdf_path", help="Path to PDF file or directory containing PDFs")
    parser.add_argument("-o", "--output", help="Output directory for results")
    parser.add_argument("-g", "--ground-truth", help="Path to ground truth JSON file")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress progress messages")
    parser.add_argument("--single", action="store_true", help="Process single file (default: auto-detect)")
    
    args = parser.parse_args()
    
    # Initialize extractor
    extractor = PortugueseLegalPDFExtractor(
        ground_truth_path=args.ground_truth,
        verbose=not args.quiet
    )
    
    pdf_path = Path(args.pdf_path)
    
    # Determine processing mode
    if args.single or pdf_path.is_file():
        # Single file processing
        if not pdf_path.exists():
            print(f"Error: File not found: {pdf_path}")
            return 1
        
        result = extractor.extract_metadata(str(pdf_path))
        
        if args.output:
            output_dir = Path(args.output)
            output_dir.mkdir(exist_ok=True)
            output_file = output_dir / f"{pdf_path.stem}_extraction.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"Results saved to: {output_file}")
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
    
    elif pdf_path.is_dir():
        # Batch processing
        try:
            summary = extractor.extract_batch(str(pdf_path), args.output)
            if args.output:
                print(f"Results saved to: {args.output}")
        except ValueError as e:
            print(f"Error: {e}")
            return 1
    
    else:
        print(f"Error: Path not found: {pdf_path}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())