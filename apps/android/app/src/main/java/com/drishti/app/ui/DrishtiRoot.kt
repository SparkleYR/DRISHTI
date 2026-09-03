package com.drishti.app.ui

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.drishti.app.di.AppContainer
import com.drishti.app.settings.DrishtiSettings
import com.drishti.app.walk.WalkForegroundService

enum class Screen { READY, WALK, SETTINGS }

@Composable
fun DrishtiRoot(
    container: AppContainer,
    walkService: WalkForegroundService?,
    onStartWalkService: () -> Unit,
    onStopWalkService: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var screen by remember { mutableStateOf(Screen.READY) }
    val settings by container.settingsStore.settings.collectAsState(initial = DrishtiSettings())

    LaunchedEffect(settings.language, settings.speechRate, settings.hapticsEnabled) {
        container.applySpokenSettings(settings.language, settings.speechRate, settings.hapticsEnabled)
    }

    when (screen) {
        Screen.READY -> ReadyScreen(
            container = container,
            settings = settings,
            onStartWalk = { screen = Screen.WALK },
            onOpenSettings = { screen = Screen.SETTINGS },
            modifier = modifier,
        )
        Screen.WALK -> WalkScreen(
            container = container,
            settings = settings,
            service = walkService,
            onStartWalkService = onStartWalkService,
            onStopWalkService = onStopWalkService,
            onExit = { screen = Screen.READY },
            modifier = modifier,
        )
        Screen.SETTINGS -> SettingsScreen(
            container = container,
            settings = settings,
            onDone = { screen = Screen.READY },
            modifier = modifier,
        )
    }
}
