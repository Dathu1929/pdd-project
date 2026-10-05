package com.smartelectricity.app

import android.content.Context
import android.os.Bundle
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.Spinner
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken

class AddConnectionActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_add_connection)

        val spinnerEB = findViewById<Spinner>(R.id.spinnerEB)
        val etServiceNumber = findViewById<EditText>(R.id.etServiceNumber)
        val etConsumerName = findViewById<EditText>(R.id.etConsumerName)
        val etAddress = findViewById<EditText>(R.id.etAddress)
        val btnSave = findViewById<Button>(R.id.btnSaveConnection)
        val btnCancel = findViewById<Button>(R.id.btnCancelConnection)

        val ebOptions = arrayOf(
            "Tamil Nadu Generation and Distribution Corp (TANGEDCO) - 12 Digits",
            "BESCOM - 10 Digits",
            "KSEB - 13 Digits",
            "APEPDCL - 12 to 16 Digits",
            "Maharashtra State Electricity Distribution Co. (MSEDCL) - 12 Digits",
            "Uttar Pradesh Power Corporation Ltd (UPPCL) - 10 to 12 Digits",
            "Punjab State Power Corporation Ltd (PSPCL) - 10 Digits",
            "West Bengal State Electricity Distribution Co. (WBSEDCL) - 9 Digits",
            "Telangana State Southern Power Distribution Co. (TSSPDCL) - 8 to 9 Digits",
            "Torrent Power - 9 to 10 Digits"
        )
        val adapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, ebOptions)
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        spinnerEB.adapter = adapter

        btnSave.setOnClickListener {
            val eb = spinnerEB.selectedItem.toString()
            val serviceNum = etServiceNumber.text.toString()
            val name = etConsumerName.text.toString()
            val addr = etAddress.text.toString()

            if (serviceNum.isEmpty() || name.isEmpty()) {
                Toast.makeText(this, "Please fill in all required fields", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            val newConnection = Connection(eb, serviceNum, name, addr)
            saveConnectionLocally(newConnection)

            Toast.makeText(this, "Connection Saved Successfully!", Toast.LENGTH_SHORT).show()
            finish()
        }

        btnCancel.setOnClickListener {
            finish()
        }
    }

    private fun saveConnectionLocally(connection: Connection) {
        val sharedPref = getSharedPreferences("SmartElectricityPrefs", Context.MODE_PRIVATE)
        val gson = Gson()
        
        // Load existing connections
        val json = sharedPref.getString("SAVED_CONNECTIONS", null)
        val type = object : TypeToken<MutableList<Connection>>() {}.type
        val connectionList: MutableList<Connection> = if (json == null) {
            mutableListOf()
        } else {
            gson.fromJson(json, type)
        }

        // Add new and save back
        connectionList.add(connection)
        val newJson = gson.toJson(connectionList)
        sharedPref.edit().putString("SAVED_CONNECTIONS", newJson).apply()
    }
}
