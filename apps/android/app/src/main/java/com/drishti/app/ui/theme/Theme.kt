package com.drishti.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/** Blind-first palette: pure black ground, safety-signal foregrounds. */
val DrishtiBlack = Color(0xFF000000)
val DrishtiYellow = Color(0xFFFFEB00)
val DrishtiRed = Color(0xFFFF3B30)
val DrishtiGreen = Color(0xFF00E676)
val DrishtiGrey = Color(0xFF9E9E9E)
val DrishtiWhite = Color(0xFFFFFFFF)

private val DrishtiColors = darkColorScheme(
    primary = DrishtiYellow,
    onPrimary = DrishtiBlack,
    secondary = DrishtiGreen,
    background = DrishtiBlack,
    onBackground = DrishtiWhite,
    surface = DrishtiBlack,
    onSurface = DrishtiWhite,
    error = DrishtiRed,
    onError = DrishtiBlack,
)

private val DrishtiTypography = Typography(
    displayLarge = TextStyle(fontWeight = FontWeight.Black, fontSize = 112.sp, lineHeight = 116.sp),
    headlineLarge = TextStyle(fontWeight = FontWeight.Black, fontSize = 44.sp, lineHeight = 48.sp),
    bodyLarge = TextStyle(fontWeight = FontWeight.SemiBold, fontSize = 24.sp, lineHeight = 32.sp),
)

@Composable
fun DrishtiTheme(content: @Composable () -> Unit) {
    @Suppress("UNUSED_EXPRESSION") isSystemInDarkTheme() // DRISHTI is always dark.
    MaterialTheme(
        colorScheme = DrishtiColors,
        typography = DrishtiTypography,
        content = content,
    )
}
