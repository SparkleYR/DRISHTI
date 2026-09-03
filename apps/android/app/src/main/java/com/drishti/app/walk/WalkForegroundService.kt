package com.drishti.app.walk

import android.app.Notification
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Binder
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.lifecycle.LifecycleService
import com.drishti.app.DrishtiApp
import com.drishti.app.MainActivity
import com.drishti.app.R

/**
 * Keeps the CameraX pipeline + capture loop alive with the screen off or locked.
 * The Activity binds to read [WalkController.state] and attach the preview surface.
 */
class WalkForegroundService : LifecycleService() {

    private val app get() = application as DrishtiApp
    lateinit var controller: WalkController
        private set

    private var wakeLock: PowerManager.WakeLock? = null
    private val binder = LocalBinder()

    inner class LocalBinder : Binder() {
        val service: WalkForegroundService get() = this@WalkForegroundService
    }

    override fun onCreate() {
        super.onCreate()
        val c = app.container
        controller = WalkController(
            context = this,
            api = c.api,
            settingsStore = c.settingsStore,
            speech = c.speech,
            haptic = c.haptic,
            strings = c.guidanceStrings,
        )
    }

    override fun onBind(intent: Intent): IBinder {
        super.onBind(intent)
        return binder
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)
        when (intent?.action) {
            ACTION_STOP -> {
                controller.stop()
                releaseWakeLock()
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
                return START_NOT_STICKY
            }
            else -> {
                startForeground(
                    DrishtiApp.WALK_NOTIFICATION_ID,
                    buildNotification(),
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA,
                )
                acquireWakeLock()
                controller.start(this)
            }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        releaseWakeLock()
        controller.shutdown()
        super.onDestroy()
    }

    private fun acquireWakeLock() {
        if (wakeLock?.isHeld == true) return
        wakeLock = (getSystemService(POWER_SERVICE) as PowerManager)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "drishti:walk")
            .apply { setReferenceCounted(false); acquire(3 * 60 * 60 * 1000L) }
    }

    private fun releaseWakeLock() {
        wakeLock?.let { if (it.isHeld) it.release() }
        wakeLock = null
    }

    private fun buildNotification(): Notification {
        val open = android.app.PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java),
            android.app.PendingIntent.FLAG_IMMUTABLE or android.app.PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val stop = android.app.PendingIntent.getService(
            this, 1,
            Intent(this, WalkForegroundService::class.java).setAction(ACTION_STOP),
            android.app.PendingIntent.FLAG_IMMUTABLE or android.app.PendingIntent.FLAG_UPDATE_CURRENT,
        )
        return NotificationCompat.Builder(this, DrishtiApp.WALK_CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(getString(R.string.state_walking))
            .setOngoing(true)
            .setSilent(true)
            .setContentIntent(open)
            .addAction(0, getString(R.string.walk_stopped), stop)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    companion object {
        const val ACTION_START = "com.drishti.app.walk.START"
        const val ACTION_STOP = "com.drishti.app.walk.STOP"
    }
}
