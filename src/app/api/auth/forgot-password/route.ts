import { NextResponse } from "next/server"
import nodemailer from "nodemailer"
import { connectToDatabase } from "@/lib/mongodb"
import User from "@/models/User"

export async function POST(request: Request) {
  try {
    const { email } = await request.json()
    if (!email) return NextResponse.json({ message: "Email is required" }, { status: 400 })

    await connectToDatabase()
    const user = await User.findOne({ email })
    
    if (!user) {
      // Security best practice: Don't reveal if the email exists or not to prevent snooping
      return NextResponse.json({ message: "If an account exists, an OTP was sent." }, { status: 200 })
    }

    // 1. Generate a random 6-digit OTP
    const otp = Math.floor(100000 + Math.random() * 900000).toString()
    
    // 2. Set expiration for 15 minutes from now
    const expireTime = new Date()
    expireTime.setMinutes(expireTime.getMinutes() + 15)

    // 3. Save OTP to database
    user.resetPasswordOtp = otp
    user.resetPasswordExpires = expireTime
    await user.save()

    // 4. Configure the email sender
    const transporter = nodemailer.createTransport({
      service: "gmail",
      auth: {
        user: process.env.EMAIL_USER,
        pass: process.env.EMAIL_PASS,
      },
    })

    // 5. Send the email
    await transporter.sendMail({
      from: `"Call-E Security" <${process.env.EMAIL_USER}>`,
      to: user.email,
      subject: "Your Password Reset Code",
      html: `
        <div style="font-family: sans-serif; text-align: center; padding: 20px;">
          <h2 style="color: #800020;">Call-E Password Reset</h2>
          <p>Your verification code is:</p>
          <h1 style="letter-spacing: 5px; color: #333;">${otp}</h1>
          <p>This code will expire in 15 minutes. Do not share it with anyone.</p>
        </div>
      `,
    })

    return NextResponse.json({ message: "OTP sent successfully" }, { status: 200 })

  } catch (error) {
    console.error("Forgot Password Error:", error)
    return NextResponse.json({ message: "Internal server error" }, { status: 500 })
  }
}