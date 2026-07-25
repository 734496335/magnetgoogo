from __future__ import annotations

import json
from pathlib import Path

from magnet.validate_enum import validate_sources


def test_repository_sources_contract_is_valid() -> None:
    root = Path(__file__).resolve().parents[2]
    count, errors = validate_sources(root / "sources.json")
    assert count == 241
    assert errors == []


def test_validator_rejects_invalid_enum_and_count(tmp_path: Path) -> None:
    path = tmp_path / "sources.json"
    path.write_text(
        json.dumps(
            {
                "rulesets": [
                    {
                        "rules": [
                            {
                                "id": "bad",
                                "health": {
                                    "status": "red",
                                    "status_detail": "unknown",
                                },
                                "quality": {"score": 101},
                            }
                        ]
                    }
                ],
                "meta": {"total_rules": 0},
            }
        ),
        encoding="utf-8",
    )

    count, errors = validate_sources(path)

    assert count == 1
    assert any("health.status" in error for error in errors)
    assert any("health.status_detail" in error for error in errors)
    assert any("quality.score" in error for error in errors)
    assert any("total_rules" in error for error in errors)
