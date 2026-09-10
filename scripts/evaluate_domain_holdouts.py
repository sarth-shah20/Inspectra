"""Provisional cross-domain NER evaluation on compatible AI-assisted entity labels."""
from __future__ import annotations
import argparse,json,random
from pathlib import Path
import spacy
from spacy.training import Example
from spacy.util import fix_random_seed

def ex(nlp,row,labels=None):
    ents=[(e['evidence_start'],e['evidence_end'],e['label']) for e in row['entities'] if labels is None or e['label'] in labels]
    return Example.from_dict(nlp.make_doc(row['clean_text']),{'entities':ents})
def score(nlp,rows,labels):
    p,g=set(),set()
    for i,r in enumerate(rows):
        p|={(i,e.start_char,e.end_char,e.label_) for e in nlp(r['clean_text']).ents if e.label_ in labels}
        g|={(i,e['evidence_start'],e['evidence_end'],e['label']) for e in r['entities'] if e['label'] in labels}
    c=len(p&g); precision=c/len(p) if p else 0; recall=c/len(g) if g else 0
    return {'records':len(rows),'compatible_labels':sorted(labels),'predicted_entities':len(p),'reference_entities':len(g),'exact_precision':precision,'exact_recall':recall,'exact_f1':2*precision*recall/(precision+recall) if precision+recall else 0}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,default=Path('data/annotations/ai_annotated.jsonl'));p.add_argument('--output',type=Path,default=Path('reports/provisional_heldout_domain_evaluation.json'));a=p.parse_args()
 if a.output.exists():p.error('refusing to overwrite report')
 rows=[json.loads(x) for x in a.input.open()]; report={'scope':'Provisional evaluation against AI-assisted labels only; not human-validated generalization performance.','experiments':{}}
 for heldout in ('construction','aviation','pipeline'):
  train=[r for r in rows if r['split']=='train' and r['domain']!=heldout]; test=[r for r in rows if r['split']=='test' and r['domain']==heldout]
  labels={e['label'] for r in train for e in r['entities']} & {e['label'] for r in test for e in r['entities']}
  fix_random_seed(17);random.seed(17);nlp=spacy.blank('en');ner=nlp.add_pipe('ner')
  for x in labels:ner.add_label(x)
  examples=[ex(nlp,r,labels) for r in train]; opt=nlp.initialize(lambda:examples)
  for _ in range(12):
   random.shuffle(examples)
   for batch in spacy.util.minibatch(examples,size=8):nlp.update(batch,sgd=opt,drop=.25)
  report['experiments'][heldout]=score(nlp,test,labels)|{'train_records':len(train),'heldout_domain':heldout}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:round(v['exact_f1'],4) for k,v in report['experiments'].items()}))
if __name__=='__main__':main()
