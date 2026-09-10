"""Select a provisional hybrid confidence threshold on validation silver labels only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from inspection_nlp.hybrid import extract_hybrid
from inspection_nlp.schemas import Record


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,default=Path('data/annotations/ai_annotated.jsonl'));p.add_argument('--model',type=Path,default=Path('models/silver-ner-v1'));p.add_argument('--output',type=Path,default=Path('reports/provisional_hybrid_calibration.json'));a=p.parse_args()
 if a.output.exists():p.error('refusing to overwrite report')
 rows=[json.loads(x) for x in a.input.open() if json.loads(x)['split']=='validation']; results=[]
 for threshold in (.5,.75,.95):
  predicted,gold=set(),set()
  for i,row in enumerate(rows):
   r=Record(record_id=row['record_id'],source_dataset='silver',source_record_id=row['record_id'],source_event_id=row['group_id'],source_document='silver',source_sha256='silver',source_row=2,domain=row['domain'],schema_version='silver',source_column_mapping={},clean_text=row['clean_text'],display_text=row['clean_text'],label_origin='weak')
   predicted|={(i,e.evidence_start,e.evidence_end,e.label) for e in extract_hybrid(r,a.model).entities if e.confidence>=threshold}
   gold|={(i,e['evidence_start'],e['evidence_end'],e['label']) for e in row['entities']}
  c=len(predicted&gold);pr=c/len(predicted) if predicted else 0;re=c/len(gold) if gold else 0;results.append({'threshold':threshold,'precision':pr,'recall':re,'f1':2*pr*re/(pr+re) if pr+re else 0})
 best=max(results,key=lambda x:(x['f1'],x['threshold']));a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps({'scope':'Provisional calibration on AI-assisted validation labels only; not calibrated confidence for deployment.','selected_threshold':best['threshold'],'validation_candidates':results,'routing':'Below threshold: UNMAPPED when no retained entity; REVIEW_REQUIRED whenever an entity is retained.'},indent=2)+'\n');print(json.dumps(best))
if __name__=='__main__':main()
