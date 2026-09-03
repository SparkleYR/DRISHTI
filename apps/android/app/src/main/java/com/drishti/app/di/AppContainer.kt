package com.drishti.app.di

import android.content.Context
import com.drishti.app.BuildConfig
import com.drishti.app.feedback.GuidanceStrings
import com.drishti.app.feedback.HapticEngine
import com.drishti.app.feedback.SpeechEngine
import com.drishti.app.feedback.SpokenLanguage
import com.drishti.app.net.ApiModule
import com.drishti.app.net.BackendOrigin
import com.drishti.app.net.DrishtiApi
import com.drishti.app.settings.SettingsStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Manual dependency container held by [com.drishti.app.DrishtiApp] for the whole
 * process. MainActivity and WalkForegroundService read from it. No Hilt in v1.
 */
class AppContainer(context: Context) {

    private val appContext = context.applicationContext

    val appScope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    val settingsStore: SettingsStore = SettingsStore(appContext)

    val api: DrishtiApi = ApiModule.create(debug = BuildConfig.DEBUG)

    /** Shared feedback engines — one TTS/vibrator for the whole app. */
    val speech: SpeechEngine = SpeechEngine(appContext)
    val haptic: HapticEngine = HapticEngine(appContext)
    val guidanceStrings: GuidanceStrings = GuidanceStrings(appContext)

    private val _lastHealthOk = MutableStateFlow(false)
    val lastHealthOk = _lastHealthOk.asStateFlow()
    fun updateHealthOk(value: Boolean) { _lastHealthOk.value = value }

    fun applyBackendUrl(raw: String): Boolean = BackendOrigin.set(raw)

    fun applySpokenSettings(language: SpokenLanguage, speechRate: Float, hapticsEnabled: Boolean) {
        guidanceStrings.setLanguage(language)
        speech.setLanguage(language)
        speech.setRate(speechRate)
        haptic.enabled = hapticsEnabled
    }
}
