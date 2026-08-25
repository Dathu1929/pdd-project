package com.smartelectricity.app

import androidx.appcompat.app.AlertDialog
import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.bottomnavigation.BottomNavigationView
import com.smartelectricity.app.network.ApiClient
import com.smartelectricity.app.network.ApiInterface
import com.smartelectricity.app.network.BillResponse
import com.smartelectricity.app.network.MeterResponse
import com.smartelectricity.app.network.UserProfile
import retrofit2.Call
import retrofit2.Callback
import retrofit2.Response

class MainActivity : AppCompatActivity() {

    private lateinit var api: ApiInterface
    private var token: String? = null

    private lateinit var tvWelcomeName: TextView
    private lateinit var tvDueVal: TextView
    private lateinit var tvUnitsVal: TextView
    private lateinit var tvDueDateVal: TextView
    private lateinit var etSearchMeter: EditText

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_home)

        // Retrieve authentication details
        val sharedPref = getSharedPreferences("SmartElectricityPrefs", MODE_PRIVATE)
        token = intent.getStringExtra("TOKEN") ?: sharedPref.getString("TOKEN", null)
        val name = intent.getStringExtra("NAME") ?: sharedPref.getString("NAME", "User")

        if (token == null) {
            // Redirect to Login if no token found
            startActivity(Intent(this, LoginActivity::class.java))
            finish()
            return
        }

        // Initialize API Client
        api = ApiClient.api

        // Bind Views
        tvWelcomeName = findViewById(R.id.tv_welcome_name)
        tvDueVal = findViewById(R.id.tv_due_val)
        tvUnitsVal = findViewById(R.id.tv_units_val)
        tvDueDateVal = findViewById(R.id.tv_due_date_val)
        etSearchMeter = findViewById(R.id.et_search_meter)

        tvWelcomeName.text = "Hi, $name 👋"

        val btnBell = findViewById<ImageButton>(R.id.btn_bell)
        val btnViewDetails = findViewById<Button>(R.id.btn_view_details)
        val btnAddConnection = findViewById<Button>(R.id.btn_add_connection)

        // Quick Actions
        val actionPay = findViewById<LinearLayout>(R.id.action_pay)
        val actionHistory = findViewById<LinearLayout>(R.id.action_history)
        val actionAnalytics = findViewById<LinearLayout>(R.id.action_analytics)
        val actionBot = findViewById<LinearLayout>(R.id.action_bot)

        // Bottom Navigation
        val bottomNav = findViewById<BottomNavigationView>(R.id.bottom_navigation)

        // Fetch Dashboard Data
        refreshDashboardData()

        btnBell.setOnClickListener {
            startActivity(Intent(this, NotificationsActivity::class.java))
        }

        findViewById<Button>(R.id.btn_pay_now_direct).setOnClickListener {
            startActivity(Intent(this, BillDetailsActivity::class.java))
        }

        findViewById<Button>(R.id.btn_enable_reminders).setOnClickListener {
            Toast.makeText(this, "Smart reminders enabled!", Toast.LENGTH_SHORT).show()
            startActivity(Intent(this, NotificationsActivity::class.java))
        }

        btnViewDetails.setOnClickListener {
            val meterNum = etSearchMeter.text.toString().trim()
            if (meterNum.isEmpty()) {
                Toast.makeText(this, "Please enter a meter number", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            // Navigate to BillDetailsActivity for specific meter
            val intent = Intent(this, BillDetailsActivity::class.java)
            intent.putExtra("METER_NUMBER", meterNum)
            startActivity(intent)
        }

        btnAddConnection.setOnClickListener {
            val intent = Intent(this, ConnectionsActivity::class.java)
            intent.putExtra("ACTION", "ADD")
            startActivity(intent)
        }

        actionPay.setOnClickListener {
            // View Bills goes to BillDetailsActivity
            val intent = Intent(this, BillDetailsActivity::class.java)
            startActivity(intent)
        }

        actionHistory.setOnClickListener {
            // Make Payment goes to BillDetailsActivity to choose and pay
            val intent = Intent(this, BillDetailsActivity::class.java)
            startActivity(intent)
        }

        actionAnalytics.setOnClickListener {
            // Reminders goes to NotificationsActivity
            startActivity(Intent(this, NotificationsActivity::class.java))
        }

        actionBot.setOnClickListener {
            // Usage Analytics goes to AnalyticsActivity
            startActivity(Intent(this, AnalyticsActivity::class.java))
        }

        // Active Connection Details Card goes to ConnectionsActivity
        findViewById<View>(R.id.card_active_connection).setOnClickListener {
            startActivity(Intent(this, ConnectionsActivity::class.java))
        }

        // Recent Bill Card goes to BillDetailsActivity
        findViewById<View>(R.id.card_recent_bill).setOnClickListener {
            startActivity(Intent(this, BillDetailsActivity::class.java))
        }

        // View All Bills link goes to BillDetailsActivity
        findViewById<View>(R.id.btn_view_all_bills).setOnClickListener {
            startActivity(Intent(this, BillDetailsActivity::class.java))
        }

        // Menu Icon Toast trigger
        findViewById<View>(R.id.btn_menu).setOnClickListener {
            Toast.makeText(this, "Main menu opened!", Toast.LENGTH_SHORT).show()
        }

        // Profile Icon dialog box (Account view and Logout shortcut)
        findViewById<View>(R.id.btn_profile).setOnClickListener {
            showProfileDialog()
        }

        bottomNav.setOnItemSelectedListener { item ->
            when (item.itemId) {
                R.id.navigation_home -> {
                    refreshDashboardData()
                    true
                }
                R.id.navigation_connections -> {
                    startActivity(Intent(this, ConnectionsActivity::class.java))
                    true
                }
                R.id.navigation_pay -> {
                    startActivity(Intent(this, BillDetailsActivity::class.java))
                    true
                }
                R.id.navigation_notifications -> {
                    startActivity(Intent(this, NotificationsActivity::class.java))
                    true
                }
                R.id.navigation_profile -> {
                    showProfileDialog()
                    false
                }
                else -> false
            }
        }
    }

    override fun onResume() {
        super.onResume()
        refreshDashboardData()
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
                    Toast.makeText(this@MainActivity, "Failed to load profile details", Toast.LENGTH_SHORT).show()
                }
            }

            override fun onFailure(call: Call<UserProfile>, t: Throwable) {
                Toast.makeText(this@MainActivity, "Connection failed. Please check your network.", Toast.LENGTH_SHORT).show()
            }
        })
    }

    private fun refreshDashboardData() {
        val authHeader = "Bearer $token"
        
        // Fetch profile to make sure name is updated
        api.getProfile(authHeader).enqueue(object : Callback<UserProfile> {
            override fun onResponse(call: Call<UserProfile>, response: Response<UserProfile>) {
                if (response.isSuccessful && response.body() != null) {
                    val profile = response.body()!!
                    tvWelcomeName.text = "Hi, ${profile.name} 👋"
                }
            }
            override fun onFailure(call: Call<UserProfile>, t: Throwable) {}
        })

        // Fetch bills
        api.getBills(authHeader).enqueue(object : Callback<List<BillResponse>> {
            override fun onResponse(call: Call<List<BillResponse>>, response: Response<List<BillResponse>>) {
                if (response.isSuccessful && response.body() != null) {
                    val bills = response.body()!!
                    val unpaid = bills.filter { it.paymentStatus == "Unpaid" }
                    if (unpaid.isNotEmpty()) {
                        val totalDue = unpaid.sumOf { it.amount }
                        tvDueVal.text = String.format("₹%.2f", totalDue)
                        tvDueDateVal.text = unpaid[0].dueDate
                        
                        // Select units consumed from the most recent bill
                        tvUnitsVal.text = String.format("%.1f kWh", bills[0].unitsConsumed)
                    } else {
                        tvDueVal.text = "₹0.00"
                        tvDueDateVal.text = "All paid"
                        if (bills.isNotEmpty()) {
                            tvUnitsVal.text = String.format("%.1f kWh", bills[0].unitsConsumed)
                        } else {
                            tvUnitsVal.text = "0 kWh"
                        }
                    }
                }
            }

            override fun onFailure(call: Call<List<BillResponse>>, t: Throwable) {
                Toast.makeText(this@MainActivity, "Connection failed. Please check your network.", Toast.LENGTH_LONG).show()
            }
        })
    }
}
