"""Start DialForge's Linphone/livekit-sip local integration worker."""

from __future__ import annotations

import os


os.environ.setdefault("DIALFORGE_LOCAL_PROFILE", "local-sip")
os.environ.setdefault("DIALFORGE_IVR_DETECTION", "true")

from livekit_runtime.local_voice_agent import main  # noqa: E402


if __name__ == "__main__":
    main()
