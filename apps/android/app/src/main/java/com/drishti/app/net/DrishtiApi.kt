package com.drishti.app.net

import okhttp3.MultipartBody
import okhttp3.RequestBody
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query

/** DRISHTI local backend, contract version 1.0.0. All paths under /api/v1. */
interface DrishtiApi {

    @GET("api/v1/health")
    suspend fun health(): Response<HealthResponse>

    @POST("api/v1/walk/sessions")
    suspend fun startSession(@Body request: StartWalkSessionRequest): Response<StartWalkSessionResponse>

    @PATCH("api/v1/walk/sessions/{id}/end")
    suspend fun endSession(@Path("id") sessionId: String): Response<EndWalkSessionResponse>

    @Multipart
    @POST("api/v1/walk/analyze")
    suspend fun analyze(
        @Part frame: MultipartBody.Part,
        @Part("session_id") sessionId: RequestBody,
        @Part("frame_id") frameId: RequestBody,
        @Part("captured_at") capturedAt: RequestBody,
        @Part("rotation_degrees") rotationDegrees: RequestBody,
    ): Response<FrameAnalysisResponse>

    @Multipart
    @POST("api/v1/explore")
    suspend fun explore(
        @Part frame: MultipartBody.Part,
        @Part("mode") mode: RequestBody,
        @Part("preferred_language") preferredLanguage: RequestBody,
    ): Response<ReadTextResponse>

    /**
     * On-demand local VLM. User-triggered only — never on the Walk loop. The
     * backend loads Moondream2 per request, so this call is slow (seconds); the
     * VLM read timeout is widened for `/vlm/query` in [ApiModule].
     */
    @Multipart
    @POST("api/v1/vlm/query")
    suspend fun vlmQuery(
        @Part frame: MultipartBody.Part,
        @Part("prompt") prompt: RequestBody,
    ): Response<VlmQueryResponse>

    /**
     * Ask -> Lock. `target_name` + `session_id` are query params; no image is
     * sent — the backend locates against its own in-memory latest frame for
     * that active Walk session (D-068). Read timeout is widened in [ApiModule].
     */
    @POST("api/v1/vlm/locate")
    suspend fun vlmLocate(
        @Query("target_name") targetName: String,
        @Query("session_id") sessionId: String,
    ): Response<VlmLocateResponse>

    /**
     * Same as [vlmLocate] but with a freshly captured still, so the target is
     * located against *now* rather than the (up to ~17 s old) frame the backend
     * cached when the Ask gesture paused the Walk loop.
     */
    @Multipart
    @POST("api/v1/vlm/locate")
    suspend fun vlmLocate(
        @Query("target_name") targetName: String,
        @Query("session_id") sessionId: String,
        @Part frame: MultipartBody.Part,
    ): Response<VlmLocateResponse>

    @POST("api/v1/hazards")
    suspend fun createHazard(@Body request: CreateHazardRequest): Response<HazardResponse>

    @Multipart
    @POST("api/v1/hazards")
    suspend fun createHazardWithEvidence(
        @Part("payload") payload: RequestBody,
        @Part evidence: MultipartBody.Part,
    ): Response<HazardResponse>

    @GET("api/v1/hazards/nearby")
    suspend fun nearbyHazards(
        @Query("map_id") mapId: String,
        @Query("map_version") mapVersion: String,
        @Query("map_x") mapX: Double,
        @Query("map_y") mapY: Double,
        @Query("radius") radius: Double,
    ): Response<HazardListResponse>
}
