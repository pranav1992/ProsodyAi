import csv
import io
from dataclasses import dataclass


@dataclass
class ManifestValidationResult:
    matched: dict[str, str]  # filename -> result_json string (may be empty)
    missing_audio: list[str]  # rows in CSV with no matching file
    unmatched_files: list[str]  # audio files with no CSV row
    errors: list[str]


def parse_and_validate(csv_bytes: bytes, audio_filenames: set[str]) -> ManifestValidationResult:
    errors: list[str] = []
    try:
        text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return ManifestValidationResult({}, [], list(audio_filenames), ["manifest is not valid UTF-8 text"])

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or "name" not in reader.fieldnames:
        errors.append('manifest is missing the required "name" column')
        return ManifestValidationResult({}, [], sorted(audio_filenames), errors)
    if "result_json" not in reader.fieldnames:
        errors.append('manifest is missing the required "result_json" column (may be empty per row)')

    matched: dict[str, str] = {}
    missing_audio: list[str] = []
    seen_names: set[str] = set()

    for row in reader:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        if name in seen_names:
            errors.append(f"duplicate manifest row for {name!r}")
            continue
        seen_names.add(name)
        if name not in audio_filenames:
            missing_audio.append(name)
            continue
        matched[name] = (row.get("result_json") or "").strip()

    unmatched_files = sorted(audio_filenames - seen_names)
    return ManifestValidationResult(matched, missing_audio, unmatched_files, errors)
