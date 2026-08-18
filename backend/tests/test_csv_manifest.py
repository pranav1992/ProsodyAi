from app.utils.csv_manifest import parse_and_validate


def test_matches_rows_to_audio_files():
    csv_bytes = b'name,result_json\ncall_001.wav,"{""emotional_tone"":""neutral""}"\ncall_002.mp3,\n'
    result = parse_and_validate(csv_bytes, {"call_001.wav", "call_002.mp3"})

    assert result.matched == {
        "call_001.wav": '{"emotional_tone":"neutral"}',
        "call_002.mp3": "",
    }
    assert result.missing_audio == []
    assert result.unmatched_files == []
    assert result.errors == []


def test_reports_missing_audio_and_unmatched_files():
    csv_bytes = b"name,result_json\ncall_001.wav,\ncall_999.wav,\n"
    result = parse_and_validate(csv_bytes, {"call_001.wav", "call_002.wav"})

    assert result.matched == {"call_001.wav": ""}
    assert result.missing_audio == ["call_999.wav"]
    assert result.unmatched_files == ["call_002.wav"]


def test_requires_name_column():
    csv_bytes = b"filename,result_json\ncall_001.wav,\n"
    result = parse_and_validate(csv_bytes, {"call_001.wav"})

    assert result.matched == {}
    assert any("name" in e for e in result.errors)


def test_flags_duplicate_rows():
    csv_bytes = b"name,result_json\ncall_001.wav,\ncall_001.wav,\n"
    result = parse_and_validate(csv_bytes, {"call_001.wav"})

    assert len(result.matched) == 1
    assert any("duplicate" in e for e in result.errors)
