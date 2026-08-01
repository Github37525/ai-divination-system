"""Static contract checks that can run without Xcode or Android Studio."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(path: str, *needles: str) -> None:
    file_path = ROOT / path
    if not file_path.is_file():
        raise AssertionError(f"missing {path}")
    text = file_path.read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            raise AssertionError(f"{path} missing {needle!r}")


def validate() -> None:
    contract = json.loads(
        (ROOT / "native/shared/cast-contract.json").read_text(encoding="utf-8")
    )
    assert contract["privacy"]["sound_enabled_by_default"] is False
    assert contract["privacy"]["sensor_data_uploaded"] is False
    assert list(contract["line_types"]) == ["6", "7", "8", "9"]

    require(
        "native/ios/DivinationApp/Services/MotionShakeDetector.swift",
        "CMMotionManager",
        "userAcceleration",
        "rotationRate",
    )
    require(
        "native/ios/DivinationApp/Services/HapticEngine.swift",
        "CHHapticEngine",
        "supportsHaptics",
    )
    require(
        "native/ios/DivinationApp/Models/CastViewModel.swift",
        "lockNextLine",
        "pendingLine",
        "restoreSession",
    )
    require(
        "native/android/app/src/main/AndroidManifest.xml",
        "android.permission.VIBRATE",
        "android.permission.INTERNET",
    )
    require(
        "native/android/app/src/main/java/com/yijing/instrument/MotionShakeDetector.kt",
        "TYPE_LINEAR_ACCELERATION",
        "TYPE_GYROSCOPE",
    )
    require(
        "native/android/app/src/main/java/com/yijing/instrument/Feedback.kt",
        "VibrationEffect",
        "SoundPool",
    )
    require(
        "native/android/app/src/main/java/com/yijing/instrument/CastViewModel.kt",
        "lockNextLine",
        "pendingLine",
        "restoreSession",
    )
    for platform_path in (
        ROOT / "native/ios/DivinationApp/Resources",
        ROOT / "native/android/app/src/main/res/raw",
    ):
        for name in (
            "coin_1.wav",
            "coin_2.wav",
            "coin_3.wav",
            "line_lock.wav",
            "moving_line.wav",
            "cast_complete.wav",
        ):
            assert (platform_path / name).stat().st_size > 1_000


if __name__ == "__main__":
    validate()
    print("native client contracts: ok")
