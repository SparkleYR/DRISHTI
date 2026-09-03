package com.drishti.app.feedback

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import kotlin.math.PI

/**
 * Keeps a spatial cue pointing at the last-known hazard bearing while the user
 * turns between backend responses (~500 ms apart). Reads the device yaw from the
 * game rotation vector; exposes the signed yaw change since [markReference].
 *
 * Not a standalone "radar" — it only interpolates cues the backend already gave.
 */
class GyroSteering(context: Context) : SensorEventListener {

    private val sensorManager = context.getSystemService(SensorManager::class.java)
    private val sensor: Sensor? =
        sensorManager.getDefaultSensor(Sensor.TYPE_GAME_ROTATION_VECTOR)
            ?: sensorManager.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)

    private val rotationMatrix = FloatArray(9)
    private val orientation = FloatArray(3)

    @Volatile private var currentYaw: Float = 0f
    @Volatile private var referenceYaw: Float = 0f
    @Volatile private var referenceAt: Long = 0L

    val isAvailable: Boolean get() = sensor != null

    fun start() {
        sensor?.let { sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_GAME) }
    }

    fun stop() = sensorManager.unregisterListener(this)

    /** Call when a fresh analysis frame is applied: the cue bearing is now "here". */
    fun markReference() {
        referenceYaw = currentYaw
        referenceAt = System.currentTimeMillis()
    }

    /**
     * Signed yaw change since the last [markReference], in radians (−π..π).
     * Positive = user rotated left (so a cue should shift right to stay put).
     * Fades to 0 once the reference is older than [validityMs].
     */
    fun yawDeltaSinceReference(validityMs: Long): Float {
        if (referenceAt == 0L) return 0f
        val age = System.currentTimeMillis() - referenceAt
        if (age > validityMs) return 0f
        var delta = currentYaw - referenceYaw
        while (delta > PI) delta -= (2 * PI).toFloat()
        while (delta < -PI) delta += (2 * PI).toFloat()
        val fade = 1f - (age.toFloat() / validityMs)
        return delta * fade
    }

    override fun onSensorChanged(event: SensorEvent) {
        if (event.sensor.type != Sensor.TYPE_GAME_ROTATION_VECTOR &&
            event.sensor.type != Sensor.TYPE_ROTATION_VECTOR
        ) return
        SensorManager.getRotationMatrixFromVector(rotationMatrix, event.values)
        SensorManager.getOrientation(rotationMatrix, orientation)
        currentYaw = orientation[0] // azimuth, radians
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}
}
