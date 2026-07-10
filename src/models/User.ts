import mongoose, { Schema, model, models } from "mongoose"
// Inside src/models/User.ts
const UserSchema = new Schema(
  {
    email: {
      type: String,
      unique: true,
      required: [true, "Email is required"],
    },
    password: {
      type: String,
      required: [true, "Password is required"],
      select: false, 
    },
    companyName: { // <--- Updated to match!
      type: String,
      required: [true, "Company name is required"],
    },
    // Inside src/models/User.ts, add these below your existing fields
    resetPasswordOtp: {
      type: String,
      default: undefined,
    },
    resetPasswordExpires: {
      type: Date,
      default: undefined,
    },
    isVerified: {
      type: Boolean,
      default: false,
    },
    verificationOtp: {
      type: String,
      default: undefined,
    },
    verificationExpires: {
      type: Date,
      default: undefined,
    },
    role: {
      type: String,
      default: "admin", 
    },
  },
  
  {
    timestamps: true,
  }
)

// Check if the model exists before compiling it to prevent OverwriteModelError
const User = models.User || model("User", UserSchema)

export default User