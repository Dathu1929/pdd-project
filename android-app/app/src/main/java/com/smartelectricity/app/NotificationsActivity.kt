package com.smartelectricity.app

import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.widget.CheckBox
import android.widget.ImageView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.bottomnavigation.BottomNavigationView
import com.google.android.material.switchmaterial.SwitchMaterial
import com.smartelectricity.app.network.ApiClient
import com.smartelectricity.app.network.ApiInterface
import com.smartelectricity.app.network.GeneralResponse
import com.smartelectricity.app.network.ReminderResponse
import com.smartelectricity.app.network.ReminderToggleRequest
import com.smartelectricity.app.network.UserProfile
import retrofit2.Call
import retrofit2.Callback
import retrofit2.Response

class NotificationsActivity : AppCompatActivity() {

    private lateinit var api: ApiInterface
    private var token: String? = null

    // General Switch
    private lateinit var switchEnableReminders: SwitchMaterial

    // Timings Checkboxes
    private lateinit var cb7Days: CheckBox
    private lateinit var cb3Days: CheckBox
    private lateinit var cb2Days: CheckBox
    private lateinit var cb1Hour: CheckBox
    private lateinit var cbDueDate: CheckBox

    // Channels Checkboxes
    private lateinit var cbSms: CheckBox
    private lateinit var cbWhatsapp: CheckBox
    private lateinit var cbCall: CheckBox
    private lateinit var cbEmail: CheckBox

    // Quiet Hours Switch
    private lateinit var switchQuietHours: SwitchMaterial

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

        // Bind Views
        switchEnableReminders = findViewById(R.id.switch_enable_reminders)
        
        cb7Days = findViewById(R.id.cb_7_days)
        cb3Days = findViewById(R.id.cb_3_days)
        cb2Days = findViewById(R.id.cb_2_days)
        cb1Hour = findViewById(R.id.cb_1_hour)
        cbDueDate = findViewById(R.id.cb_due_date)

        cbSms = findViewById(R.id.cb_sms)
        cbWhatsapp = findViewById(R.id.cb_whatsapp)
        cbCall = findViewById(R.id.cb_call)
        cbEmail = findViewById(R.id.cb_email)

        switchQuietHours = findViewById(R.id.switch_quiet_hours)

        // Setup Toolbar actions
        findViewById<View>(R.id.btn_back).setOnClickListener {
            finish()
        }

        findViewById<View>(R.id.btn_help).setOnClickListener {
            Toast.makeText(this, "Need help? Settings determine when and how notifications are sent.", Toast.LENGTH_SHORT).show()
        }

        // Profile link in the blue info banner
        findViewById<View>(R.id.tv_profile_link).setOnClickListener {
            showProfileDialog()
        }

        // Disable options when general reminders switch is off
        switchEnableReminders.setOnCheckedChangeListener { _, isChecked ->
            toggleAllOptionsEnabledState(isChecked)
        }

