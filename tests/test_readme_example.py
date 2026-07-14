"""Keep the README honest: the quickstart output and the version number in
the docs must match what the code actually produces.
"""

from pathlib import Path

import chatstencil
from chatstencil import render_chat

ROOT = Path(__file__).resolve().parent.parent


def test_quickstart_render_matches_the_readme_capture():
    # This is the exact call and the exact output shown in README Quickstart.
    out = render_chat(
        chatstencil.PRESETS["chatml"].source,
        [
            {"role": "system", "content": "You are a concise assistant. Answer in one sentence."},
            {"role": "user", "content": "What does a chat template do?"},
        ],
    )
    assert out == (
        "<|im_start|>system\n"
        "You are a concise assistant. Answer in one sentence.<|im_end|>\n"
        "<|im_start|>user\n"
        "What does a chat template do?<|im_end|>\n"
        "<|im_start|>assistant\n"
    )


def test_version_is_consistent_across_package_and_manifest():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f'version = "{chatstencil.__version__}"' in pyproject
    assert chatstencil.__version__ == "0.1.0"
