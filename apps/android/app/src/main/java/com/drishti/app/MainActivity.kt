package com.drishti.app

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.os.Bundle
import android.os.IBinder
import android.view.KeyEvent
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.core.content.ContextCompat
import com.drishti.app.ui.DrishtiRoot
import com.drishti.app.ui.theme.DrishtiBlack
import com.drishti.app.ui.theme.DrishtiTheme
import com.drishti.app.walk.WalkForegroundService
import com.drishti.app.walk.WalkMode

class MainActivity : ComponentActivity() {

    private val container get() = (application as DrishtiApp).container

    private var walkService by mutableStateOf<WalkForegroundService?>(null)

    private val connection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName?, binder: IBinder?) {
            walkService = (binder as? WalkForegroundService.LocalBinder)?.service
        }
        override fun onServiceDisconnected(name: ComponentName?) { walkService = null }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        setContent {
            DrishtiTheme {
                DrishtiRoot(
                    container = container,
                    walkService = walkService,
                    onStartWalkService = ::startWalkService,
                    onStopWalkService = ::stopWalkService,
                    modifier = Modifier.fillMaxSize().background(DrishtiBlack),
                )
            }
        }
    }

    override fun onStart() {
        super.onStart()
        bindService(
            Intent(this, WalkForegroundService::class.java),
            connection,
            Context.BIND_AUTO_CREATE,
        )
    }

    override fun onStop() {
        super.onStop()
        runCatching { unbindService(connection) }
        walkService = null
    }

    private fun startWalkService() {
        ContextCompat.startForegroundService(
            this,
            Intent(this, WalkForegroundService::class.java).setAction(WalkForegroundService.ACTION_START),
        )
    }

    private fun stopWalkService() {
        startService(
            Intent(this, WalkForegroundService::class.java).setAction(WalkForegroundService.ACTION_STOP),
        )
    }

    // Hardware button intercepts (ANDROID_APP_SPEC §6). Consume both directions so
    // the OS volume slider never appears while walking.
    private fun walkActive(): Boolean {
        val mode = walkService?.controller?.state?.value?.mode
        return mode != null && mode != WalkMode.STOPPED
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        if (walkActive()) {
            when (keyCode) {
                KeyEvent.KEYCODE_VOLUME_UP -> {
                    if (event?.repeatCount == 0) walkService?.controller?.triggerAsk()
                    return true
                }
                KeyEvent.KEYCODE_VOLUME_DOWN -> {
                    if (event?.repeatCount == 0) walkService?.controller?.triggerSos()
                    return true
                }
            }
        }
        return super.onKeyDown(keyCode, event)
    }

    override fun onKeyUp(keyCode: Int, event: KeyEvent?): Boolean {
        if (walkActive() && (keyCode == KeyEvent.KEYCODE_VOLUME_UP || keyCode == KeyEvent.KEYCODE_VOLUME_DOWN)) {
            return true
        }
        return super.onKeyUp(keyCode, event)
    }
}
