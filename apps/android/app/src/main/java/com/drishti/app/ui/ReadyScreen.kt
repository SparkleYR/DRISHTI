package com.drishti.app.ui

import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.onClick
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.drishti.app.R
import com.drishti.app.di.AppContainer
import com.drishti.app.settings.DrishtiSettings
import com.drishti.app.ui.theme.DrishtiGreen
import com.drishti.app.ui.theme.DrishtiWhite
import com.drishti.app.ui.theme.DrishtiYellow

@Composable
fun ReadyScreen(
    container: AppContainer,
    settings: DrishtiSettings,
    onStartWalk: () -> Unit,
    onOpenSettings: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val prompt = stringResource(R.string.ready_prompt)
    val hint = stringResource(R.string.ready_hint)

    LaunchedEffect(settings.language) {
        container.applySpokenSettings(settings.language, settings.speechRate, settings.hapticsEnabled)
        container.speech.ensureAudible()
        container.speech.say(
            container.guidanceStrings.string(R.string.ready_prompt),
            flush = true,
            dedupe = false,
        )
    }

    Box(
        modifier = modifier
            .fillMaxSize()
            .semantics {
                contentDescription = prompt
                onClick("start walking") { onStartWalk(); true }
            }
            .pointerInput(Unit) {
                detectTapGestures(
                    onDoubleTap = { onStartWalk() },
                    onLongPress = { onOpenSettings() },
                )
            },
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(24.dp),
            modifier = Modifier.padding(32.dp),
        ) {
            StateBanner(text = stringResource(R.string.state_ready), color = DrishtiGreen)
            Text(
                text = prompt,
                color = DrishtiYellow,
                textAlign = TextAlign.Center,
                style = MaterialTheme.typography.bodyLarge,
            )
            Text(
                text = hint,
                color = DrishtiWhite,
                textAlign = TextAlign.Center,
                style = MaterialTheme.typography.bodyLarge,
            )
        }
    }
}
