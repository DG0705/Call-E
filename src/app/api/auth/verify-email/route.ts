import { NextResponse } from "next/server"
import jwt from "jsonwebtoken"
import { connectToDatabase } from "@/lib/mongodb"
import User from "@/models/User"

export async function POST(request: Request) {
  try {
    const { email, otp } = await request.json()

    if (!email || !otp) {
      return NextResponse.json({ message: "Missing required fields" }, { status: 400 })
    }

    await connectToDatabase()

    const user = await User.findOne({
      email: email,
      verificationOtp: otp,
      verificationExpires: { $gt: Date.now() },
    })

    if (!user) {
      return NextResponse.json({ message: "Invalid or expired OTP" }, { status: 400 })
    }

    // 1. Mark as verified and clear OTP data
    user.isVerified = true
    user.verificationOtp = undefined
    user.verificationExpires = undefined
    await user.save()

    // 2. Issue the JWT Session Cookie
    const token = jwt.sign(
      { userId: user._id, email: user.email },
      process.env.JWT_SECRET as string,
      { expiresIn: "7d" }
    )

    const response = NextResponse.json(
      { message: "Email verified successfully!" },
      { status: 200 }
    )

    response.cookies.set("calle-auth-token", token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      maxAge: 60 * 60 * 24 * 7,
      path: "/",
    })

    return response
    
  } catch (error) {
    console.error("Verification Error:", error)
    return NextResponse.json({ message: "Internal server error" }, { status: 500 })
  }
}