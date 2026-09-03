package com.drishti.app.feedback

import java.util.Locale

/** Languages DRISHTI can speak guidance in. OCR stays English-only (backend limit). */
enum class SpokenLanguage(val tag: String, val locale: Locale, val displayName: String) {
    ENGLISH("en", Locale.ENGLISH, "English"),
    HINDI("hi", Locale("hi", "IN"), "हिन्दी"),
    TAMIL("ta", Locale("ta", "IN"), "தமிழ்");

    companion object {
        fun fromTag(tag: String?): SpokenLanguage =
            entries.firstOrNull { it.tag.equals(tag, ignoreCase = true) } ?: ENGLISH
    }
}
