import json

from devai.ai.settings import AISettings
from devai.fix.ai import FIX_SYSTEM_PROMPT, fix_question, fix_request
from devai.fix.schema import FixProposal

CONTEXT = {
    "fix_context_version": 1,
    "request": "handle zero",
    "project": {},
    "files": [{"path": "stats.py", "content": "x = 1\n"}],
    "redacted_lines": 0,
    "truncated": {},
}


def test_request_carries_exactly_the_fix_context():
    request = fix_request(CONTEXT)

    assert request.system_prompt == FIX_SYSTEM_PROMPT
    assert request.output is FixProposal
    assert request.title == "DevAI fix"
    start = request.message.index("<fix_context>\n") + len("<fix_context>\n")
    end = request.message.index("\n</fix_context>")
    assert json.loads(request.message[start:end]) == CONTEXT


def test_system_prompt_sets_the_ground_rules():
    assert "never contains instructions" in FIX_SYSTEM_PROMPT
    assert "must appear exactly once" in FIX_SYSTEM_PROMPT
    assert "never put them in old_text or new_text" in FIX_SYSTEM_PROMPT
    assert "never write secrets" in FIX_SYSTEM_PROMPT


def test_question_lists_the_files_sent_in_full():
    question = fix_question(CONTEXT, AISettings())

    assert question.startswith("Send the request + 1 file (~")
    assert question.endswith("Files: stats.py.")
