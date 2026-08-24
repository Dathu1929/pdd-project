package com.smartelectricity.app

import android.app.AlertDialog
import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.bottomnavigation.BottomNavigationView
import com.smartelectricity.app.network.ApiClient
import com.smartelectricity.app.network.ApiInterface
import com.smartelectricity.app.network.GeneralResponse
import com.smartelectricity.app.network.NotificationResponse
import com.smartelectricity.app.network.ReminderResponse
import com.smartelectricity.app.network.ReminderToggleRequest
import retrofit2.Call
import retrofit2.Callback
import retrofit2.Response

class NotificationsActivity : AppCompatActivity() {

    private lateinit var api: ApiInterface
    private var token: String? = null

    private lateinit var rvNotifications: RecyclerView
    private val notificationList = ArrayList<NotificationResponse>()
    private lateinit var adapter: NotificationsAdapter

    // Tab Contents
    private lateinit var layoutUpcomingContent: LinearLayout
    private lateinit var layoutSentContent: LinearLayout
    private lateinit var layoutSettingsContent: LinearLayout

    // Tab Views
    private lateinit var tabUpcoming: LinearLayout
    private lateinit var tabSent: LinearLayout
    private lateinit var tabSettings: LinearLayout

    // Tab Sub-views for state highlighting
    private lateinit var ivTabUpcoming: ImageView
    private lateinit var tvTabUpcoming: TextView
    private lateinit var indicatorUpcoming: View

    private lateinit var ivTabSent: ImageView
    private lateinit var tvTabSent: TextView
    private lateinit var indicatorSent: View

    private lateinit var ivTabSettings: ImageView
    private lateinit var tvTabSettings: TextView
    private lateinit var indicatorSettings: View

    // Reminder Status TextViews
    private var is7DaysEnabled = true
    private var is3DaysEnabled = true
    private var is1DayEnabled = true
    private var isDueDateEnabled = true

