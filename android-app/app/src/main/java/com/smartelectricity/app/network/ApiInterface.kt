package com.smartelectricity.app.network

import retrofit2.Call
import retrofit2.http.*

interface ApiInterface {

    @POST("api/auth/login")
    fun login(@Body request: LoginRequest): Call<AuthResponse>

    @POST("api/auth/register")
    fun register(@Body request: RegisterRequest): Call<AuthResponse>

    @GET("api/users/profile")
    fun getProfile(@Header("Authorization") token: String): Call<UserProfile>

    @POST("api/users/profile")
    fun updateProfile(
        @Header("Authorization") token: String,
        @Body request: RegisterRequest
    ): Call<GeneralResponse>

    @GET("api/meters")
    fun getMeters(@Header("Authorization") token: String): Call<List<MeterResponse>>

    @POST("api/meters")
    fun addMeter(
        @Header("Authorization") token: String,
        @Body request: MeterRequest
    ): Call<GeneralResponse>

    @DELETE("api/meters/{id}")
    fun deleteMeter(
        @Header("Authorization") token: String,
        @Path("id") id: Int
    ): Call<GeneralResponse>

    @GET("api/bills")
    fun getBills(@Header("Authorization") token: String): Call<List<BillResponse>>

    @POST("api/payments")
    fun makePayment(
        @Header("Authorization") token: String,
        @Body request: PaymentRequest
    ): Call<GeneralResponse>

    @GET("api/reminders")
    fun getReminders(@Header("Authorization") token: String): Call<List<ReminderResponse>>

    @POST("api/reminders/toggle")
    fun toggleReminder(
        @Header("Authorization") token: String,
        @Body request: ReminderToggleRequest
    ): Call<GeneralResponse>

    @GET("api/notifications")
    fun getNotifications(@Header("Authorization") token: String): Call<List<NotificationResponse>>

    @POST("api/ai/chat")
    fun aiChat(
        @Header("Authorization") token: String,
        @Body request: ChatRequest
    ): Call<ChatResponse>
}
