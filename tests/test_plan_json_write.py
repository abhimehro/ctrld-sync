"""Focused regression tests for secure plan JSON writes."""

import json
import stat

import pytest

import main
from models import PlanEntry


def test_write_plan_json_is_atomic_and_owner_only(tmp_path):
    plan_path = tmp_path / "plans" / "plan.json"
    plan = [PlanEntry(profile="dry-run-placeholder", folders=[])]

    main._write_plan_json(str(plan_path), plan)

    assert json.loads(plan_path.read_text(encoding="utf-8")) == plan
    assert stat.S_IMODE(plan_path.stat().st_mode) == 0o600
    assert list(plan_path.parent.glob(f".{plan_path.name}.*.tmp")) == []


def test_write_plan_json_removes_temp_file_when_serialization_fails(
    monkeypatch, tmp_path
):
    plan_path = tmp_path / "plan.json"

    def fail_dump(*_args, **_kwargs):
        raise TypeError("serialization failed")

    monkeypatch.setattr(main.json, "dump", fail_dump)

    with pytest.raises(TypeError, match="serialization failed"):
        main._write_plan_json(
            str(plan_path), [PlanEntry(profile="dry-run-placeholder", folders=[])]
        )

    assert not plan_path.exists()
    assert list(tmp_path.glob(f".{plan_path.name}.*.tmp")) == []
