"""Build aggregate source-wide analytics without reading narrative text."""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--snapshot",type=Path,default=Path("data/processed/corpus-v1")); p.add_argument("--output",type=Path,default=Path("reports/source_wide_analytics.json")); a=p.parse_args()
    if a.output.exists(): p.error("refusing to overwrite analytics artifact")
    db=sqlite3.connect(f"file:{(a.snapshot/'index.sqlite').resolve()}?mode=ro",uri=True)
    try:
        rows=db.execute("SELECT record_id,domain,label,group_id,grouped,temporal,official_safe,excluded,words,pii FROM records").fetchall()
    finally: db.close()
    domains=defaultdict(lambda:{"records":0,"excluded":0,"word_total":0,"pii_flagged":0,"labels":Counter(),"splits":Counter(),"unique_events":set()})
    for _,domain,label,group,grouped,temporal,official,excluded,words,pii in rows:
        item=domains[domain]; item["records"]+=1; item["excluded"]+=bool(excluded); item["word_total"]+=words or 0; item["pii_flagged"]+=bool(pii); item["labels"][label or "unlabelled"]+=1; item["unique_events"].add(group)
        split=official if domain=="construction" else temporal if domain=="aviation" else grouped
        item["splits"][split or "unassigned"]+=1
    report={"scope":"Aggregate metadata from frozen corpus-v1; no narrative text included.","domains":{}}
    for domain,item in sorted(domains.items()):
        report["domains"][domain]={"records":item["records"],"event_deduplicated_records":len(item["unique_events"]),"excluded":item["excluded"],"pii_pattern_flagged":item["pii_flagged"],"mean_words":round(item["word_total"]/item["records"],2),"split_counts":dict(sorted(item["splits"].items())),"source_label_counts":dict(item["labels"].most_common())}
    report["notes"]=["PHMSA counts use connected event groups as the event-deduplicated unit.","FAA temporal split uses source-file reporting year; 2026 is demo-only.","Counts describe report volume, not safety risk or incident rates."]
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({name:value["records"] for name,value in report["domains"].items()}))
if __name__=="__main__": main()
