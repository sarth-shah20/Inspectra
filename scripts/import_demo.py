"""Import explicitly synthetic cross-industry examples into a local report library."""

import argparse
from pathlib import Path

from inspection_nlp.documents import parse_document
from inspection_nlp.extraction import extract
from inspection_nlp.storage import Library


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=Path('data/local/inspectra-demo.sqlite3'))
    args = parser.parse_args()
    sample = Path(__file__).resolve().parents[1] / 'samples/vendor_demo/synthetic_reports.csv'
    records = parse_document(sample.read_bytes(), sample.name, text_column='Inspection',
        metadata_columns={'vendor': 'Company', 'report_date': 'InspectionDate',
                          'report_number': 'ReportNumber', 'product': 'Product', 'batch': 'Batch', 'asset_id': 'Asset'})
    for record in records:
        record.document_metadata['data_provenance'] = 'synthetic_demo_not_real_inspection_data'
    saved = Library(args.database).save_run([extract(r) for r in records], {'demo': 'synthetic-vendor-v1'})
    print(f'Imported {len(saved)} synthetic narratives into {args.database}')


if __name__ == '__main__':
    main()
