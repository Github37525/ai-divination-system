package com.yijing.instrument

import android.content.Context
import android.media.AudioAttributes
import android.media.SoundPool
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager

class Feedback(context: Context) {
    private val appContext = context.applicationContext
    private val vibrator: Vibrator = if (Build.VERSION.SDK_INT >= 31) {
        appContext.getSystemService(VibratorManager::class.java).defaultVibrator
    } else {
        @Suppress("DEPRECATION")
        appContext.getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
    }
    private val soundPool = SoundPool.Builder()
        .setMaxStreams(3)
        .setAudioAttributes(
            AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ASSISTANCE_SONIFICATION)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .build(),
        )
        .build()
    private val sounds = mapOf(
        "coin_1" to soundPool.load(appContext, R.raw.coin_1, 1),
        "coin_2" to soundPool.load(appContext, R.raw.coin_2, 1),
        "coin_3" to soundPool.load(appContext, R.raw.coin_3, 1),
        "line_lock" to soundPool.load(appContext, R.raw.line_lock, 1),
        "moving_line" to soundPool.load(appContext, R.raw.moving_line, 1),
        "cast_complete" to soundPool.load(appContext, R.raw.cast_complete, 1),
    )

    fun validMotion(enabled: Boolean) {
        if (enabled) vibrateTick(0.25f)
    }

    fun coinImpact(index: Int, hapticsEnabled: Boolean, soundEnabled: Boolean) {
        if (hapticsEnabled) vibrateTick(0.28f + index * 0.09f)
        play("coin_${index + 1}", soundEnabled, 0.72f)
    }

    fun lineLocked(moving: Boolean, hapticsEnabled: Boolean, soundEnabled: Boolean) {
        if (hapticsEnabled) {
            if (Build.VERSION.SDK_INT >= 30 && vibrator.areAllPrimitivesSupported(
                    VibrationEffect.Composition.PRIMITIVE_CLICK,
                    VibrationEffect.Composition.PRIMITIVE_LOW_TICK,
                    VibrationEffect.Composition.PRIMITIVE_THUD,
                )
            ) {
                val composition = VibrationEffect.startComposition()
                    .addPrimitive(VibrationEffect.Composition.PRIMITIVE_CLICK, 0.36f)
                    .addPrimitive(VibrationEffect.Composition.PRIMITIVE_LOW_TICK, 0.42f, 70)
                if (moving) {
                    composition.addPrimitive(VibrationEffect.Composition.PRIMITIVE_THUD, 0.82f, 120)
                }
                vibrator.vibrate(composition.compose())
            } else {
                vibrateWaveform(if (moving) longArrayOf(0, 18, 75, 20, 100, 36) else longArrayOf(0, 18, 70, 20))
            }
        }
        play(if (moving) "moving_line" else "line_lock", soundEnabled, 0.78f)
    }

    fun castComplete(hapticsEnabled: Boolean, soundEnabled: Boolean) {
        if (hapticsEnabled) {
            if (Build.VERSION.SDK_INT >= 29) {
                vibrator.vibrate(VibrationEffect.createPredefined(VibrationEffect.EFFECT_DOUBLE_CLICK))
            } else {
                vibrateWaveform(longArrayOf(0, 18, 70, 24, 90, 34))
            }
        }
        play("cast_complete", soundEnabled, 0.82f)
    }

    fun release() {
        soundPool.release()
    }

    private fun vibrateTick(scale: Float) {
        if (!vibrator.hasVibrator()) return
        if (Build.VERSION.SDK_INT >= 30 && vibrator.areAllPrimitivesSupported(
                VibrationEffect.Composition.PRIMITIVE_LOW_TICK,
            )
        ) {
            vibrator.vibrate(
                VibrationEffect.startComposition()
                    .addPrimitive(VibrationEffect.Composition.PRIMITIVE_LOW_TICK, scale)
                    .compose(),
            )
        } else if (Build.VERSION.SDK_INT >= 29) {
            vibrator.vibrate(VibrationEffect.createPredefined(VibrationEffect.EFFECT_TICK))
        } else {
            vibrator.vibrate(VibrationEffect.createOneShot(12, (scale * 150).toInt().coerceAtLeast(28)))
        }
    }

    private fun vibrateWaveform(timings: LongArray) {
        if (vibrator.hasVibrator()) {
            vibrator.vibrate(VibrationEffect.createWaveform(timings, -1))
        }
    }

    private fun play(name: String, enabled: Boolean, volume: Float) {
        if (!enabled) return
        sounds[name]?.let { soundPool.play(it, volume, volume, 1, 0, 1f) }
    }
}
