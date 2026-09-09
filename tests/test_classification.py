from inspection_nlp.classification import (
    ClassificationExample,
    build_pipeline,
    class_counts,
    evaluate,
    predict,
)


def test_classification_pipeline_and_metrics():
    train = [
        ClassificationExample("1", "door has a frame gap", "gap"),
        ClassificationExample("2", "gap between fire door and frame", "gap"),
        ClassificationExample("3", "door closer needs adjustment", "closer"),
        ClassificationExample("4", "closer adjustment needed", "closer"),
    ]
    model = build_pipeline(c=1.0, class_weight=None)
    model.fit([item.text for item in train], [item.label for item in train])
    result = evaluate(model, train)
    assert result["macro_f1"] == 1.0
    assert result["predictions"][0] == {"record_id": "1", "actual": "gap", "predicted": "gap"}
    assert class_counts(train) == {"closer": 2, "gap": 2}
    prediction = predict(model, "frame gap found")
    assert prediction["label"] == "gap"
    assert 0 <= prediction["score"] <= 1
