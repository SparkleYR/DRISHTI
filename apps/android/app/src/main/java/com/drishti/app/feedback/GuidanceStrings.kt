package com.drishti.app.feedback

import android.content.Context
import android.content.res.Configuration
import com.drishti.app.R
import com.drishti.app.net.GuidanceAction
import com.drishti.app.net.GuidanceContract

/**
 * Turns a backend [GuidanceContract] into a phrase in the user's chosen spoken
 * language. The backend only sends English `speech`; for Hindi/Tamil we resolve
 * our own localized resources keyed by `action`, refined by `reason_code` for a
 * few high-value cases. English output matches the contract wording.
 */
class GuidanceStrings(appContext: Context) {

    private val base = appContext.applicationContext
    @Volatile private var localized: Context = base

    fun setLanguage(language: SpokenLanguage) {
        val config = Configuration(base.resources.configuration)
        config.setLocale(language.locale)
        localized = base.createConfigurationContext(config)
    }

    /** Phrase to speak, or null when nothing should be spoken (CLEAR / empty). */
    fun speechFor(guidance: GuidanceContract): String? {
        val ctx = localized
        return when (guidance.reasonCode) {
            "WALL_OR_DEAD_END_AHEAD" -> ctx.getString(R.string.guide_wall)
            "APPROACHING_VEHICLE_CENTRE" -> ctx.getString(R.string.guide_vehicle)
            "ALL_CORRIDORS_BLOCKED" -> ctx.getString(R.string.guide_all_blocked)
            "CENTRE_SURFACE_UNCERTAIN" -> ctx.getString(R.string.guide_surface_uncertain)
            "STAIRS_OR_LEVEL_CHANGE_AHEAD" -> ctx.getString(R.string.guide_stairs)
            else -> when (guidance.action) {
                GuidanceAction.CLEAR -> null
                GuidanceAction.CAUTION -> ctx.getString(R.string.guide_caution)
                GuidanceAction.MOVE_LEFT -> ctx.getString(R.string.guide_move_left)
                GuidanceAction.MOVE_RIGHT -> ctx.getString(R.string.guide_move_right)
                GuidanceAction.STOP -> ctx.getString(R.string.guide_stop)
                GuidanceAction.PAUSE_UNCLEAR -> ctx.getString(R.string.guide_pause_unclear)
            }
        }
    }

    /**
     * Short human-readable "why" for the current guidance — shown under the
     * banner so a low-vision user can see *why* it says STOP / move / pause.
     * Null when the path is clear.
     */
    fun reasonText(guidance: GuidanceContract): String? {
        val ctx = localized
        return when (guidance.reasonCode) {
            "WALL_OR_DEAD_END_AHEAD" -> ctx.getString(R.string.reason_wall)
            "APPROACHING_VEHICLE_CENTRE" -> ctx.getString(R.string.reason_vehicle)
            "ALL_CORRIDORS_BLOCKED" -> ctx.getString(R.string.reason_all_blocked)
            "CENTRE_BLOCKED_CLEARER_SIDE" -> ctx.getString(R.string.reason_centre_blocked_side)
            "CENTRE_BLOCKED_DIRECTION_UNCLEAR" -> ctx.getString(R.string.reason_centre_blocked_unclear)
            "CENTRE_SURFACE_UNCERTAIN" -> ctx.getString(R.string.reason_surface_uncertain)
            "STAIRS_OR_LEVEL_CHANGE_AHEAD" -> ctx.getString(R.string.reason_stairs)
            "OBSTACLE_NEARBY" -> ctx.getString(R.string.reason_obstacle_nearby)
            "LOW_RISK_MONITORED" -> ctx.getString(R.string.reason_low_risk)
            "PATH_CLEAR" -> null
            else -> when (guidance.action) {
                GuidanceAction.CLEAR -> null
                GuidanceAction.STOP -> ctx.getString(R.string.reason_obstacle_ahead)
                GuidanceAction.MOVE_LEFT, GuidanceAction.MOVE_RIGHT ->
                    ctx.getString(R.string.reason_centre_blocked_side)
                GuidanceAction.PAUSE_UNCLEAR -> ctx.getString(R.string.reason_surface_uncertain)
                GuidanceAction.CAUTION -> ctx.getString(R.string.reason_obstacle_nearby)
            }
        }
    }

    fun string(resId: Int, vararg args: Any): String = localized.getString(resId, *args)
}
