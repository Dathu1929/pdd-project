package com.smartelectricity.app

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.smartelectricity.app.network.ApiClient
import com.smartelectricity.app.network.ApiInterface
import com.smartelectricity.app.network.ChatRequest
import com.smartelectricity.app.network.ChatResponse
import retrofit2.Call
import retrofit2.Callback
import retrofit2.Response

class ChatActivity : AppCompatActivity() {

    private lateinit var api: ApiInterface
    private var token: String? = null

    private lateinit var rvChat: RecyclerView
    private lateinit var etMessage: EditText
    private lateinit var btnSend: Button
    private val chatList = ArrayList<ChatMessage>()
    private lateinit var adapter: ChatAdapter

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_chat)

        val sharedPref = getSharedPreferences("SmartElectricityPrefs", MODE_PRIVATE)
        token = sharedPref.getString("TOKEN", null)

        if (token == null) {
            finish()
            return
        }

        api = ApiClient.api

        rvChat = findViewById(R.id.rv_chat)
        etMessage = findViewById(R.id.et_chat_message)
        btnSend = findViewById(R.id.btn_chat_send)

        rvChat.layoutManager = LinearLayoutManager(this)
        adapter = ChatAdapter(chatList)
        rvChat.adapter = adapter

        // Add welcome message
        chatList.add(ChatMessage("Hello! Ask me anything about electricity saving tips, current due amounts, or predictions.", isBot = true))
        adapter.notifyItemInserted(0)

        btnSend.setOnClickListener {
            val text = etMessage.text.toString().trim()
            if (text.isEmpty()) return@setOnClickListener

            // Add user message to UI
            chatList.add(ChatMessage(text, isBot = false))
            adapter.notifyItemInserted(chatList.size - 1)
            rvChat.scrollToPosition(chatList.size - 1)
            etMessage.setText("")

            val authHeader = "Bearer $token"
            api.aiChat(authHeader, ChatRequest(text)).enqueue(object : Callback<ChatResponse> {
                override fun onResponse(call: Call<ChatResponse>, response: Response<ChatResponse>) {
                    if (response.isSuccessful && response.body() != null) {
                        val reply = response.body()!!.reply
                        chatList.add(ChatMessage(reply, isBot = true))
                        adapter.notifyItemInserted(chatList.size - 1)
                        rvChat.scrollToPosition(chatList.size - 1)
                    } else {
                        Toast.makeText(this@ChatActivity, "Chat error", Toast.LENGTH_SHORT).show()
                    }
                }

                override fun onFailure(call: Call<ChatResponse>, t: Throwable) {
                    Toast.makeText(this@ChatActivity, "Connection failed. Please check your network.", Toast.LENGTH_LONG).show()
                }
            })
        }
    }

    // Message Data Model
    data class ChatMessage(val text: String, val isBot: Boolean)

    // RecyclerView Adapter
    class ChatAdapter(private val messages: List<ChatMessage>) : RecyclerView.Adapter<ChatAdapter.ViewHolder>() {

        class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
            val layoutBot: LinearLayout = view.findViewById(R.id.layout_bot_message)
            val tvBot: TextView = view.findViewById(R.id.tv_bot_message)
            val layoutUser: LinearLayout = view.findViewById(R.id.layout_user_message)
            val tvUser: TextView = view.findViewById(R.id.tv_user_message)
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
            val view = LayoutInflater.from(parent.context).inflate(R.layout.item_chat_msg, parent, false)
            return ViewHolder(view)
        }

        override fun onBindViewHolder(holder: ViewHolder, position: Int) {
            val item = messages[position]
            if (item.isBot) {
                holder.layoutBot.visibility = View.VISIBLE
                holder.tvBot.text = item.text
                holder.layoutUser.visibility = View.GONE
            } else {
                holder.layoutBot.visibility = View.GONE
                holder.layoutUser.visibility = View.VISIBLE
                holder.tvUser.text = item.text
            }
        }

        override fun getItemCount() = messages.size
    }
}
