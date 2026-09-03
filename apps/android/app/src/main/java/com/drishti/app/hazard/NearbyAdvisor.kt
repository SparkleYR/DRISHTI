package com.drishti.app.hazard

import com.drishti.app.R
import com.drishti.app.feedback.GuidanceStrings
import com.drishti.app.feedback.SpeechEngine
import com.drishti.app.net.ApiResult
import com.drishti.app.net.DrishtiApi
import com.drishti.app.net.apiCall
import com.drishti.app.settings.DrishtiSettings

/**
 * Every ~20 s while walking, speaks any newly-reported hazard near the configured
 * map point as a low-priority advisory. Never repeats the same hazard id.
 */
class NearbyAdvisor(
    private val api: DrishtiApi,
    private val speech: SpeechEngine,
    private val strings: GuidanceStrings,
) {
    private val announced = HashSet<String>()

    suspend fun poll(settings: DrishtiSettings) {
        val r = apiCall {
            api.nearbyHazards(
                mapId = settings.hazardMapId,
                mapVersion = settings.hazardMapVersion,
                mapX = settings.hazardMapX.toDouble(),
                mapY = settings.hazardMapY.toDouble(),
                radius = 0.25,
            )
        }
        if (r !is ApiResult.Ok) return
        r.value.items
            .filter { announced.add(it.id) }
            .take(2)
            .forEach { hazard ->
                speech.say(strings.string(R.string.nearby_hazard, hazard.category), flush = false)
            }
    }

    fun reset() = announced.clear()
}
