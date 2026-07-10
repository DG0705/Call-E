"use client"

import React from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Bar, BarChart, ResponsiveContainer, XAxis, YAxis, Tooltip, PieChart, Pie, Cell } from "recharts"

// Mock Data for the Bar Chart (Call Volume over the week)
const volumeData = [
  { day: "Mon", calls: 120 },
  { day: "Tue", calls: 210 },
  { day: "Wed", calls: 180 },
  { day: "Thu", calls: 240 },
  { day: "Fri", calls: 290 },
  { day: "Sat", calls: 90 },
  { day: "Sun", calls: 75 },
]

// Mock Data for the Pie Chart (Sentiment Breakdown)
const sentimentData = [
  { name: "Positive", value: 65, color: "#16a34a" }, // Green
  { name: "Neutral", value: 20, color: "#94a3b8" },  // Slate
  { name: "Frustrated", value: 15, color: "#dc2626" }, // Red
]

const recentCalls = [
  { id: "CAL-892", phone: "+1 (555) 019-2831", duration: "04:12", sentiment: "Positive", status: "Resolved" },
  { id: "CAL-893", phone: "+1 (555) 837-9102", duration: "12:05", sentiment: "Frustrated", status: "Escalated" },
  { id: "CAL-894", phone: "+1 (555) 443-1129", duration: "01:45", sentiment: "Neutral", status: "Resolved" },
  { id: "CAL-895", phone: "+1 (555) 992-3841", duration: "08:30", sentiment: "Frustrated", status: "Escalated" },
]

export default function DashboardPage() {

  return (
    <div className="bg-white p-8 rounded-xl shadow-sm border border-slate-200 min-h-[500px]">
      <h2 className="text-2xl font-bold text-slate-900 mb-6">Overview</h2>
      
      <div className="grid grid-cols-3 gap-6">
        {/* Placeholder Stat Cards to show off the layout */}
        <div className="p-6 rounded-lg border border-slate-100 bg-slate-50">
          <p className="text-sm font-medium text-slate-500 mb-1">Total Calls</p>
          <p className="text-3xl font-bold text-[#800020]">1,248</p>
        </div>
        
        <div className="p-6 rounded-lg border border-slate-100 bg-slate-50">
          <p className="text-sm font-medium text-slate-500 mb-1">Active APIs</p>
          <p className="text-3xl font-bold text-[#800020]">3</p>
        </div>
        
        <div className="p-6 rounded-lg border border-slate-100 bg-slate-50">
          <p className="text-sm font-medium text-slate-500 mb-1">Credits Remaining</p>
          <p className="text-3xl font-bold text-[#800020]">500</p>
        </div>
      </div>
    </div>
  )
}
