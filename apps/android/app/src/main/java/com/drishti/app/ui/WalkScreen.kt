package com.drishti.app.ui

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import com.drishti.app.R
import com.drishti.app.di.AppContainer
import com.drishti.app.net.GuidanceAction
import com.drishti.app.net.OcrConfidenceQualification
import com.drishti.app.settings.DrishtiSettings
import com.drishti.app.walk.ExploreCard
import com.drishti.app.ui.gestures.walkGestures
import com.drishti.app.ui.theme.DrishtiBlack
import com.drishti.app.ui.theme.DrishtiGreen
import com.drishti.app.ui.theme.DrishtiRed
import com.drishti.app.ui.theme.DrishtiWhite
import com.drishti.app.ui.theme.DrishtiYellow
import com.drishti.app.walk.WalkForegroundService
import com.drishti.app.walk.WalkMode
import com.drishti.app.walk.WalkUiState
import kotlinx.coroutines.flow.MutableStateFlow

@Composable
fun WalkScreen(
    container: AppContainer,
    settings: DrishtiSettings,
    service: WalkForegroundService?,
    onStartWalkService: () -> Unit,
    onStopWalkService: () -> Unit,
    onExit: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    var hasCamera by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) ==
                PackageManager.PERMISSION_GRANTED,
        )
    }
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted -> hasCamera = granted }

    // Microphone drives the spoken question for the VLM scene-description path.
    // Requested once, after camera; denial only degrades that one feature.
    val micLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { /* SceneDescriber re-checks at call time */ }

    LaunchedEffect(hasCamera) {
        if (hasCamera) {
            onStartWalkService()
            if (
                ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) !=
                PackageManager.PERMISSION_GRANTED
            ) {
                micLauncher.launch(Manifest.permission.RECORD_AUDIO)
            }
        } else {
            permissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    val controller = service?.controller
    val stateFlow = remember(controller) { controller?.state ?: MutableStateFlow(WalkUiState()) }
    val state by stateFlow.collectAsState()

    DisposableEffect(controller) { onDispose { controller?.detachPreview() } }

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(DrishtiBlack)
            .semantics { contentDescription = bannerLabel(context, state) }
            .walkGestures(
                onDoubleTap = { onStopWalkService(); onExit() },
                onSingleTap = { controller?.repeatLast() },
                onLongPress = { controller?.triggerAsk() },
                onTripleTap = {
                    controller?.cancelSos()
                    controller?.cancelHazard()
                },
                onTwoFingerTap = { controller?.toggleBlank() },
                onThreeFingerTap = { controller?.armHazard() },
                onTwoFingerSwipeUp = { controller?.armHazard() },
                onTwoFingerSwipeRight = { controller?.triggerExplore() },
            ),
    ) {
        if (settings.visualLayerEnabled && !state.screenBlank && hasCamera) {
            AndroidView(
                factory = { ctx ->
                    PreviewView(ctx).apply {
                        implementationMode = PreviewView.ImplementationMode.COMPATIBLE
                        scaleType = PreviewView.ScaleType.FILL_CENTER
                    }
                },
                modifier = Modifier.fillMaxSize(),
                update = { view -> controller?.attachPreview(view.surfaceProvider) },
            )
            OverlayCanvas(
                geometry = state.geometry,
                overlay = state.overlay,
                detections = state.detections,
                modifier = Modifier.fillMaxSize(),
            )
        }

        Column(
            modifier = Modifier.fillMaxSize().safeDrawingPadding().padding(16.dp),
            verticalArrangement = Arrangement.SpaceBetween,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    text = statusLine(context, state, container),
                    color = if (state.connectionLost) DrishtiRed else DrishtiWhite,
                    style = MaterialTheme.typography.bodyLarge,
                )
                state.explore?.let { ExploreResultCard(context, it) }
                state.scene?.let { SceneResultCard(context, it) }
            }

            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                StateBanner(text = bannerWord(context, state), color = bannerColor(state))
                val reasonText = state.reason
                if (state.mode == WalkMode.WALKING && reasonText != null) {
                    Text(
                        text = reasonText,
                        color = bannerColor(state),
                        textAlign = TextAlign.Center,
                        style = MaterialTheme.typography.headlineSmall,
                        modifier = Modifier.padding(top = 8.dp),
                    )
                }
            }

            Text(
                text = state.message
                    ?: if (state.mode == WalkMode.WALKING) "" else stringResource(R.string.ready_hint),
                color = DrishtiYellow,
                textAlign = TextAlign.Center,
                style = MaterialTheme.typography.bodyLarge,
            )
        }

        if (state.screenBlank) {
            Box(modifier = Modifier.fillMaxSize().background(DrishtiBlack))
        }
    }
}

