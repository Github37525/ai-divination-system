"""Generate short original UI sounds used by both native clients."""

from __future__ import annotations

import math
from pathlib import Path
import struct
import wave


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = (
    ROOT / "native" / "ios" / "DivinationApp" / "Resources",
    ROOT / "native" / "android" / "app" / "src" / "main" / "res" / "raw",
)
SAMPLE_RATE = 44_100


def synthesize(name: str, tones: list[tuple[float, float, float]]) -> None:
    duration = max(start + length for start, length, _ in tones)
    frames: list[bytes] = []
    for index in range(int(duration * SAMPLE_RATE)):
        time = index / SAMPLE_RATE
        sample = 0.0
        for start, length, frequency in tones:
            local = time - start
            if 0 <= local < length:
                envelope = math.exp(-local * 16.0) * min(local / 0.004, 1.0)
                fundamental = math.sin(2 * math.pi * frequency * local)
                overtone = 0.35 * math.sin(2 * math.pi * frequency * 2.71 * local)
                sample += envelope * (fundamental + overtone)
        sample = max(-1.0, min(1.0, sample * 0.36))
        frames.append(struct.pack("<h", int(sample * 32_767)))

    for output in OUTPUTS:
        output.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output / name), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(b"".join(frames))


def main() -> None:
    synthesize("coin_1.wav", [(0.00, 0.28, 1_260)])
    synthesize("coin_2.wav", [(0.00, 0.30, 1_010)])
    synthesize("coin_3.wav", [(0.00, 0.34, 820)])
    synthesize("line_lock.wav", [(0.00, 0.20, 420), (0.10, 0.22, 520)])
    synthesize("moving_line.wav", [(0.00, 0.16, 510), (0.20, 0.32, 760)])
    synthesize(
        "cast_complete.wav",
        [(0.00, 0.30, 392), (0.16, 0.35, 494), (0.34, 0.48, 659)],
    )


if __name__ == "__main__":
    main()
