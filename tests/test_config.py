"""Tests for config loading."""

from pathlib import Path

from ai_collab.config import load_workflow_config, _default_workflow


def test_default_workflow_has_three_roles():
    wf = _default_workflow()
    assert len(wf.roles) == 3
    assert wf.roles[0].role == "commander"
    assert wf.roles[0].is_primary is True


def test_default_workflow_has_review_enabled():
    wf = _default_workflow()
    assert wf.review.enabled is True
    assert wf.review.pass_threshold == 7.0


def test_load_workflow_fallback_to_default():
    wf = load_workflow_config("nonexistent", Path("/tmp/nonexistent"))
    assert wf.name == "default"
    assert len(wf.roles) == 3
