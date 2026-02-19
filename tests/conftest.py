"""Shared fixtures for claude-wg tests."""

__authors__ = ["Dominik Dahlem"]
__status__ = "Development"

import pytest


@pytest.fixture
def sample_thread() -> dict:
    return {
        "owner": "U_ME",
        "ts": "111.111",
        "version": 1,
        "status": "awaiting_feedback",
        "approved": False,
        "approved_by": None,
        "files": ["auth/middleware.py"],
        "plan_versions": [
            {
                "version": 1,
                "text": "Initial plan",
                "posted_at": "2026-01-01T00:00:00+00:00",
            }
        ],
        "feedback": [],
    }


@pytest.fixture
def sample_state(sample_thread) -> dict:
    return {
        "channel_id": "C123",
        "channel_name": "wg_test",
        "created_by": "U_ME",
        "collaborators": ["U_BOB"],
        "threads": {"111.111": sample_thread},
    }
