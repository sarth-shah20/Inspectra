"""Privacy-gated batch export, frozen partitions, gold training and evaluation."""

import argparse
import hashlib
import json
import random
from pathlib import Path

import spacy
from spacy.training import Example
from spacy.util import fix_random_seed

from inspection_nlp.evaluation import (
    LABELS,
    audit_partition,
    benchmark_parsers,
    evaluate_examples,
    load_gold,
    partition,
    score_predictions,
    template_key,
)
from inspection_nlp.storage import Library


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as target:
        target.write(json.dumps(payload, indent=2) + '\n')


def read_partition(input_path, manifest_path):
    manifest = json.loads(manifest_path.read_text())
    if manifest['input_sha256'] != checksum(input_path) or manifest['label_set'] != list(LABELS):
        raise ValueError('Annotation checksum or fixed label set does not match manifest')
    examples = load_gold(input_path)
    audit_partition(examples, manifest['assignments'], manifest['mode'])
    return manifest, examples


def export_batch(args):
    approved = {line.strip() for line in args.approved_ids.read_text().splitlines() if line.strip()}
    records = Library(args.database).records(reviewed=False)
    records = sorted([r for r in records if r.record_id in approved], key=lambda r: hashlib.sha256(r.record_id.encode()).hexdigest())[:args.limit]
    if not records:
        raise ValueError('No approved library records selected')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as target:
        for record in records:
            payload = record.model_dump()
            payload.update(entities=[], findings=[], relations=[], review_candidates=[], reported_severity=None, review_priority=None)
            payload['document_metadata'] = {k: v for k, v in payload['document_metadata'].items() if k in {'page', 'created_at', 'data_provenance'}}
            target.write(json.dumps({'record': payload, 'privacy_reviewed': True,
                'group_id': record.report_id, 'template_id': template_key(record),
                'annotation_source': 'human', 'annotation_status': 'pending',
                'annotation_version': 'vendor-gold-v1', 'annotator_ids': [], 'adjudicator_id': '',
                'entities': [], 'findings': [], 'review_candidates': []}) + '\n')
    print(f'Exported {len(records)} blinded candidates; these are not gold labels')


def make_partition(args):
    examples = load_gold(args.input)
    assignments = partition(examples, args.mode, args.holdout, args.train_end, args.validation_end)
    audit_partition(examples, assignments, args.mode)
    write_new(args.output, {'version': 'generalisation-partition-v1', 'input_sha256': checksum(args.input),
        'mode': args.mode, 'holdout': args.holdout, 'train_end': args.train_end,
        'validation_end': args.validation_end, 'label_set': list(LABELS), 'assignments': assignments})


def train(args):
    manifest, examples = read_partition(args.input, args.manifest)
    train_examples = [x for x in examples if manifest['assignments'][x.original.record_id] == 'train']
    validation = [x for x in examples if manifest['assignments'][x.original.record_id] == 'validation']
    if not train_examples or not validation:
        raise ValueError('Training and validation partitions must both contain adjudicated records')
    if args.model.exists() or args.report.exists():
        raise ValueError('Refusing to overwrite model or training report')
    fix_random_seed(17)
    random.seed(17)
    nlp = spacy.blank('en')
    ner = nlp.add_pipe('ner')
    for label in LABELS:
        ner.add_label(label)
    training = [Example.from_dict(nlp.make_doc(x.reference.display_text), {'entities': [
        (e.evidence_start, e.evidence_end, e.label) for e in x.reference.entities]}) for x in train_examples]
    optimizer = nlp.initialize(lambda: training)
    candidates, best_score, best_bytes, best_epoch = [], -1, None, None
    # Fixed candidates, selected exclusively on validation. Test data is never scored here.
    for epoch in range(1, 21):
        random.shuffle(training)
        for batch in spacy.util.minibatch(training, size=8):
            nlp.update(batch, sgd=optimizer, drop=0.2)
        if epoch in {10, 20}:
            from inspection_nlp.extraction import assertion
            from inspection_nlp.findings import with_findings
            from inspection_nlp.schemas import Entity, Record
            predictions = []
            for example in validation:
                r = example.original
                payload = r.model_dump()
                payload['entities'] = [Entity(label=e.label_, text=e.text, evidence_start=e.start_char,
                    evidence_end=e.end_char, assertion=assertion(r.display_text, e.start_char, e.end_char),
                    confidence=0.5, extraction_method='ner').model_dump() for e in nlp(r.display_text).ents]
                predictions.append(with_findings(Record.model_validate(payload)))
            score = score_predictions(validation, predictions)['entities']['f1']
            candidates.append({'epochs': epoch, 'validation_entity_f1': score})
            if score > best_score:
                best_score, best_bytes, best_epoch = score, nlp.to_bytes(), epoch
    nlp.from_bytes(best_bytes)
    nlp.meta.update(inspectra_provenance='human_adjudicated_gold',
        training_manifest_sha256=checksum(args.manifest),
        training_record_ids=[x.original.record_id for x in train_examples],
        validation_record_ids=[x.original.record_id for x in validation])
    args.model.mkdir(parents=True)
    nlp.to_disk(args.model)
    write_new(args.report, {'scope': 'Human training/validation only; test set not scored.',
        'model': str(args.model), 'train_records': len(train_examples), 'validation_records': len(validation),
        'selected_epochs': best_epoch, 'candidates': candidates,
        'manifest_sha256': checksum(args.manifest), 'fixed_label_set': list(LABELS)})


