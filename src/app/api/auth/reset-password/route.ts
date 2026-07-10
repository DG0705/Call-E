import { NextResponse } from "next/server"
import bcrypt from "bcryptjs"
import { connectToDatabase } from "@/lib/mongodb"
import User from "@/models/User"

export async function POST(request: Request) {
  try {
    const { email, otp, newPassword } = await request.json()

    if (!email || !otp || !newPassword) {
      return NextResponse.json({ message: "Missing required fields" }, { status: 400 })
    }

    await connectToDatabase()

    // 1. Find the user and check if the OTP matches and hasn't expired
    const user = await User.findOne({
      email: email,
      resetPasswordOtp: otp,
      resetPasswordExpires: { $gt: Date.now() }, // $gt means "Greater Than" right now
    })

    if (!user) {
      return NextResponse.json({ message: "Invalid or expired OTP" }, { status: 400 })
    }

    // 2. Hash the new password
    const hashedNewPassword = await bcrypt.hash(newPassword, 10)

    // 3. Update the password and instantly erase the OTP fields so they can't be reused
    user.password = hashedNewPassword
    user.resetPasswordOtp = undefined
    user.resetPasswordExpires = undefined
    await user.save()

    return NextResponse.json({ message: "Password reset successfully!" }, { status: 200 })
    
  } catch (error) {
    console.error("Reset Password Error:", error)
    return NextResponse.json({ message: "Internal server error" }, { status: 500 })
  }
}