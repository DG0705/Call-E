"use client"

import React, { useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

export default function ForgotPasswordPage() {
  const router = useRouter()
  const [step, setStep] = useState<1 | 2>(1)
  const [email, setEmail] = useState("")
  const [otp, setOtp] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  // Step 1: Request the OTP
  async function handleSendOtp(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setMessage(null)

    try {
      const res = await fetch("/api/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      })
      const data = await res.json()

      if (!res.ok) throw new Error(data.message)
      
      setMessage("OTP sent to your email!")
      setStep(2) // Move to the next screen
    } catch (err: any) {
      setError(err.message || "Failed to send OTP")
    }
  }

  // Step 2: Verify OTP and Reset Password
  async function handleResetPassword(e: React.FormEvent) {
    e.preventDefault()
    setError(null)

    try {
      const res = await fetch("/api/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, otp, newPassword }),
      })
      const data = await res.json()

      if (!res.ok) throw new Error(data.message)
      
      alert("Password reset successfully! Please sign in.")
      router.push("/sign-in")
    } catch (err: any) {
      setError(err.message || "Failed to reset password")
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#800020] p-4">
      <div className="w-full max-w-md space-y-8 rounded-2xl bg-white p-8 shadow-2xl">
        <div className="text-center">
          <h2 className="text-3xl font-bold tracking-tight text-slate-900">
            {step === 1 ? "Reset Password" : "Enter OTP"}
          </h2>
          <p className="mt-2 text-sm text-slate-600">
            {step === 1 
              ? "Enter your email to receive a verification code" 
              : "Enter the 6-digit code sent to your email"}
          </p>
        </div>

        {error && <div className="rounded-md bg-red-50 p-3 text-sm text-red-500">{error}</div>}
        {message && <div className="rounded-md bg-green-50 p-3 text-sm text-green-600">{message}</div>}

        {step === 1 ? (
          <form onSubmit={handleSendOtp} className="space-y-6">
            <div>
              <label className="text-sm font-medium text-slate-700">Work Email</label>
              <Input 
                type="email" 
                placeholder="admin@company.com" 
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required 
                className="mt-2"
              />
            </div>
            <Button type="submit" className="w-full bg-[#800020] hover:bg-[#5e0b17] text-white">
              Send OTP
            </Button>
          </form>
        ) : (
          <form onSubmit={handleResetPassword} className="space-y-6">
            <div>
              <label className="text-sm font-medium text-slate-700">6-Digit OTP</label>
              <Input 
                type="text" 
                placeholder="123456" 
                value={otp}
                onChange={(e) => setOtp(e.target.value)}
                required 
                className="mt-2"
              />
            </div>
            <div>
              <label className="text-sm font-medium text-slate-700">New Password</label>
              <Input 
                type="password" 
                placeholder="••••••••" 
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required 
                className="mt-2"
              />
            </div>
            <Button type="submit" className="w-full bg-[#800020] hover:bg-[#5e0b17] text-white">
              Update Password
            </Button>
          </form>
        )}

        <div className="text-center text-sm text-slate-600">
          Remember your password?{" "}
          <Link href="/sign-in" className="font-semibold text-[#800020] hover:text-[#5e0b17]">
            Sign in
          </Link>
        </div>
      </div>
    </div>
  )
}