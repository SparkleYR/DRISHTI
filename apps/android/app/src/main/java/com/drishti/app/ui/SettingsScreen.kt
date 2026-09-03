package com.drishti.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.drishti.app.R
import com.drishti.app.di.AppContainer
import com.drishti.app.net.ApiResult
import com.drishti.app.net.apiCall
import com.drishti.app.settings.DrishtiSettings
import com.drishti.app.ui.theme.DrishtiGreen
import com.drishti.app.ui.theme.DrishtiRed
import com.drishti.app.ui.theme.DrishtiWhite
import com.drishti.app.ui.theme.DrishtiYellow
import kotlinx.coroutines.launch

@Composable
fun SettingsScreen(
    container: AppContainer,
    settings: DrishtiSettings,
    onDone: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val scope = rememberCoroutineScope()
    var url by remember(settings.backendUrl) { mutableStateOf(settings.backendUrl) }
    var status by remember { mutableStateOf("") }
    var statusColor by remember { mutableStateOf(DrishtiWhite) }

    LaunchedEffect(url) { container.applyBackendUrl(url) }

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp),
    ) {
        Text(
            stringResource(R.string.settings_title),
            color = DrishtiYellow,
            style = MaterialTheme.typography.headlineLarge,
        )

        Text(stringResource(R.string.settings_backend), color = DrishtiWhite, style = MaterialTheme.typography.bodyLarge)
        OutlinedTextField(
            value = url,
            onValueChange = { url = it },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        Button(
            onClick = {
                container.applyBackendUrl(url)
                scope.launch {
                    container.settingsStore.setBackendUrl(url)
                    status = "…"
                    statusColor = DrishtiWhite
                    when (val r = apiCall { container.api.health() }) {
                        is ApiResult.Ok -> {
                            container.updateHealthOk(r.value.walkModeAvailable)
                            status = "OK — walk_mode_available=${r.value.walkModeAvailable}, " +
                                "detector=${r.value.models.detector.status}, ocr=${r.value.models.ocr.status}"
                            statusColor = DrishtiGreen
                        }
                        is ApiResult.Failure -> {
                            status = "Error ${r.code}: ${r.message}"
                            statusColor = DrishtiRed
                        }
                        is ApiResult.Transport -> {
                            status = "Unreachable: ${r.message}"
                            statusColor = DrishtiRed
                        }
                    }
                }
            },
            modifier = Modifier.fillMaxWidth(),
        ) { Text(stringResource(R.string.settings_test)) }

        if (status.isNotEmpty()) {
            Text(status, color = statusColor, style = MaterialTheme.typography.bodyLarge)
        }

        Button(onClick = onDone, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.settings_done))
        }
    }
}
