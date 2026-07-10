import * as z from "zod"

export const loginSchema = z.object({
  email: z.string().email({ message: "Please enter a valid business email address." }),
  password: z.string().min(8, { message: "Password must be at least 8 characters long." }),
})

export const signupSchema = z.object({
  companyName: z.string().min(2, { message: "Company name must be at least 2 characters." }),
  email: z.string().email({ message: "Please enter a valid business email address." }),
  password: z.string().min(8, { message: "Password must be at least 8 characters long." }),
  confirmPassword: z.string(),
}).refine((data) => data.password === data.confirmPassword, {
  message: "Passwords do not match.",
  path: ["confirmPassword"],
})

export const signinSchema = z.object({
  email: z.string().email({ message: "Invalid email address" }),
  password: z.string().min(1, { message: "Password is required" }),
})

export const forgotPasswordSchema = z.object({
  email: z.string().email({ message: "Please enter a valid business email address." }),
})

export const resetPasswordSchema = z.object({
  otp: z.string().length(6, { message: "OTP must be exactly 6 digits." }),
  password: z.string().min(8, { message: "Password must be at least 8 characters long." }),
  confirmPassword: z.string(),
}).refine((data) => data.password === data.confirmPassword, {
  message: "Passwords do not match.",
  path: ["confirmPassword"],
})