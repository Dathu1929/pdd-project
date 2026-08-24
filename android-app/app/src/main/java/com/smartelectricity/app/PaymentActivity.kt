package com.smartelectricity.app

import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.RadioButton
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.smartelectricity.app.network.ApiClient
import com.smartelectricity.app.network.ApiInterface
import com.smartelectricity.app.network.GeneralResponse
import com.smartelectricity.app.network.PaymentRequest
import retrofit2.Call
import retrofit2.Callback
import retrofit2.Response

class PaymentActivity : AppCompatActivity() {

    private lateinit var api: ApiInterface
    private var token: String? = null
    private var billId: Int = -1
    private var amount: Double = 0.0

    private lateinit var rbUpi: RadioButton
    private lateinit var rbCard: RadioButton
    private lateinit var rbNetbanking: RadioButton
    private lateinit var rbWallet: RadioButton
    private lateinit var rbOtherUpi: RadioButton

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_payment)

        val sharedPref = getSharedPreferences("SmartElectricityPrefs", MODE_PRIVATE)
        token = sharedPref.getString("TOKEN", null)

        billId = intent.getIntExtra("BILL_ID", -1)
        amount = intent.getDoubleExtra("AMOUNT", 0.0)
        val serviceNumber = intent.getStringExtra("SERVICE_NUMBER") ?: "N/A"
        val consumerName = intent.getStringExtra("CONSUMER_NAME") ?: "User"
        val dueDate = intent.getStringExtra("DUE_DATE") ?: "N/A"
        val billingMonth = intent.getStringExtra("BILLING_MONTH") ?: "N/A"

        if (token == null || billId == -1) {
            finish()
            return
        }

        api = ApiClient.api

        // Bind Bill Summary Views
        findViewById<TextView>(R.id.tv_summary_service_number).text = serviceNumber
        findViewById<TextView>(R.id.tv_summary_consumer_name).text = consumerName
        findViewById<TextView>(R.id.tv_summary_billing_month).text = billingMonth
        findViewById<TextView>(R.id.tv_summary_due_date).text = dueDate
        
        val amountStr = String.format("₹ %.2f", amount)
        findViewById<TextView>(R.id.tv_summary_total_amount).text = amountStr
        findViewById<TextView>(R.id.tv_bottom_amount).text = amountStr

        // Bind Radio Buttons
        rbUpi = findViewById(R.id.rb_upi_select)
        rbCard = findViewById(R.id.rb_card_select)
        rbNetbanking = findViewById(R.id.rb_netbanking_select)
        rbWallet = findViewById(R.id.rb_wallet_select)
        rbOtherUpi = findViewById(R.id.rb_other_upi_select)

        // Bind Row Layouts for full row selectability
        findViewById<LinearLayout>(R.id.row_upi).setOnClickListener { selectMethod("UPI") }
        findViewById<LinearLayout>(R.id.row_card).setOnClickListener { selectMethod("Card") }
        findViewById<LinearLayout>(R.id.row_netbanking).setOnClickListener { selectMethod("NetBanking") }
        findViewById<LinearLayout>(R.id.row_wallet).setOnClickListener { selectMethod("Wallet") }
        findViewById<LinearLayout>(R.id.row_other_upi).setOnClickListener { selectMethod("OtherUPI") }

        // Back Navigation
        findViewById<ImageButton>(R.id.btn_back).setOnClickListener {
            finish()
        }

        val btnPay = findViewById<Button>(R.id.btn_complete_payment)
        btnPay.setOnClickListener {
            val selectedMethod = getSelectedPaymentMethod()
            val authHeader = "Bearer $token"
            val req = PaymentRequest(billId, amount, selectedMethod)

            api.makePayment(authHeader, req).enqueue(object : Callback<GeneralResponse> {
                override fun onResponse(call: Call<GeneralResponse>, response: Response<GeneralResponse>) {
                    if (response.isSuccessful && response.body() != null) {
                        Toast.makeText(this@PaymentActivity, "Payment Successful!", Toast.LENGTH_LONG).show()
                        
                        // Clear backstack and go home
                        val intent = Intent(this@PaymentActivity, MainActivity::class.java)
                        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
                        startActivity(intent)
                        finish()
                    } else {
                        Toast.makeText(this@PaymentActivity, "Payment Failed", Toast.LENGTH_SHORT).show()
                    }
                }

                override fun onFailure(call: Call<GeneralResponse>, t: Throwable) {
                    Toast.makeText(this@PaymentActivity, "Connection failed. Please check your network.", Toast.LENGTH_LONG).show()
                }
            })
        }
    }

    private fun selectMethod(method: String) {
        rbUpi.isChecked = method == "UPI"
        rbCard.isChecked = method == "Card"
        rbNetbanking.isChecked = method == "NetBanking"
        rbWallet.isChecked = method == "Wallet"
        rbOtherUpi.isChecked = method == "OtherUPI"
    }

    private fun getSelectedPaymentMethod(): String {
        return when {
            rbUpi.isChecked -> "UPI"
            rbCard.isChecked -> "Card"
            rbNetbanking.isChecked -> "NetBanking"
            rbWallet.isChecked -> "Wallet"
            rbOtherUpi.isChecked -> "UPI"
            else -> "UPI"
        }
    }
}
