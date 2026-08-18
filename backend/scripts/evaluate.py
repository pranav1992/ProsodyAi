"""Validation script for deliverables #6 (accuracy/F1/confusion matrix) and
#8 (latency). Run against the three labeled calls, or any labeled folder in
the same shape as the batch-upload format (audio files + labels.csv with
name/result_json columns).

Usage:
    python scripts/evaluate.py path/to/labeled_calls_dir

Note: thresholds in acoustic_features.py were hand-tuned against these three
calls, so accuracy reported here is optimistic relative to the hidden test
set -- see VALIDATION.md for the leave-one-call-out discussion.
"""
import json
import sys
from pathlib import Path

from sklearn.metrics import confusion_matrix, f1_score

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline.pipeline import run_pipeline  # noqa: E402
from app.utils.csv_manifest import parse_and_validate  # noqa: E402
from app.services.storage import SUPPORTED_AUDIO_EXTENSIONS  # noqa: E402

FIELDS = [
    "emotional_tone", "emotional_intensity", "background_noise_present",
    "background_noise_severity", "audio_quality", "speaker_overlap_present",
    "long_silence_present",
]


def main(labeled_dir: str) -> None:
    directory = Path(labeled_dir)
    manifest = next(directory.glob("*.csv"), None)
    if manifest is None:
        raise SystemExit(f"no CSV manifest found in {directory}")

    audio_files = {p.name for p in directory.iterdir() if p.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS}
    validation = parse_and_validate(manifest.read_bytes(), audio_files)
    if validation.errors:
        raise SystemExit(f"manifest errors: {validation.errors}")

    predictions, ground_truth, latencies_ms = [], [], []

    for filename, expected_json in validation.matched.items():
        if not expected_json:
            print(f"skipping {filename}: no ground truth in manifest")
            continue
        expected = json.loads(expected_json)
        outcome = run_pipeline(str(directory / filename))
        predicted = outcome.prediction.model_dump()

        predictions.append(predicted)
        ground_truth.append(expected)
        latencies_ms.append(outcome.processing_ms)

        print(f"\n{filename} ({outcome.duration_s:.1f}s audio, {outcome.processing_ms}ms processing)")
        for field in FIELDS:
            match = "OK" if predicted.get(field) == expected.get(field) else "MISMATCH"
            print(f"  {field:28s} pred={predicted.get(field)!s:20s} expected={expected.get(field)!s:20s} {match}")

    if not predictions:
        raise SystemExit("no labeled examples found to evaluate")

    print("\n=== Per-field accuracy ===")
    for field in FIELDS:
        correct = sum(1 for p, g in zip(predictions, ground_truth) if p.get(field) == g.get(field))
        print(f"  {field:28s} {correct}/{len(predictions)} = {correct / len(predictions):.2f}")

    tones_pred = [p["emotional_tone"] for p in predictions]
    tones_true = [g["emotional_tone"] for g in ground_truth]
    labels = sorted(set(tones_true) | set(tones_pred))
    print("\n=== emotional_tone macro F1 ===")
    print(f"  {f1_score(tones_true, tones_pred, labels=labels, average='macro', zero_division=0):.3f}")
    print("\n=== emotional_tone confusion matrix ===")
    print(f"  labels: {labels}")
    print(confusion_matrix(tones_true, tones_pred, labels=labels))

    print("\n=== Latency ===")
    print(f"  mean: {sum(latencies_ms) / len(latencies_ms):.0f}ms  max: {max(latencies_ms)}ms")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/evaluate.py path/to/labeled_calls_dir")
    main(sys.argv[1])
