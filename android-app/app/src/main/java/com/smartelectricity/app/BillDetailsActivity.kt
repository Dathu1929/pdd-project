package com.smartelectricity.app

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.smartelectricity.app.network.ApiClient
import com.smartelectricity.app.network.ApiInterface
import com.smartelectricity.app.network.BillResponse
import retrofit2.Call
import retrofit2.Callback
import retrofit2.Response
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.TimeUnit

class BillDetailsActivity : AppCompatActivity() {

    private lateinit var api: ApiInterface
    private var token: String? = null
    private var meterFilter: String? = null

    private lateinit var tvBillMonth: TextView
    private lateinit var tvBillMeterNumber: TextView
    private lateinit var tvBillAmount: TextView
    private lateinit var tvBillDueDays: TextView
    private lateinit var tvUnitsValDetail: TextView
    private lateinit var btnPay: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_bill_details)

        val sharedPref = getSharedPreferences("SmartElectricityPrefs", MODE_PRIVATE)
        token = sharedPref.getString("TOKEN", null)
        meterFilter = intent.getStringExtra("METER_NUMBER")

        if (token == null) {
            finish()
            return
        }

        api = ApiClient.api

        tvBillMonth = findViewById(R.id.tv_bill_month)
        tvBillMeterNumber = findViewById(R.id.tv_bill_meter_number)
        tvBillAmount = findViewById(R.id.tv_bill_amount)
        tvBillDueDays = findViewById(R.id.tv_bill_due_days)
        tvUnitsValDetail = findViewById(R.id.tv_units_val_detail)
        btnPay = findViewById(R.id.btn_pay_bill_detail)

        fetchBillDetails()
    }

    private fun fetchBillDetails() {
        val authHeader = "Bearer $token"
        api.getBills(authHeader).enqueue(object : Callback<List<BillResponse>> {
            override fun onResponse(call: Call<List<BillResponse>>, response: Response<List<BillResponse>>) {
                if (response.isSuccessful && response.body() != null) {
                    val bills = response.body()!!
                    
                    // Filter or find the target bill
                    val targetBill = if (meterFilter != null) {
                        // Attempt to find unpaid first, else latest
                        bills.find { it.paymentStatus == "Unpaid" } ?: bills.firstOrNull()
                    } else {
                        bills.find { it.paymentStatus == "Unpaid" } ?: bills.firstOrNull()
                    }

                    if (targetBill != null) {
                        displayBill(targetBill)
                    } else {
                        showNoBill()
                    }
                } else {
                    Toast.makeText(this@BillDetailsActivity, "Failed to load bills", Toast.LENGTH_SHORT).show()
                }
            }

            override fun onFailure(call: Call<List<BillResponse>>, t: Throwable) {
                Toast.makeText(this@BillDetailsActivity, "Connection failed. Please check your network.", Toast.LENGTH_LONG).show()
            }
        })
    }

    private fun displayBill(bill: BillResponse) {
        tvBillMonth.text = bill.billingMonth
        tvBillMeterNumber.text = "Service No: ${bill.serviceNumber ?: "N/A"}"
        tvBillAmount.text = String.format("₹%.2f", bill.amount)
        tvUnitsValDetail.text = String.format("%.1f kWh", bill.unitsConsumed)

        if (bill.paymentStatus == "Paid") {
            tvBillDueDays.text = "Paid"
            tvBillDueDays.setTextColor(resources.getColor(R.color.green_success, null))
            btnPay.visibility = View.GONE
        } else {
            btnPay.visibility = View.VISIBLE
            val daysLeft = calculateDaysRemaining(bill.dueDate)
            if (daysLeft >= 0) {
                tvBillDueDays.text = "Due in $daysLeft days"
                tvBillDueDays.setTextColor(resources.getColor(R.color.orange_warning, null))
            } else {
                tvBillDueDays.text = "Overdue by ${-daysLeft} days"
                tvBillDueDays.setTextColor(resources.getColor(R.color.red_error, null))
            }

            btnPay.setOnClickListener {
                val intent = Intent(this, PaymentActivity::class.java)
                intent.putExtra("BILL_ID", bill.id)
                intent.putExtra("AMOUNT", bill.amount)
                intent.putExtra("SERVICE_NUMBER", bill.serviceNumber ?: "N/A")
                intent.putExtra("CONSUMER_NAME", bill.consumerName ?: "User")
                intent.putExtra("DUE_DATE", bill.dueDate)
                intent.putExtra("BILLING_MONTH", bill.billingMonth)
                startActivity(intent)
            }
        }
    }

    private fun showNoBill() {
        tvBillMonth.text = "No Bill"
        tvBillMeterNumber.text = ""
        tvBillAmount.text = "₹0.00"
        tvBillDueDays.text = "No pending actions"
        tvUnitsValDetail.text = "0 kWh"
        btnPay.visibility = View.GONE
    }

    private fun calculateDaysRemaining(dueDateStr: String): Long {
        return try {
            val sdf = SimpleDateFormat("yyyy-MM-dd", Locale.getDefault())
            val dueDate = sdf.parse(dueDateStr) ?: Date()
            val today = sdf.parse(sdf.format(Date())) ?: Date()
            val diff = dueDate.time - today.time
            TimeUnit.DAYS.convert(diff, TimeUnit.MILLISECONDS)
        } catch (e: Exception) {
            0
        }
    }
}
