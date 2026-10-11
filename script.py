"""Step 1: turn a topic into a scene-by-scene script.

Uses Claude (Anthropic API) by default, or any OpenRouter model as an
alternative. With no key at all it falls back to a simple template so the
rest of the pipeline can still be tested.
"""
import json
import os
import time

import requests

PROMPT = """You write scripts for short faceless YouTube videos.
Topic: {topic}

Return ONLY JSON in this shape:
{{"title": "...", "scenes": [{{"narration": "...", "search_query": "..."}}]}}

Rules:
- 5 to 7 scenes, about 60 to 90 seconds of narration in total.
- Scene 1 is a hook. Last scene is a short wrap-up.
- narration: 1-3 plain spoken sentences, no emojis, no stage directions.
- search_query: 2-4 words describing stock footage that fits the scene
  (concrete and visual, e.g. "ocean waves sunset", not abstract ideas)."""


def write_script(topic: str) -> dict:
    prompt = PROMPT.format(topic=topic)
    if os.getenv("ANTHROPIC_API_KEY"):
        text = _ask_claude(prompt)
    elif os.getenv("OPENROUTER_API_KEY"):
        text = _ask_openrouter(prompt)
    else:
        print("  no ANTHROPIC_API_KEY or OPENROUTER_API_KEY -> using template script")
        return _template(topic)

    # Models sometimes wrap JSON in ```fences```; strip them before parsing.
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    data = json.loads(text)
    scenes = data.get("scenes") or []
    if not scenes or not all(s.get("narration") and s.get("search_query") for s in scenes):
        raise ValueError(f"LLM returned an unusable script: {data}")
    return data


def _ask_claude(prompt: str) -> str:
    """Call Claude directly through Anthropic's Messages API."""
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5"),
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=90,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def _ask_openrouter(prompt: str) -> str:
    """Any model on OpenRouter. Free models are often rate-limited (429), so
    retry with backoff and let OpenRouter fall back to other models."""
    models = [os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")]
    models += [m.strip() for m in os.getenv("OPENROUTER_FALLBACK_MODELS", "").split(",") if m.strip()]
    for attempt in range(4):
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
            json={"models": models, "messages": [{"role": "user", "content": prompt}]},
            timeout=90,
        )
        if resp.status_code in (429, 502, 503) and attempt < 3:
            wait = 10 * 2 ** attempt  # 10s, 20s, 40s
            print(f"  OpenRouter {resp.status_code} (busy/rate-limited), retrying in {wait}s")
            time.sleep(wait)
            continue
        if not resp.ok:
            raise RuntimeError(f"OpenRouter {resp.status_code}: {resp.text[:300]}")
        return resp.json()["choices"][0]["message"]["content"]
    raise RuntimeError("OpenRouter retries exhausted")


def _template(topic: str) -> dict:
    lines = [
        (f"Here is something most people never think about: {topic}.", topic),
        (f"Let's start with the basics of {topic}, and why it matters.", topic + " closeup"),
        ("The details are more surprising than you might expect.", "city timelapse"),
        ("And the more you look, the more interesting it gets.", "nature aerial"),
        ("That's the story in under a minute. Follow for more.", "sunset sky"),
    ]
    return {"title": topic.title(), "scenes": [{"narration": n, "search_query": q} for n, q in lines]}
