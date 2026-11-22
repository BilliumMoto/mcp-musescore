"""Tests of the cursor tools' voice and staff options, no MuseScore.

The tools only pass these options on to the plugin, where MuseScore does the
writing, so these tests check what reaches the plugin: the option when given,
nothing when left out, and a refusal before anything is sent for a bad value.
They don't cover the plugin's writing itself: that needs MuseScore, through the
headless plugin tests or a live check on a score.
"""

import asyncio

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

import server

WRITE_TOOLS = [
    # (tool, its arguments, the plugin action it sends)
    ("add_note", {"pitch": 60}, "addNote"),
    ("add_rest", {}, "addRest"),
    ("add_tuplet", {}, "addTuplet"),
    ("add_lyrics", {"lyrics": ["la"]}, "addLyrics"),
    ("add_tie", {}, "addTie"),
    (
        "add_tied_note",
        {"duration": {"numerator": 1, "denominator": 8}},
        "addTiedNote",
    ),
]

BAD_VOICES = [-1, 4, True, "1", 1.5]


def record_commands(monkeypatch):
    """Replace the plugin connection with a recorder of the commands sent.

    It answers barNumbers with an error (no score), so bars are sent as given.
    """
    calls = []

    async def fake_send_command(action, params=None):
        calls.append((action, params))
        if action == "barNumbers":
            return {"status": "error", "message": "no score in this test"}
        return {"status": "success", "result": {"success": True}}

    monkeypatch.setattr(server.client, "send_command", fake_send_command)
    return calls


def call(tool, args):
    async def run():
        async with Client(server.mcp) as client:
            return await client.call_tool(tool, args)

    return asyncio.run(run())


@pytest.mark.parametrize("tool,args,action", WRITE_TOOLS)
def test_write_tools_pass_the_voice_on(monkeypatch, tool, args, action):
    """Tested feature: write tools send a given voice, and none if left out.

    Check: called with voice=1 the plugin command carries voice 1; called
    without a voice it carries none, so the plugin writes in voice 1 (0).

    Mocks: the plugin connection (send_command) records commands instead.

    Test would be deprecated if: the write tools lose their voice option.
    """
    calls = record_commands(monkeypatch)
    call(tool, {**args, "voice": 1})
    call(tool, args)
    sent = [params for a, params in calls if a == action]
    assert len(sent) == 2
    assert sent[0]["voice"] == 1
    assert "voice" not in sent[1]


@pytest.mark.parametrize("voice", [0, 3])
def test_voice_accepts_both_ends(monkeypatch, voice):
    """Tested feature: voices 0 (voice 1) and 3 (voice 4) are accepted.

    Check: add_rest with each end of the range sends it unchanged.

    Mocks: the plugin connection (send_command) records commands instead.

    Test would be deprecated if: the voice option is removed or renumbered.
    """
    calls = record_commands(monkeypatch)
    call("add_rest", {"voice": voice})
    assert [p["voice"] for a, p in calls if a == "addRest"] == [voice]


@pytest.mark.parametrize("voice", BAD_VOICES)
@pytest.mark.parametrize("tool,args,action", WRITE_TOOLS)
def test_bad_voice_is_refused_before_sending(
    monkeypatch, tool, args, action, voice
):
    """Tested feature: write tools refuse any voice but an integer 0-3.

    Check: each write tool with an out-of-range, boolean, string or fractional
    voice raises ToolError and sends no command for it.

    Mocks: the plugin connection (send_command) records commands instead.

    Test would be deprecated if: the voice option is removed or renumbered.
    """
    calls = record_commands(monkeypatch)
    with pytest.raises(ToolError):
        call(tool, {**args, "voice": voice})
    assert not [a for a, _ in calls if a == action]


@pytest.mark.parametrize("voice", BAD_VOICES)
def test_bad_voice_in_a_sequence_is_refused_before_sending(monkeypatch, voice):
    """Tested feature: a sequence step with a bad voice is refused, not coerced.

    Check: processSequence with an addRest step whose voice is out of range,
    boolean, string or fractional raises ToolError and sends no sequence.

    Mocks: the plugin connection (send_command) records commands instead.

    Test would be deprecated if: sequence steps lose their voice option.
    """
    calls = record_commands(monkeypatch)
    step = {
        "action": "addRest",
        "params": {
            "duration": {"numerator": 1, "denominator": 4},
            "advanceCursorAfterAction": True,
            "voice": voice,
        },
    }
    with pytest.raises(ToolError):
        call("processSequence", {"sequence": [step]})
    assert not [a for a, _ in calls if a == "processSequence"]


def test_go_to_measure_passes_the_staff_on(monkeypatch):
    """Tested feature: go_to_measure sends a given staff, and none if left out.

    Check: with staff=4 the goToMeasure command carries staff 4; without it, no
    staff, so the plugin selects the bar on every staff as before.

    Mocks: the plugin connection (send_command) records commands instead, and
    answers barNumbers with an error, so the bar is sent unconverted.

    Test would be deprecated if: go_to_measure loses its staff option.
    """
    calls = record_commands(monkeypatch)
    call("go_to_measure", {"measure": 13, "staff": 4})
    call("go_to_measure", {"measure": 13})
    sent = [params for a, params in calls if a == "goToMeasure"]
    assert sent == [{"measure": 13, "staff": 4}, {"measure": 13}]


@pytest.mark.parametrize("staff", [-1, True, "2"])
def test_bad_staff_is_refused_before_sending(monkeypatch, staff):
    """Tested feature: a staff that isn't a non-negative integer is refused.

    Check: go_to_measure, and a goToMeasure sequence step, with a negative,
    boolean or string staff raise ToolError and send nothing for it.

    Mocks: the plugin connection (send_command) records commands instead.

    Test would be deprecated if: go_to_measure loses its staff option.
    """
    calls = record_commands(monkeypatch)
    with pytest.raises(ToolError):
        call("go_to_measure", {"measure": 13, "staff": staff})
    step = {"action": "goToMeasure", "params": {"measure": 13, "staff": staff}}
    with pytest.raises(ToolError):
        call("processSequence", {"sequence": [step]})
    assert not [a for a, _ in calls if a in ("goToMeasure", "processSequence")]
