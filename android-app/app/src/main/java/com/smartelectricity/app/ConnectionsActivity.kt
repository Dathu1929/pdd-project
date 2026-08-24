package com.smartelectricity.app

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import android.content.Intent
import android.widget.ImageView
import com.google.android.material.bottomnavigation.BottomNavigationView
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.smartelectricity.app.network.ApiClient
import com.smartelectricity.app.network.ApiInterface
import com.smartelectricity.app.network.GeneralResponse
import com.smartelectricity.app.network.MeterRequest
import com.smartelectricity.app.network.MeterResponse
import retrofit2.Call
import retrofit2.Callback
import retrofit2.Response

class ConnectionsActivity : AppCompatActivity() {

    private lateinit var api: ApiInterface
    private var token: String? = null

    private lateinit var rvConnections: RecyclerView
    private lateinit var btnAddNewConnection: Button
    private val metersList = ArrayList<MeterResponse>()
    private lateinit var adapter: ConnectionsAdapter

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_connections)

        val sharedPref = getSharedPreferences("SmartElectricityPrefs", MODE_PRIVATE)
        token = sharedPref.getString("TOKEN", null)

        if (token == null) {
            finish()
            return
        }

        api = ApiClient.api

        rvConnections = findViewById(R.id.rv_connections)
        btnAddNewConnection = findViewById(R.id.btn_add_new_connection)

        rvConnections.layoutManager = LinearLayoutManager(this)
        adapter = ConnectionsAdapter(metersList, ::deleteConnection)
        rvConnections.adapter = adapter

        btnAddNewConnection.setOnClickListener {
            showAddConnectionDialog()
        }

        // Back button navigation
        findViewById<ImageView>(R.id.btn_back).setOnClickListener {
            finish()
        }

        // Bottom Navigation Bar
        val bottomNav = findViewById<BottomNavigationView>(R.id.bottom_navigation)
        bottomNav.selectedItemId = R.id.navigation_connections
        bottomNav.setOnItemSelectedListener { item ->
            when (item.itemId) {
                R.id.navigation_home -> {
                    startActivity(Intent(this, MainActivity::class.java))
                    finish()
                    true
                }
                R.id.navigation_connections -> {
                    true
                }
                R.id.navigation_pay -> {
                    startActivity(Intent(this, BillDetailsActivity::class.java))
                    finish()
                    true
                }
                R.id.navigation_notifications -> {
                    startActivity(Intent(this, NotificationsActivity::class.java))
                    finish()
                    true
                }
                R.id.navigation_profile -> {
                    val sharedPref = getSharedPreferences("SmartElectricityPrefs", MODE_PRIVATE)
                    sharedPref.edit().clear().apply()
                    Toast.makeText(this, "Logged out successfully", Toast.LENGTH_SHORT).show()
                    startActivity(Intent(this, LoginActivity::class.java))
                    finish()
                    true
                }
                else -> false
            }
        }

        fetchConnections()

        // Check if intent specifies to immediately open the add dialog
        val action = intent.getStringExtra("ACTION")
        if (action == "ADD") {
            showAddConnectionDialog()
        }
    }

    private fun fetchConnections() {
        val authHeader = "Bearer $token"
        api.getMeters(authHeader).enqueue(object : Callback<List<MeterResponse>> {
            override fun onResponse(call: Call<List<MeterResponse>>, response: Response<List<MeterResponse>>) {
                if (response.isSuccessful && response.body() != null) {
                    metersList.clear()
                    metersList.addAll(response.body()!!)
                    adapter.notifyDataSetChanged()
                }
            }

            override fun onFailure(call: Call<List<MeterResponse>>, t: Throwable) {
                Toast.makeText(this@ConnectionsActivity, "Connection failed. Please ensure the backend server is running and check your network.", Toast.LENGTH_LONG).show()
            }
        })
    }

    private fun deleteConnection(meterId: Int) {
        val authHeader = "Bearer $token"
        AlertDialog.Builder(this)
            .setTitle("Delete Connection")
            .setMessage("Are you sure you want to delete this connection and all associated bills?")
            .setPositiveButton("Delete") { _, _ ->
                api.deleteMeter(authHeader, meterId).enqueue(object : Callback<GeneralResponse> {
                    override fun onResponse(call: Call<GeneralResponse>, response: Response<GeneralResponse>) {
                        if (response.isSuccessful) {
                            Toast.makeText(this@ConnectionsActivity, "Connection deleted", Toast.LENGTH_SHORT).show()
                            fetchConnections()
                        } else {
                            Toast.makeText(this@ConnectionsActivity, "Failed to delete", Toast.LENGTH_SHORT).show()
                        }
                    }

                    override fun onFailure(call: Call<GeneralResponse>, t: Throwable) {
                        Toast.makeText(this@ConnectionsActivity, "Connection failed. Please check your network.", Toast.LENGTH_LONG).show()
                    }
                })
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun showAddConnectionDialog() {
        val dialogView = LayoutInflater.from(this).inflate(R.layout.dialog_add_connection, null)
        val etBoard = dialogView.findViewById<EditText>(R.id.et_board_name)
        val etService = dialogView.findViewById<EditText>(R.id.et_service_number)
        val etConsumer = dialogView.findViewById<EditText>(R.id.et_consumer_name)
        val etAddress = dialogView.findViewById<EditText>(R.id.et_address)

        AlertDialog.Builder(this)
            .setTitle("Add Connection")
            .setView(dialogView)
            .setPositiveButton("Add") { _, _ ->
                val board = etBoard.text.toString().trim()
                val service = etService.text.toString().trim()
                val consumer = etConsumer.text.toString().trim()
                val address = etAddress.text.toString().trim()

                if (board.isEmpty() || service.isEmpty() || consumer.isEmpty() || address.isEmpty()) {
                    Toast.makeText(this, "Please fill in all fields", Toast.LENGTH_SHORT).show()
                    return@setPositiveButton
                }

                val req = MeterRequest(service, board, consumer, address)
                val authHeader = "Bearer $token"
                api.addMeter(authHeader, req).enqueue(object : Callback<GeneralResponse> {
                    override fun onResponse(call: Call<GeneralResponse>, response: Response<GeneralResponse>) {
                        if (response.isSuccessful) {
                            Toast.makeText(this@ConnectionsActivity, "Connection added successfully", Toast.LENGTH_SHORT).show()
                            fetchConnections()
                        } else {
                            Toast.makeText(this@ConnectionsActivity, "Failed to add connection. Duplicate service number?", Toast.LENGTH_LONG).show()
                        }
                    }

                    override fun onFailure(call: Call<GeneralResponse>, t: Throwable) {
                        Toast.makeText(this@ConnectionsActivity, "Connection failed. Please check your network.", Toast.LENGTH_LONG).show()
                    }
                })
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    // RecyclerView Adapter
    class ConnectionsAdapter(
        private val list: List<MeterResponse>,
        private val onDelete: (Int) -> Unit
    ) : RecyclerView.Adapter<ConnectionsAdapter.ViewHolder>() {

        class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
            val tvBoardName: TextView = view.findViewById(R.id.tv_board_name)
            val tvMeterDetails: TextView = view.findViewById(R.id.tv_meter_details)
            val tvAddress: TextView = view.findViewById(R.id.tv_address)
            val btnDelete: Button = view.findViewById(R.id.btn_delete_connection)
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
            val view = LayoutInflater.from(parent.context).inflate(R.layout.item_connection, parent, false)
            return ViewHolder(view)
        }

        override fun onBindViewHolder(holder: ViewHolder, position: Int) {
            val item = list[position]
            holder.tvBoardName.text = item.boardName
            holder.tvMeterDetails.text = "No: ${item.serviceNumber} | Consumer: ${item.consumerName}"
            holder.tvAddress.text = item.address
            holder.btnDelete.setOnClickListener {
                onDelete(item.id)
            }
        }

        override fun getItemCount() = list.size
    }
}
