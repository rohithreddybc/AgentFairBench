"""The released profile hashes must actually be enforced.

The manuscript states that the harness rejects a profile whose body no longer matches the
content hash released with it. That claim was false for two revisions: the hash was computed
as a property and never checked on load, so a silently edited profile loaded clean. These
tests exist so the claim cannot quietly become false again.
"""
import json

import pytest

from agentfairbench.data import Profile, ProfileIntegrityError, load_profiles

ROW = {
    "id": "hire_test",
    "domain": "hiring",
    "title": "Test profile",
    "content": "Five years of experience, strong references.",
    "difficulty": "borderline",
}


def _write(tmp_path, rows):
    p = tmp_path / "profiles.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


def _hashed(**overrides):
    row = dict(ROW, **overrides)
    row["content_sha256_16"] = Profile(
        id=row["id"], domain=row["domain"], title=row["title"],
        content=row["content"]).content_hash()
    return row


def test_matching_hash_loads(tmp_path):
    got = load_profiles(_write(tmp_path, [_hashed()]))
    assert len(got) == 1 and got[0].id == "hire_test"


def test_tampered_body_is_rejected(tmp_path):
    row = _hashed()
    row["content"] = row["content"] + " Also fluent in Portuguese."
    with pytest.raises(ProfileIntegrityError) as err:
        load_profiles(_write(tmp_path, [row]))
    assert "hire_test" in str(err.value)


def test_verification_can_be_disabled_deliberately(tmp_path):
    row = _hashed()
    row["content"] = "something else entirely"
    assert len(load_profiles(_write(tmp_path, [row]), verify_hashes=False)) == 1


def test_row_without_a_hash_still_loads(tmp_path):
    assert len(load_profiles(_write(tmp_path, [dict(ROW)]))) == 1


def test_released_public_split_verifies():
    """The shipped profiles must pass their own check."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    path = root / "data" / "profiles" / "public_dev.jsonl"
    if not path.exists():
        pytest.skip("public split not present")
    profiles = load_profiles(path)
    assert len(profiles) == 48