    // Reminder Channels Local States
    private var isSmsEnabled = true
    private var isWhatsappEnabled = true
    private var isEmailEnabled = true
    private var isCallEnabled = true

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_notifications)

        val sharedPref = getSharedPreferences("SmartElectricityPrefs", MODE_PRIVATE)
        token = sharedPref.getString("TOKEN", null)

        if (token == null) {
            finish()
            return
        }

        api = ApiClient.api

        // Bind layouts
        layoutUpcomingContent = findViewById(R.id.layout_upcoming_content)
        layoutSentContent = findViewById(R.id.layout_sent_content)
        layoutSettingsContent = findViewById(R.id.layout_settings_content)

        // Bind tabs
        tabUpcoming = findViewById(R.id.tab_upcoming)
        tabSent = findViewById(R.id.tab_sent)
        tabSettings = findViewById(R.id.tab_settings)

        // Bind tab subviews
        ivTabUpcoming = findViewById(R.id.iv_tab_upcoming)
        tvTabUpcoming = findViewById(R.id.tv_tab_upcoming)
        indicatorUpcoming = findViewById(R.id.indicator_upcoming)

        ivTabSent = findViewById(R.id.iv_tab_sent)
        tvTabSent = findViewById(R.id.tv_tab_sent)
        indicatorSent = findViewById(R.id.indicator_sent)

        ivTabSettings = findViewById(R.id.iv_tab_settings)
        tvTabSettings = findViewById(R.id.tv_tab_settings)
        indicatorSettings = findViewById(R.id.indicator_settings)

        // Setup Sent notifications list
        rvNotifications = findViewById(R.id.rv_notifications)
        rvNotifications.layoutManager = LinearLayoutManager(this)
        adapter = NotificationsAdapter(notificationList)
        rvNotifications.adapter = adapter

        // Set Tab click listeners
        tabUpcoming.setOnClickListener { switchTab("upcoming") }
        tabSent.setOnClickListener { switchTab("sent") }
        tabSettings.setOnClickListener { switchTab("settings") }

        // Back button navigation
        findViewById<ImageView>(R.id.btn_back).setOnClickListener {
            finish()
        }

        // Add Reminder dialog button
        findViewById<View>(R.id.btn_add_reminder).setOnClickListener {
            showAddReminderDialog()
        }

        // Configure Settings row triggers
        setupChannelsSettings()

        // Bind Reminder Cards Toggle Action
        setupRemindersToggleAction()

        // Bottom Navigation Bar
        val bottomNav = findViewById<BottomNavigationView>(R.id.bottom_navigation)
        bottomNav.selectedItemId = R.id.navigation_notifications
        bottomNav.setOnItemSelectedListener { item ->
            when (item.itemId) {
                R.id.navigation_home -> {
                    startActivity(Intent(this, MainActivity::class.java))
                    finish()
                    true
                }
                R.id.navigation_connections -> {
                    startActivity(Intent(this, ConnectionsActivity::class.java))
                    finish()
                    true
                }
                R.id.navigation_pay -> {
                    startActivity(Intent(this, BillDetailsActivity::class.java))
                    finish()
                    true
                }
                R.id.navigation_notifications -> true
                R.id.navigation_profile -> {
                    sharedPref.edit().clear().apply()
                    Toast.makeText(this, "Logged out successfully", Toast.LENGTH_SHORT).show()
                    startActivity(Intent(this, LoginActivity::class.java))
                    finish()
                    true
                }
                else -> false
            }
        }

        // Load data on start
        fetchReminders()
        fetchNotifications()
        loadLocalSettings()
    }

    private fun switchTab(tab: String) {
        // Hide all contents
        layoutUpcomingContent.visibility = View.GONE
        layoutSentContent.visibility = View.GONE
        layoutSettingsContent.visibility = View.GONE

        // Reset Tab Colors
        val grey = resources.getColor(R.color.text_muted, null)
        ivTabUpcoming.setColorFilter(grey)
        tvTabUpcoming.setTextColor(grey)
        tvTabUpcoming.setTypeface(null, android.graphics.Typeface.NORMAL)
        indicatorUpcoming.visibility = View.INVISIBLE

        ivTabSent.setColorFilter(grey)
        tvTabSent.setTextColor(grey)
        tvTabSent.setTypeface(null, android.graphics.Typeface.NORMAL)
        indicatorSent.visibility = View.INVISIBLE

        ivTabSettings.setColorFilter(grey)
        tvTabSettings.setTextColor(grey)
        tvTabSettings.setTypeface(null, android.graphics.Typeface.NORMAL)
        indicatorSettings.visibility = View.INVISIBLE

        // Highlight selected tab
        val blue = resources.getColor(R.color.primary, null)
        when (tab) {
            "upcoming" -> {
                layoutUpcomingContent.visibility = View.VISIBLE
                ivTabUpcoming.setColorFilter(blue)
                tvTabUpcoming.setTextColor(blue)
                tvTabUpcoming.setTypeface(null, android.graphics.Typeface.BOLD)
                indicatorUpcoming.visibility = View.VISIBLE
            }
            "sent" -> {
                layoutSentContent.visibility = View.VISIBLE
                ivTabSent.setColorFilter(blue)
                tvTabSent.setTextColor(blue)
                tvTabSent.setTypeface(null, android.graphics.Typeface.BOLD)
                indicatorSent.visibility = View.VISIBLE
                fetchNotifications() // refresh
            }
            "settings" -> {
                layoutSettingsContent.visibility = View.VISIBLE
                ivTabSettings.setColorFilter(blue)
                tvTabSettings.setTextColor(blue)
                tvTabSettings.setTypeface(null, android.graphics.Typeface.BOLD)
                indicatorSettings.visibility = View.VISIBLE
            }
        }
    }

    private fun fetchReminders() {
        val authHeader = "Bearer $token"
        api.getReminders(authHeader).enqueue(object : Callback<List<ReminderResponse>> {
            override fun onResponse(call: Call<List<ReminderResponse>>, response: Response<List<ReminderResponse>>) {
                if (response.isSuccessful && response.body() != null) {
                    val reminders = response.body()!!
                    for (r in reminders) {
                        when (r.daysBefore) {
                            7 -> is7DaysEnabled = r.enabled == 1
                            3 -> is3DaysEnabled = r.enabled == 1
                            1 -> is1DayEnabled = r.enabled == 1
                            0 -> isDueDateEnabled = r.enabled == 1
                        }
                    }
                    updateRemindersUI()
                }
            }

            override fun onFailure(call: Call<List<ReminderResponse>>, t: Throwable) {}
        })
    }

    private fun updateRemindersUI() {
        val card1Status = (findViewById<View>(R.id.ll_date_1) as? android.view.ViewGroup)?.getChildAt(1) as? TextView
        card1Status?.let {
            it.text = if (is7DaysEnabled) "✔ Scheduled" else "Disabled"
            it.setTextColor(resources.getColor(if (is7DaysEnabled) R.color.green_success else R.color.red_error, null))
        }

        val card2Status = (findViewById<View>(R.id.ll_date_2) as? android.view.ViewGroup)?.getChildAt(1) as? TextView
        card2Status?.let {
            it.text = if (is3DaysEnabled) "✔ Scheduled" else "Disabled"
            it.setTextColor(resources.getColor(if (is3DaysEnabled) R.color.green_success else R.color.red_error, null))
        }

        val card3Status = (findViewById<View>(R.id.ll_date_3) as? android.view.ViewGroup)?.getChildAt(1) as? TextView
        card3Status?.let {
            it.text = if (is1DayEnabled) "✔ Scheduled" else "Disabled"
            it.setTextColor(resources.getColor(if (is1DayEnabled) R.color.green_success else R.color.red_error, null))
        }

        val card4Status = (findViewById<View>(R.id.ll_date_4) as? android.view.ViewGroup)?.getChildAt(1) as? TextView
        card4Status?.let {
            it.text = if (isDueDateEnabled) "✔ Scheduled" else "Disabled"
            it.setTextColor(resources.getColor(if (isDueDateEnabled) R.color.green_success else R.color.red_error, null))
        }
    }

    private fun setupRemindersToggleAction() {
        // Enclosing Card Parent layouts
        val flDays1 = findViewById<View>(R.id.fl_days_1)
        val card1 = flDays1.parent.parent as? View
        card1?.setOnClickListener {
            toggleReminder(7, !is7DaysEnabled)
        }

        val flDays2 = findViewById<View>(R.id.fl_days_2)
        val card2 = flDays2.parent.parent as? View
        card2?.setOnClickListener {
            toggleReminder(3, !is3DaysEnabled)
        }

        val flDays3 = findViewById<View>(R.id.fl_days_3)
        val card3 = flDays3.parent.parent as? View
        card3?.setOnClickListener {
            toggleReminder(1, !is1DayEnabled)
        }

        val flDays4 = findViewById<View>(R.id.fl_days_4)
        val card4 = flDays4.parent.parent as? View
        card4?.setOnClickListener {
            toggleReminder(0, !isDueDateEnabled)
        }
    }

    private fun toggleReminder(daysBefore: Int, enable: Boolean) {
        val authHeader = "Bearer $token"
        val req = ReminderToggleRequest(daysBefore, enable)
        api.toggleReminder(authHeader, req).enqueue(object : Callback<GeneralResponse> {
            override fun onResponse(call: Call<GeneralResponse>, response: Response<GeneralResponse>) {
                if (response.isSuccessful) {
                    Toast.makeText(this@NotificationsActivity, "Reminder updated successfully", Toast.LENGTH_SHORT).show()
                    fetchReminders()
                }
            }

            override fun onFailure(call: Call<GeneralResponse>, t: Throwable) {
                Toast.makeText(this@NotificationsActivity, "Failed to toggle reminder", Toast.LENGTH_SHORT).show()
            }
        })
    }

    private fun setupChannelsSettings() {
        findViewById<View>(R.id.layout_setting_sms).setOnClickListener {
            isSmsEnabled = !isSmsEnabled
            saveSetting("SMS", isSmsEnabled)
            updateSettingsUI()
            Toast.makeText(this, "SMS Reminder channel " + (if (isSmsEnabled) "Enabled" else "Disabled"), Toast.LENGTH_SHORT).show()
        }

        findViewById<View>(R.id.layout_setting_whatsapp).setOnClickListener {
            isWhatsappEnabled = !isWhatsappEnabled
            saveSetting("Whatsapp", isWhatsappEnabled)
            updateSettingsUI()
            Toast.makeText(this, "WhatsApp Reminder channel " + (if (isWhatsappEnabled) "Enabled" else "Disabled"), Toast.LENGTH_SHORT).show()
        }

        findViewById<View>(R.id.layout_setting_email).setOnClickListener {
            isEmailEnabled = !isEmailEnabled
            saveSetting("Email", isEmailEnabled)
            updateSettingsUI()
            Toast.makeText(this, "Email Reminder channel " + (if (isEmailEnabled) "Enabled" else "Disabled"), Toast.LENGTH_SHORT).show()
        }

        findViewById<View>(R.id.layout_setting_call).setOnClickListener {
            isCallEnabled = !isCallEnabled
            saveSetting("Call", isCallEnabled)
            updateSettingsUI()
            Toast.makeText(this, "Call Reminder channel " + (if (isCallEnabled) "Enabled" else "Disabled"), Toast.LENGTH_SHORT).show()
        }
    }

    private fun loadLocalSettings() {
        val sharedPref = getSharedPreferences("SmartElectricityPrefs", MODE_PRIVATE)
        isSmsEnabled = sharedPref.getBoolean("SMS_REMINDERS", true)
        isWhatsappEnabled = sharedPref.getBoolean("WHATSAPP_REMINDERS", true)
        isEmailEnabled = sharedPref.getBoolean("EMAIL_REMINDERS", true)
        isCallEnabled = sharedPref.getBoolean("CALL_REMINDERS", true)
        updateSettingsUI()
    }

    private fun saveSetting(key: String, value: Boolean) {
        val sharedPref = getSharedPreferences("SmartElectricityPrefs", MODE_PRIVATE)
        sharedPref.edit().putBoolean("${key.uppercase()}_REMINDERS", value).apply()
    }

    private fun updateSettingsUI() {
        findViewById<TextView>(R.id.tv_settings_sms_status).apply {
            text = if (isSmsEnabled) "Enabled" else "Disabled"
            setTextColor(resources.getColor(if (isSmsEnabled) R.color.green_success else R.color.red_error, null))
        }

        findViewById<TextView>(R.id.tv_settings_whatsapp_status).apply {
            text = if (isWhatsappEnabled) "Enabled" else "Disabled"
            setTextColor(resources.getColor(if (isWhatsappEnabled) R.color.green_success else R.color.red_error, null))
        }

        findViewById<TextView>(R.id.tv_settings_email_status).apply {
            text = if (isEmailEnabled) "Enabled" else "Disabled"
            setTextColor(resources.getColor(if (isEmailEnabled) R.color.green_success else R.color.red_error, null))
        }

        findViewById<TextView>(R.id.tv_settings_call_status).apply {
            text = if (isCallEnabled) "Enabled" else "Disabled"
            setTextColor(resources.getColor(if (isCallEnabled) R.color.green_success else R.color.red_error, null))
        }
    }

    private fun showAddReminderDialog() {
        val dialogView = LayoutInflater.from(this).inflate(R.layout.dialog_add_connection, null)
        val etDays = dialogView.findViewById<EditText>(R.id.et_service_number)
        etDays.hint = "Enter days before due date (e.g. 5)"
        dialogView.findViewById<EditText>(R.id.et_board_name).visibility = View.GONE
        dialogView.findViewById<EditText>(R.id.et_consumer_name).visibility = View.GONE
        dialogView.findViewById<EditText>(R.id.et_address).visibility = View.GONE

        AlertDialog.Builder(this)
            .setTitle("Add Smart Reminder")
            .setView(dialogView)
            .setPositiveButton("Schedule") { _, _ ->
                val daysStr = etDays.text.toString().trim()
                if (daysStr.isEmpty()) {
                    Toast.makeText(this, "Please enter a value", Toast.LENGTH_SHORT).show()
                    return@setPositiveButton
                }
                val days = daysStr.toIntOrNull()
                if (days == null) {
                    Toast.makeText(this, "Invalid number of days", Toast.LENGTH_SHORT).show()
                    return@setPositiveButton
                }
                toggleReminder(days, true)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun fetchNotifications() {
        val authHeader = "Bearer $token"
        api.getNotifications(authHeader).enqueue(object : Callback<List<NotificationResponse>> {
            override fun onResponse(call: Call<List<NotificationResponse>>, response: Response<List<NotificationResponse>>) {
                if (response.isSuccessful && response.body() != null) {
                    notificationList.clear()
                    notificationList.addAll(response.body()!!)
                    adapter.notifyDataSetChanged()
                }
            }

            override fun onFailure(call: Call<List<NotificationResponse>>, t: Throwable) {
                Toast.makeText(this@NotificationsActivity, "Connection failed. Please check your network.", Toast.LENGTH_LONG).show()
            }
        })
    }

    // RecyclerView Adapter
    class NotificationsAdapter(private val list: List<NotificationResponse>) : RecyclerView.Adapter<NotificationsAdapter.ViewHolder>() {

        class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
            val tvTitle: TextView = view.findViewById(R.id.tv_notif_title)
            val tvTime: TextView = view.findViewById(R.id.tv_notif_time)
            val tvMessage: TextView = view.findViewById(R.id.tv_notif_message)
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
            val view = LayoutInflater.from(parent.context).inflate(R.layout.item_notification, parent, false)
            return ViewHolder(view)
        }

        override fun onBindViewHolder(holder: ViewHolder, position: Int) {
            val item = list[position]
            holder.tvTitle.text = item.title
            holder.tvTime.text = item.createdAt
            holder.tvMessage.text = item.message
        }

        override fun getItemCount() = list.size
    }
}
