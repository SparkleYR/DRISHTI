package com.drishti.app

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import com.drishti.app.di.AppContainer
import com.drishti.app.settings.DrishtiSettings
import kotlinx.coroutines.launch

class DrishtiApp : Application() {

    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)

        // Start on the default origin (no blocking disk I/O on the main thread),
        // then track persisted edits as they load / change.
        container.applyBackendUrl(DrishtiSettings.DEFAULT_BACKEND_URL)
        container.appScope.launch {
            container.settingsStore.settings.collect { container.applyBackendUrl(it.backendUrl) }
        }

        createNotificationChannel()
    }

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            WALK_CHANNEL_ID,
            "Walk Mode",
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = "Keeps DRISHTI walk assistance running with the screen off."
            setShowBadge(false)
            enableVibration(false)
            enableLights(false)
        }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    companion object {
        const val WALK_CHANNEL_ID = "drishti_walk"
        const val WALK_NOTIFICATION_ID = 4201
    }
}
