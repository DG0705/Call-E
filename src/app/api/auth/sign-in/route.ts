import { NextResponse } from "next/server"
import bcrypt from "bcryptjs"
import jwt from "jsonwebtoken"
import { connectToDatabase } from "@/lib/mongodb"
import User from "@/models/User"

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const { email, password } = body

    if (!email || !password) {
      return NextResponse.json({ message: "Missing required fields" }, { status: 400 })
    }

    await connectToDatabase()

    const existingUser = await User.findOne({ email }).select('+password')
    if (!existingUser) {
      return NextResponse.json({ message: "Invalid email or password" }, { status: 401 })
    }

    const isPasswordValid = await bcrypt.compare(password, existingUser.password)
    if (!isPasswordValid) {
      return NextResponse.json({ message: "Invalid email or password" }, { status: 401 })
    }
    
    // --- CREATE THE SECURE SESSION ---
    // Declared only ONCE here!
    const token = jwt.sign(
      { userId: existingUser._id, email: existingUser.email },
      process.env.JWT_SECRET as string,
      { expiresIn: "7d" }
    )

    // 1. Create the response first
    const response = NextResponse.json(
      { message: "Login successful!", userId: existingUser._id },
      { status: 200 }
    )

    // 2. Attach the cookie safely to the response
    response.cookies.set("calle-auth-token", token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      maxAge: 60 * 60 * 24 * 7, // 7 days
      path: "/",
    })
    // ---------------------------------

    // 3. Send it back to the frontend
    return response
    
  } catch (error) {
    console.error("Sign-in Error:", error)
    return NextResponse.json({ message: "Internal server error" }, { status: 500 })
  }
}