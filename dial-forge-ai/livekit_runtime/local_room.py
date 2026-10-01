"""Start DialForge's browser/LiveKit-Meet local-room worker."""

from __future__ import annotations

import os


os.environ.setdefault("DIALFORGE_LOCAL_PROFILE", "local-room")

from livekit_runtime.local_voice_agent import main  # noqa: E402


if __name__ == "__main__":
    main()
