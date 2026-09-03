package com.drishti.app.feedback

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager

/**
 * Requests transient "may duck" focus so DRISHTI cues lower background media and
 * TalkBack without stopping them. Held while Walk Mode is active.
 */
class AudioFocusManager(context: Context) {

    private val audioManager = context.getSystemService(AudioManager::class.java)

    private val request = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK)
        .setAudioAttributes(
            AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ASSISTANCE_ACCESSIBILITY)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .build(),
        )
        .setWillPauseWhenDucked(false)
        .setOnAudioFocusChangeListener { /* advisory only; we never hard-stop safety cues */ }
        .build()

    private var held = false

    fun acquire() {
        if (held) return
        held = audioManager.requestAudioFocus(request) == AudioManager.AUDIOFOCUS_REQUEST_GRANTED
    }

    fun release() {
        if (!held) return
        audioManager.abandonAudioFocusRequest(request)
        held = false
    }
}
