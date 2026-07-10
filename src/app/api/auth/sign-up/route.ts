import { NextResponse } from "next/server"
import bcrypt from "bcryptjs"
import nodemailer from "nodemailer"
import { connectToDatabase } from "@/lib/mongodb"
import User from "@/models/User"

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const { companyName, email, password } = body

    if (!companyName || !email || !password) {
      return NextResponse.json({ message: "Missing required fields" }, { status: 400 })
    }

    await connectToDatabase()

    // 1. Check if user already exists
    let user = await User.findOne({ email })
    
    if (user && user.isVerified) {
      return NextResponse.json({ message: "Email is already registered" }, { status: 400 })
    }

    // 2. Generate a 6-digit OTP
    const otp = Math.floor(100000 + Math.random() * 900000).toString()
    const expireTime = new Date()
    expireTime.setMinutes(expireTime.getMinutes() + 15)
    
    // 3. Hash the password
    const hashedPassword = await bcrypt.hash(password, 10)

    // 4. Create or update the unverified user
    if (user && !user.isVerified) {
      // If they tried to sign up before but didn't verify, update their info
      user.companyName = companyName
      user.password = hashedPassword
      user.verificationOtp = otp
      user.verificationExpires = expireTime
      await user.save()
    } else {
      // Brand new user
      user = await User.create({
        companyName,
        email,
        password: hashedPassword,
        isVerified: false,
        verificationOtp: otp,
        verificationExpires: expireTime,
      })
    }

    // 5. Send the verification email
    const transporter = nodemailer.createTransport({
      service: "gmail",
      auth: {
        user: process.env.EMAIL_USER,
        pass: process.env.EMAIL_PASS,
      },
    })

    await transporter.sendMail({
      from: `"Call-E Onboarding" <${process.env.EMAIL_USER}>`,
      to: email,
      subject: "Verify your Call-E account",
      html: `
        <div style="font-family: sans-serif; text-align: center; padding: 20px;">
          <h2 style="color: #800020;">Welcome to Call-E!</h2>
          <p>Please verify your email address with the code below:</p>
          <h1 style="letter-spacing: 5px; color: #333;">${otp}</h1>
          <p>This code will expire in 15 minutes.</p>
        </div>
      `,
    })

    return NextResponse.json({ message: "Verification OTP sent!" }, { status: 200 })
    
  } catch (error) {
    console.error("Sign-up Error:", error)
    return NextResponse.json({ message: "Internal server error" }, { status: 500 })
  }
}