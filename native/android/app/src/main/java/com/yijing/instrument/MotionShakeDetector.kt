package com.yijing.instrument

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlin.math.max
import kotlin.math.sqrt

class MotionShakeDetector(context: Context) : SensorEventListener {
    private val sensorManager = context.getSystemService(SensorManager::class.java)
    private val linearSensor = sensorManager.getDefaultSensor(Sensor.TYPE_LINEAR_ACCELERATION)
    private val accelerometer = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
    private val gyroscope = sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE)
    private val mainHandler = Handler(Looper.getMainLooper())
    private val gravity = FloatArray(3)
    private var rotationMagnitude = 0.0
    private var calibrationSamples = 0
    private var lastImpulseAt = 0L
    private var cooldownUntil = 0L
    private val impulses = ArrayDeque<Long>()
    private var active = false

    private val _energy = MutableStateFlow(0.0)
    val energy: StateFlow<Double> = _energy
    private val _calibrationProgress = MutableStateFlow(0.0)
    val calibrationProgress: StateFlow<Double> = _calibrationProgress
    private val _ready = MutableStateFlow(false)
    val ready: StateFlow<Boolean> = _ready
    val isAvailable: Boolean get() = (linearSensor != null || accelerometer != null)

    var onShake: ((Double) -> Unit)? = null
    var onReady: (() -> Unit)? = null

    fun start() {
        if (active) return
        if (!isAvailable) {
            _ready.value = true
            onReady?.invoke()
            return
        }
        calibrationSamples = 0
        _calibrationProgress.value = 0.0
        _ready.value = false
        impulses.clear()
        val accelerationSource = linearSensor ?: accelerometer
        sensorManager.registerListener(this, accelerationSource, SensorManager.SENSOR_DELAY_GAME)
        gyroscope?.let { sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_GAME) }
        active = true
    }

    fun stop() {
        if (active) sensorManager.unregisterListener(this)
        active = false
        _ready.value = false
        _energy.value = 0.0
    }

    override fun onSensorChanged(event: SensorEvent) {
        when (event.sensor.type) {
            Sensor.TYPE_GYROSCOPE -> {
                rotationMagnitude = magnitude(event.values).toDouble()
            }
            Sensor.TYPE_LINEAR_ACCELERATION -> consumeAcceleration(magnitude(event.values) / GRAVITY)
            Sensor.TYPE_ACCELEROMETER -> {
                for (index in 0..2) {
                    gravity[index] = 0.82f * gravity[index] + 0.18f * event.values[index]
                }
                val linear = FloatArray(3) { event.values[it] - gravity[it] }
                consumeAcceleration(magnitude(linear) / GRAVITY)
            }
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit

    private fun consumeAcceleration(accelerationG: Float) {
        if (calibrationSamples < 30) {
            calibrationSamples += 1
            _calibrationProgress.value = calibrationSamples / 30.0
            if (calibrationSamples == 30) {
                _ready.value = true
                mainHandler.post { onReady?.invoke() }
            }
            return
        }

        val energy = (max(accelerationG / 1.15, rotationMagnitude / 2.2) * 58).coerceIn(0.0, 100.0)
        _energy.value = energy
        val now = SystemClock.elapsedRealtime()
        if (now < cooldownUntil || (accelerationG < 1.15 && rotationMagnitude < 2.2)) return
        if (now - lastImpulseAt < 110) return
        lastImpulseAt = now
        impulses.addLast(now)
        while (impulses.isNotEmpty() && now - impulses.first() > 900) impulses.removeFirst()
        if (impulses.size >= 3) {
            impulses.clear()
            cooldownUntil = now + 1_800
            mainHandler.post { onShake?.invoke(energy) }
        }
    }

    private fun magnitude(values: FloatArray): Float =
        sqrt(values[0] * values[0] + values[1] * values[1] + values[2] * values[2])

    private companion object {
        const val GRAVITY = 9.80665f
    }
}
