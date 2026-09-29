"""Compose reproducible aggregate evaluation tables and error-analysis notes from saved reports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def read(path): return json.loads(path.read_text())
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reports',type=Path,default=Path('reports'));p.add_argument('--output',type=Path,default=Path('reports/provisional_evaluation_summary.json'));a=p.parse_args()
 if a.output.exists():p.error('refusing to overwrite summary')
 r=a.reports; fire=read(r/'fire_door_baseline.json');faa=read(r/'faa-part-condition_baseline.json');phmsa=read(r/'phmsa-cause_baseline.json');ner=read(r/'silver_ner_evaluation.json');hold=read(r/'provisional_heldout_domain_evaluation.json');cal=read(r/'provisional_hybrid_calibration.json')
 rows=[{'experiment':'fire-door classification','scope':'source-specific','test_macro_f1':fire['test']['macro_f1'],'test_weighted_f1':fire['test']['weighted_f1']},{'experiment':'FAA PartCondition classification','scope':'source-specific temporal 2025','test_macro_f1':faa['test']['macro_f1'],'test_weighted_f1':faa['test']['weighted_f1']},{'experiment':'PHMSA cause classification','scope':'source-specific grouped','test_macro_f1':phmsa['test']['macro_f1'],'test_weighted_f1':phmsa['test']['weighted_f1']},{'experiment':'NER','scope':'provisional AI-assisted labels','test_exact_f1':ner['test']['exact_f1']}]
 summary={'scope':'All entity metrics are provisional: they use AI-assisted labels and are not human-validated performance.','evaluation_table':rows,'heldout_domain_provisional':hold['experiments'],'hybrid_calibration_provisional':cal,'error_analysis':['Construction holdout recall is low because the compact training vocabulary does not cover many fire-door terms.','Pipeline holdout recall is lower than aviation, indicating source-specific vocabulary and narrative-style dependence.','The hybrid threshold retains deterministic evidence at 0.75; model-only spans require review because spaCy span confidence is not calibrated.','Source classification taxonomies are incompatible across domains and are not used as shared-entity scores.','No metric supports compliance, engineering-risk, or deployment claims.']}
 a.output.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({'rows':len(rows),'heldout_domains':len(hold['experiments'])}))
if __name__=='__main__':main()
