package com.smartelectricity.app.network

import com.google.gson.annotations.SerializedName

// Schemas matching python endpoints
data class LoginRequest(
    @SerializedName("email") val email: String,
    @SerializedName("password") val password: String
)

data class RegisterRequest(
    @SerializedName("name") val name: String,
    @SerializedName("email") val email: String,
    @SerializedName("password") val password: String,
    @SerializedName("phone") val phone: String,
    @SerializedName("alternate_phone") val alternatePhone: String? = null
)

data class AuthResponse(
    @SerializedName("token") val token: String,
    @SerializedName("user") val user: UserProfile
)

data class UserProfile(
    @SerializedName("id") val id: Int,
    @SerializedName("name") val name: String,
    @SerializedName("email") val email: String,
    @SerializedName("phone") val phone: String?,
    @SerializedName("alternate_phone") val alternatePhone: String?
)

data class MeterRequest(
    @SerializedName("service_number") val serviceNumber: String,
    @SerializedName("board_name") val boardName: String,
    @SerializedName("consumer_name") val consumerName: String,
    @SerializedName("address") val address: String
)

data class MeterResponse(
    @SerializedName("id") val id: Int,
    @SerializedName("service_number") val serviceNumber: String,
    @SerializedName("board_name") val boardName: String,
    @SerializedName("consumer_name") val consumerName: String,
    @SerializedName("address") val address: String
)

data class BillResponse(
    @SerializedName("id") val id: Int,
    @SerializedName("meter_id") val meterId: Int,
    @SerializedName("billing_month") val billingMonth: String,
    @SerializedName("units_consumed") val unitsConsumed: Double,
    @SerializedName("amount") val amount: Double,
    @SerializedName("due_date") val dueDate: String,
    @SerializedName("payment_status") val paymentStatus: String,
    @SerializedName("service_number") val serviceNumber: String? = null,
    @SerializedName("consumer_name") val consumerName: String? = null
)

data class PaymentRequest(
    @SerializedName("bill_id") val billId: Int,
    @SerializedName("amount") val amount: Double,
    @SerializedName("payment_method") val paymentMethod: String
)

data class ReminderResponse(
    @SerializedName("id") val id: Int,
    @SerializedName("user_id") val userId: Int,
    @SerializedName("days_before") val daysBefore: Int,
    @SerializedName("enabled") val enabled: Int
)

data class ReminderToggleRequest(
    @SerializedName("days_before") val daysBefore: Int,
    @SerializedName("enabled") val enabled: Boolean
)

data class NotificationResponse(
    @SerializedName("id") val id: Int,
    @SerializedName("user_id") val userId: Int,
    @SerializedName("title") val title: String,
    @SerializedName("message") val message: String,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("is_read") val isRead: Int
)

data class ChatRequest(
    @SerializedName("message") val message: String
)

data class ChatResponse(
    @SerializedName("reply") val reply: String
)

data class GeneralResponse(
    @SerializedName("message") val message: String
)