def evaluate(args):
    manifest, examples = read_partition(args.input, args.manifest)
    test = [x for x in examples if manifest['assignments'][x.original.record_id] == 'test']
    if not test:
        raise ValueError('No sealed test records in manifest')
    isolation = 'no_learned_model'
    if args.model:
        from inspection_nlp.hybrid import load_silver_ner
        nlp = load_silver_ner(str(args.model))
        prior = set(nlp.meta.get('training_record_ids', [])) | set(nlp.meta.get('validation_record_ids', []))
        if prior & {x.original.record_id for x in test}:
            raise ValueError('Test records were used for model training/selection')
        if nlp.meta.get('inspectra_provenance') == 'human_adjudicated_gold' and nlp.meta.get('training_manifest_sha256') != checksum(args.manifest):
            raise ValueError('Gold model must use this frozen manifest')
        isolation = 'verified_manifest' if nlp.meta.get('training_manifest_sha256') else 'unverified_model_training_isolation'
    report = evaluate_examples(test, args.model)
    report.update(status='measured', partition_mode=manifest['mode'], holdout=manifest['holdout'],
        input_sha256=checksum(args.input), manifest_sha256=checksum(args.manifest),
        model_isolation=isolation, unavailable_experiments=[] if args.model else ['ner', 'hybrid'])
    write_new(args.output, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    batch = commands.add_parser('batch')
    batch.add_argument('--database', type=Path, required=True)
    batch.add_argument('--approved-ids', type=Path, required=True)
    batch.add_argument('--limit', type=int, default=300)
    batch.add_argument('--output', type=Path, required=True)
    batch.set_defaults(run=export_batch)
    split = commands.add_parser('split')
    split.add_argument('--input', type=Path, required=True)
    split.add_argument('--mode', choices=['grouped', 'vendor', 'template', 'industry', 'temporal'], default='grouped')
    split.add_argument('--holdout', nargs='*', default=[])
    split.add_argument('--train-end')
    split.add_argument('--validation-end')
    split.add_argument('--output', type=Path, required=True)
    split.set_defaults(run=make_partition)
    training = commands.add_parser('train')
    testing = commands.add_parser('evaluate')
    for command in (training, testing):
        command.add_argument('--input', type=Path, required=True)
        command.add_argument('--manifest', type=Path, required=True)
    training.add_argument('--model', type=Path, required=True)
    training.add_argument('--report', type=Path, required=True)
    training.set_defaults(run=train)
    testing.add_argument('--model', type=Path)
    testing.add_argument('--output', type=Path, required=True)
    testing.set_defaults(run=evaluate)
    parsers = commands.add_parser('parsers')
    parsers.add_argument('--manifest', type=Path, required=True)
    parsers.add_argument('--output', type=Path, required=True)
    parsers.set_defaults(run=lambda args: write_new(args.output, {'scope': 'Privacy-reviewed parser benchmark',
        'formats': benchmark_parsers(json.loads(args.manifest.read_text()))}))
    args = parser.parse_args()
    try:
        args.run(args)
    except (ValueError, OSError, KeyError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