private fun bannerWord(context: Context, s: WalkUiState): String {
    val res = when (s.mode) {
        WalkMode.SOS -> R.string.state_sos
        WalkMode.READING -> R.string.state_reading
        WalkMode.DESCRIBING -> R.string.state_describing
        WalkMode.PAUSED -> R.string.state_paused
        WalkMode.STARTING -> R.string.state_ready
        WalkMode.ERROR -> R.string.state_paused
        WalkMode.STOPPED -> R.string.state_ready
        WalkMode.WALKING -> when (s.guidance?.action) {
            GuidanceAction.STOP -> R.string.state_stop
            GuidanceAction.MOVE_LEFT -> R.string.state_left
            GuidanceAction.MOVE_RIGHT -> R.string.state_right
            GuidanceAction.CAUTION -> R.string.state_caution
            GuidanceAction.PAUSE_UNCLEAR -> R.string.state_paused
            else -> R.string.state_walking
        }
    }
    return context.getString(res)
}

private fun bannerColor(s: WalkUiState) = when (s.mode) {
    WalkMode.SOS, WalkMode.ERROR -> DrishtiRed
    WalkMode.READING, WalkMode.DESCRIBING -> DrishtiWhite
    WalkMode.STARTING -> DrishtiWhite
    else -> when (s.guidance?.action) {
        GuidanceAction.STOP -> DrishtiRed
        GuidanceAction.MOVE_LEFT, GuidanceAction.MOVE_RIGHT, GuidanceAction.CAUTION, GuidanceAction.PAUSE_UNCLEAR -> DrishtiYellow
        else -> DrishtiGreen
    }
}

private fun bannerLabel(context: Context, s: WalkUiState): String =
    bannerWord(context, s) + ". " + (s.message ?: "")

private fun statusLine(context: Context, s: WalkUiState, container: AppContainer): String {
    if (s.connectionLost) return context.getString(R.string.conn_lost)
    val ms = s.lastTotalMs?.let { " ${it.toInt()} ms" } ?: ""
    val deg = if (s.surfacesDegraded) " • " + context.getString(R.string.surface_degraded) else ""
    val ttsErr = container.speech.initError
    val tts = " • " + if (ttsErr == null) context.getString(R.string.diag_tts_ok)
        else context.getString(R.string.diag_tts_fail, ttsErr)
    return context.getString(R.string.state_walking) + ms + deg + tts
}

@Composable
private fun ExploreResultCard(context: Context, card: ExploreCard) {
    val qualityLabel = when (card.quality) {
        OcrConfidenceQualification.HIGH -> context.getString(R.string.explore_quality_high)
        OcrConfidenceQualification.LOW -> context.getString(R.string.explore_quality_low)
        OcrConfidenceQualification.NONE -> context.getString(R.string.explore_quality_none)
    }
    val accent = if (card.quality == OcrConfidenceQualification.HIGH) DrishtiGreen else DrishtiYellow
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 12.dp)
            .border(2.dp, accent, RoundedCornerShape(12.dp))
            .background(DrishtiBlack, RoundedCornerShape(12.dp))
            .padding(16.dp)
            .semantics {
                contentDescription = "$qualityLabel. ${card.text}. " +
                    if (card.routeNumbers.isEmpty()) "" else
                        context.getString(R.string.explore_routes_label) + " " +
                        card.routeNumbers.joinToString(", ")
            },
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            text = context.getString(R.string.explore_card_title) + " — " + qualityLabel,
            color = accent,
            style = MaterialTheme.typography.labelLarge,
        )
        if (card.text.isNotBlank()) {
            Text(
                text = card.text,
                color = DrishtiWhite,
                textAlign = TextAlign.Center,
                fontWeight = FontWeight.Bold,
                style = MaterialTheme.typography.headlineMedium,
                modifier = Modifier.padding(top = 8.dp),
            )
        }
        if (card.routeNumbers.isNotEmpty()) {
            Text(
                text = context.getString(R.string.explore_routes_label) + ": " +
                    card.routeNumbers.joinToString("  "),
                color = accent,
                textAlign = TextAlign.Center,
                fontWeight = FontWeight.Black,
                style = MaterialTheme.typography.headlineSmall,
                modifier = Modifier.padding(top = 8.dp),
            )
        }
    }
}

@Composable
private fun SceneResultCard(context: Context, card: com.drishti.app.walk.SceneCard) {
    val accent = DrishtiWhite
    val seconds = (card.totalMs / 1000.0)
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 12.dp)
            .border(2.dp, accent, RoundedCornerShape(12.dp))
            .background(DrishtiBlack, RoundedCornerShape(12.dp))
            .padding(16.dp)
            .semantics { contentDescription = "${card.question}. ${card.answer}" },
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            text = context.getString(R.string.vlm_card_title) +
                " — " + String.format("%.1f", seconds) + " s",
            color = accent,
            style = MaterialTheme.typography.labelLarge,
        )
        Text(
            text = card.question,
            color = DrishtiYellow,
            textAlign = TextAlign.Center,
            style = MaterialTheme.typography.bodyLarge,
            modifier = Modifier.padding(top = 8.dp),
        )
        Text(
            text = card.answer,
            color = DrishtiWhite,
            textAlign = TextAlign.Center,
            fontWeight = FontWeight.Bold,
            style = MaterialTheme.typography.headlineSmall,
            modifier = Modifier.padding(top = 8.dp),
        )
    }
}