        // Save Settings Action
        findViewById<View>(R.id.btn_save_settings).setOnClickListener {
            saveAllSettings()
        }

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
                    showProfileDialog()
                    false
                }
                else -> false
            }
        }

        // Load Initial Preferences
        loadLocalSettings()
        fetchReminders()
    }

    private fun toggleAllOptionsEnabledState(enabled: Boolean) {
        cb7Days.isEnabled = enabled
        cb3Days.isEnabled = enabled
        cb2Days.isEnabled = enabled
        cb1Hour.isEnabled = enabled
        cbDueDate.isEnabled = enabled

        cbSms.isEnabled = enabled
        cbWhatsapp.isEnabled = enabled
        cbCall.isEnabled = enabled
        cbEmail.isEnabled = enabled

        switchQuietHours.isEnabled = enabled
    }

    private fun loadLocalSettings() {
        val sharedPref = getSharedPreferences("SmartElectricityPrefs", MODE_PRIVATE)
        
        val isGeneralEnabled = sharedPref.getBoolean("GENERAL_REMINDERS_ENABLED", true)
        switchEnableReminders.isChecked = isGeneralEnabled

        cbSms.isChecked = sharedPref.getBoolean("SMS_REMINDERS", true)
        cbWhatsapp.isChecked = sharedPref.getBoolean("WHATSAPP_REMINDERS", true)
        cbCall.isChecked = sharedPref.getBoolean("CALL_REMINDERS", true)
        cbEmail.isChecked = sharedPref.getBoolean("EMAIL_REMINDERS", true)

        switchQuietHours.isChecked = sharedPref.getBoolean("QUIET_HOURS_ENABLED", false)

        toggleAllOptionsEnabledState(isGeneralEnabled)
    }

    private fun fetchReminders() {
        val authHeader = "Bearer $token"
        api.getReminders(authHeader).enqueue(object : Callback<List<ReminderResponse>> {
            override fun onResponse(call: Call<List<ReminderResponse>>, response: Response<List<ReminderResponse>>) {
                if (response.isSuccessful && response.body() != null) {
                    val reminders = response.body()!!
                    for (r in reminders) {
                        val isEnabled = r.enabled == 1
                        when (r.daysBefore) {
                            7 -> cb7Days.isChecked = isEnabled
                            3 -> cb3Days.isChecked = isEnabled
                            2 -> cb2Days.isChecked = isEnabled
                            1 -> cb1Hour.isChecked = isEnabled
                            0 -> cbDueDate.isChecked = isEnabled
                        }
                    }
                }
            }

            override fun onFailure(call: Call<List<ReminderResponse>>, t: Throwable) {
                Toast.makeText(this@NotificationsActivity, "Failed to load timing preferences from server", Toast.LENGTH_SHORT).show()
            }
        })
    }

    private fun saveAllSettings() {
        val sharedPref = getSharedPreferences("SmartElectricityPrefs", MODE_PRIVATE)
        val editor = sharedPref.edit()

        val isGeneralEnabled = switchEnableReminders.isChecked
        editor.putBoolean("GENERAL_REMINDERS_ENABLED", isGeneralEnabled)

        // Save local channels
        editor.putBoolean("SMS_REMINDERS", cbSms.isChecked)
        editor.putBoolean("WHATSAPP_REMINDERS", cbWhatsapp.isChecked)
        editor.putBoolean("CALL_REMINDERS", cbCall.isChecked)
        editor.putBoolean("EMAIL_REMINDERS", cbEmail.isChecked)

        // Save quiet hours
        editor.putBoolean("QUIET_HOURS_ENABLED", switchQuietHours.isChecked)
        editor.apply()

        // If general reminders are disabled, sync that state. Otherwise, save checked timings.
        val authHeader = "Bearer $token"
        val timingsToSave = mapOf(
            7 to (cb7Days.isChecked && isGeneralEnabled),
            3 to (cb3Days.isChecked && isGeneralEnabled),
            2 to (cb2Days.isChecked && isGeneralEnabled),
            1 to (cb1Hour.isChecked && isGeneralEnabled),
            0 to (cbDueDate.isChecked && isGeneralEnabled)
        )

        var completedCalls = 0
        var hasError = false

        for ((daysBefore, enabled) in timingsToSave) {
            val req = ReminderToggleRequest(daysBefore, enabled)
            api.toggleReminder(authHeader, req).enqueue(object : Callback<GeneralResponse> {
                override fun onResponse(call: Call<GeneralResponse>, response: Response<GeneralResponse>) {
                    completedCalls++
                    if (!response.isSuccessful) {
                        hasError = true
                    }
                    checkSavingFinished(completedCalls, timingsToSave.size, hasError)
                }

                override fun onFailure(call: Call<GeneralResponse>, t: Throwable) {
                    completedCalls++
                    hasError = true
                    checkSavingFinished(completedCalls, timingsToSave.size, hasError)
                }
            })
        }
    }

    private fun checkSavingFinished(completed: Int, total: Int, hasError: Boolean) {
        if (completed == total) {
            if (hasError) {
                Toast.makeText(this, "Settings saved locally, but some updates failed on the server.", Toast.LENGTH_SHORT).show()
            } else {
                Toast.makeText(this, "Reminder settings saved successfully!", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun showProfileDialog() {
        val dialogView = LayoutInflater.from(this).inflate(R.layout.dialog_profile_details, null)
        val tvName = dialogView.findViewById<TextView>(R.id.tv_profile_name)
        val tvEmail = dialogView.findViewById<TextView>(R.id.tv_profile_email)
        val tvPhone = dialogView.findViewById<TextView>(R.id.tv_profile_phone)
        val tvAltPhone = dialogView.findViewById<TextView>(R.id.tv_profile_alt_phone)

        val dialog = AlertDialog.Builder(this)
            .setView(dialogView)
            .setPositiveButton("Close", null)
            .setNeutralButton("Log Out") { _, _ ->
                val sharedPref = getSharedPreferences("SmartElectricityPrefs", MODE_PRIVATE)
                sharedPref.edit().clear().apply()
                Toast.makeText(this, "Logged out successfully", Toast.LENGTH_SHORT).show()
                val intent = Intent(this, LoginActivity::class.java)
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
                startActivity(intent)
                finish()
            }
            .create()

        dialog.show()

        val authHeader = "Bearer $token"
        api.getProfile(authHeader).enqueue(object : Callback<UserProfile> {
            override fun onResponse(call: Call<UserProfile>, response: Response<UserProfile>) {
                if (response.isSuccessful && response.body() != null) {
                    val profile = response.body()!!
                    tvName.text = profile.name
                    tvEmail.text = profile.email
                    tvPhone.text = profile.phone ?: "Not Provided"
                    tvAltPhone.text = profile.alternatePhone ?: "Not Provided"
                } else {
                    Toast.makeText(this@NotificationsActivity, "Failed to load profile details", Toast.LENGTH_SHORT).show()
                }
            }

            override fun onFailure(call: Call<UserProfile>, t: Throwable) {
                Toast.makeText(this@NotificationsActivity, "Connection failed. Please check your network.", Toast.LENGTH_SHORT).show()
            }
        })
    }
}
