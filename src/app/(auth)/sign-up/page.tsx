"use client"

import React, { useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

export default function SignUpPage() {
  const router = useRouter()
  const [step, setStep] = useState<1 | 2>(1)
  const [error, setError] = useState<string | null>(null)
  
  // Form State
  const [companyName, setCompanyName] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [otp, setOtp] = useState("")

  // Step 1: Submit Details & Request OTP
  async function handleSignUp(e: React.FormEvent) {
    e.preventDefault()
    setError(null)

    if (password !== confirmPassword) {
      return setError("Passwords do not match")
    }

    try {
      const res = await fetch("/api/auth/sign-up", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ companyName, email, password }),
      })
      const data = await res.json()

      if (!res.ok) throw new Error(data.message)
      
      setStep(2) // Move to verification step
    } catch (err: any) {
      setError(err.message || "Failed to create account")
    }
  }

  // Step 2: Verify OTP
  async function handleVerify(e: React.FormEvent) {
    e.preventDefault()
    setError(null)

    try {
      const res = await fetch("/api/auth/verify-email", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, otp }),
      })
      const data = await res.json()

      if (!res.ok) throw new Error(data.message)
      
      // Verification successful, JWT is set! Glide to Dashboard.
      router.push("/dashboard")
    } catch (err: any) {
      setError(err.message || "Failed to verify email")
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#800020] p-4">
      <div className="w-full max-w-md space-y-8 rounded-2xl bg-white p-8 shadow-2xl">
        <div className="text-center">
          <h2 className="text-3xl font-bold tracking-tight text-slate-900">
            {step === 1 ? "Create an account" : "Verify your email"}
          </h2>
          <p className="mt-2 text-sm text-slate-600">
            {step === 1 
              ? "Enter your enterprise details to get started"
              : `We sent a code to ${email}`}
          </p>
        </div>

        {error && <div className="rounded-md bg-red-50 p-3 text-sm text-red-500">{error}</div>}

        {step === 1 ? (
          <form onSubmit={handleSignUp} className="space-y-6">
            <div>
              <label className="text-sm font-medium text-slate-700">Company Name</label>
              <Input 
                type="text" 
                placeholder="Acme Corp" 
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                required className="mt-2" 
              />
            </div>
            <div>
              <label className="text-sm font-medium text-slate-700">Work Email</label>
              <Input 
                type="email" 
                placeholder="admin@company.com" 
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required className="mt-2" 
              />
            </div>
            <div>
              <label className="text-sm font-medium text-slate-700">Password</label>
              <Input 
                type="password" 
                placeholder="••••••••" 
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required className="mt-2" 
              />
            </div>
            <div>
              <label className="text-sm font-medium text-slate-700">Confirm Password</label>
              <Input 
                type="password" 
                placeholder="••••••••" 
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required className="mt-2" 
              />
            </div>
            <Button type="submit" className="w-full bg-[#800020] hover:bg-[#5e0b17] text-white">
              Sign Up
            </Button>
          </form>
        ) : (
          <form onSubmit={handleVerify} className="space-y-6">
            <div>
              <label className="text-sm font-medium text-slate-700">6-Digit Code</label>
              <Input 
                type="text" 
                placeholder="123456" 
                value={otp}
                onChange={(e) => setOtp(e.target.value)}
                required className="mt-2 text-center text-lg tracking-[0.5em]" 
              />
            </div>
            <Button type="submit" className="w-full bg-[#800020] hover:bg-[#5e0b17] text-white">
              Verify & Enter Dashboard
            </Button>
          </form>
        )}

        {step === 1 && (
          <div className="text-center text-sm text-slate-600">
            Already have an account?{" "}
            <Link href="/sign-in" className="font-semibold text-[#800020] hover:text-[#5e0b17]">
              Sign in
            </Link>
          </div>
        )}
      </div>
    </div>
  )
}