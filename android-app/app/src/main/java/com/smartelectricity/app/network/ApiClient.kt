package com.smartelectricity.app.network

import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

object ApiClient {
    // 10.0.2.2 is the localhost loopback for the Android Emulator.
    // If you run on a physical device, you can change this to your computer's local IP (e.g. 192.168.x.x)
    // or run 'adb reverse tcp:8000 tcp:8000' and change this to 'http://127.0.0.1:8000/'
    const val BASE_URL = "http://10.39.24.211:8000/"

    private val retrofit: Retrofit by lazy {
        Retrofit.Builder()
            .baseUrl(BASE_URL)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
    }

    val api: ApiInterface by lazy {
        retrofit.create(ApiInterface::class.java)
    }
}
