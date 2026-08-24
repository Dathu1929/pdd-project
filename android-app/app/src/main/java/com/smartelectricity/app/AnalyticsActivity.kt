package com.smartelectricity.app

import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import com.github.mikephil.charting.charts.BarChart
import com.github.mikephil.charting.data.BarData
import com.github.mikephil.charting.data.BarDataSet
import com.github.mikephil.charting.data.BarEntry

class AnalyticsActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_analytics)

        val barChart = findViewById<BarChart>(R.id.bar_chart)

        // Setup mock daily consumption data (kWh) for the last 7 days
        val entries = ArrayList<BarEntry>()
        entries.add(BarEntry(1f, 8.2f))
        entries.add(BarEntry(2f, 9.5f))
        entries.add(BarEntry(3f, 7.8f))
        entries.add(BarEntry(4f, 11.2f))
        entries.add(BarEntry(5f, 6.5f))
        entries.add(BarEntry(6f, 12.5f))
        entries.add(BarEntry(7f, 8.9f))

        val dataSet = BarDataSet(entries, "Daily Energy Consumption (kWh)")
        dataSet.color = resources.getColor(R.color.primary_light, null)
        dataSet.valueTextColor = resources.getColor(R.color.text_white, null)
        dataSet.valueTextSize = 10f

        val barData = BarData(dataSet)
        barChart.data = barData

        // Sleek Premium Dark Mode Styling
        barChart.description.isEnabled = false
        barChart.legend.textColor = resources.getColor(R.color.text_muted, null)
        barChart.xAxis.textColor = resources.getColor(R.color.text_muted, null)
        barChart.axisLeft.textColor = resources.getColor(R.color.text_muted, null)
        barChart.axisRight.isEnabled = false
        barChart.xAxis.setDrawGridLines(false)
        barChart.axisLeft.setDrawGridLines(true)
        barChart.axisLeft.gridColor = 0x22FFFFFF
        barChart.setTouchEnabled(true)
        barChart.animateY(1000)
        barChart.invalidate() // Refresh
    }
}
