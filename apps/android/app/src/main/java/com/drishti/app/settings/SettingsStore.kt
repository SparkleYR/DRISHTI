package com.drishti.app.settings

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.floatPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.drishti.app.feedback.SpokenLanguage
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "drishti_settings")

/** Everything the user can tune. Persisted locally; never leaves the device. */
data class DrishtiSettings(
    val backendUrl: String = DEFAULT_BACKEND_URL,
    val language: SpokenLanguage = SpokenLanguage.ENGLISH,
    val hapticsEnabled: Boolean = true,
    val spatialAudioEnabled: Boolean = true,
    val visualLayerEnabled: Boolean = true,
    val speechRate: Float = 0.5f,
    val riskSensitivity: Float = 0.5f,
    val hazardMapId: String = "hackathon-demo-hall",
    val hazardMapVersion: String = "1",
    val hazardMapX: Float = 0.5f,
    val hazardMapY: Float = 0.5f,
) {
    companion object {
        const val DEFAULT_BACKEND_URL = "http://10.111.36.200:8000"
    }
}

class SettingsStore(private val context: Context) {

    private object Keys {
        val backendUrl = stringPreferencesKey("backend_url")
        val language = stringPreferencesKey("language")
        val haptics = booleanPreferencesKey("haptics")
        val spatialAudio = booleanPreferencesKey("spatial_audio")
        val visualLayer = booleanPreferencesKey("visual_layer")
        val speechRate = floatPreferencesKey("speech_rate")
        val riskSensitivity = floatPreferencesKey("risk_sensitivity")
        val mapId = stringPreferencesKey("hazard_map_id")
        val mapVersion = stringPreferencesKey("hazard_map_version")
        val mapX = floatPreferencesKey("hazard_map_x")
        val mapY = floatPreferencesKey("hazard_map_y")
    }

    val settings: Flow<DrishtiSettings> = context.dataStore.data.map { p ->
        DrishtiSettings(
            backendUrl = p[Keys.backendUrl] ?: DrishtiSettings.DEFAULT_BACKEND_URL,
            language = SpokenLanguage.fromTag(p[Keys.language]),
            hapticsEnabled = p[Keys.haptics] ?: true,
            spatialAudioEnabled = p[Keys.spatialAudio] ?: true,
            visualLayerEnabled = p[Keys.visualLayer] ?: true,
            speechRate = p[Keys.speechRate] ?: 0.5f,
            riskSensitivity = p[Keys.riskSensitivity] ?: 0.5f,
            hazardMapId = p[Keys.mapId] ?: "hackathon-demo-hall",
            hazardMapVersion = p[Keys.mapVersion] ?: "1",
            hazardMapX = p[Keys.mapX] ?: 0.5f,
            hazardMapY = p[Keys.mapY] ?: 0.5f,
        )
    }

    suspend fun setBackendUrl(value: String) = edit { it[Keys.backendUrl] = value.trim() }
    suspend fun setLanguage(value: SpokenLanguage) = edit { it[Keys.language] = value.tag }
    suspend fun setHaptics(value: Boolean) = edit { it[Keys.haptics] = value }
    suspend fun setSpatialAudio(value: Boolean) = edit { it[Keys.spatialAudio] = value }
    suspend fun setVisualLayer(value: Boolean) = edit { it[Keys.visualLayer] = value }
    suspend fun setSpeechRate(value: Float) = edit { it[Keys.speechRate] = value.coerceIn(0f, 1f) }
    suspend fun setRiskSensitivity(value: Float) = edit { it[Keys.riskSensitivity] = value.coerceIn(0f, 1f) }

    private suspend fun edit(block: (androidx.datastore.preferences.core.MutablePreferences) -> Unit) {
        context.dataStore.edit(block)
    }
}
