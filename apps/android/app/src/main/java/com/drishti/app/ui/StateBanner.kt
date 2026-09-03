package com.drishti.app.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.BasicText
import androidx.compose.foundation.text.TextAutoSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** One enormous word. Colour is never the only signal — the word itself carries it. */
@Composable
fun StateBanner(text: String, color: Color, modifier: Modifier = Modifier) {
    Box(modifier = modifier.fillMaxWidth().padding(horizontal = 12.dp), contentAlignment = Alignment.Center) {
        BasicText(
            text = text,
            autoSize = TextAutoSize.StepBased(minFontSize = 40.sp, maxFontSize = 150.sp, stepSize = 2.sp),
            maxLines = 1,
            style = TextStyle(
                color = color,
                fontWeight = FontWeight.Black,
                textAlign = TextAlign.Center,
            ),
        )
    }
}
