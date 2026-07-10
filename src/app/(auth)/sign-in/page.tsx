"use client"

import React, { useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import * as z from "zod"

// Make sure this matches your schema name!
import { signinSchema } from "@/lib/validations/auth"

import { Button } from "@/components/ui/button"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"

export default function SignInPage() {
  const router = useRouter()
  const [error, setError] = useState<string | null>(null)

  const form = useForm<z.infer<typeof signinSchema>>({
    resolver: zodResolver(signinSchema),
    defaultValues: {
      email: "",
      password: "",
    },
  })

  async function onSubmit(data: z.infer<typeof signinSchema>) {
    try {
      setError(null)
      console.log("Attempting to sign in...")
      
      const response = await fetch("/api/auth/sign-in", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email: data.email,
          password: data.password,
        }),
      })

      const result = await response.json()

      if (!response.ok) {
        // If the password or email is wrong, show the error on the screen
        setError(result.message)
        return
      }

      console.log("Login successful! ID:", result.userId)
      // Glide the user into the dashboard!
      router.push("/dashboard")
      
    } catch (error) {
      console.error("Network Error:", error)
      setError("Something went wrong connecting to the server.")
    }
  }

 return (
    // 1. Changed the outer background from slate-50 to a deep Burgundy
    <div className="flex min-h-screen items-center justify-center bg-[#800020] p-4">
      
      {/* 2. Kept the center card completely White */}
      <div className="w-full max-w-md space-y-8 rounded-2xl bg-white p-8 shadow-2xl">
        <div className="text-center">
          <h2 className="text-3xl font-bold tracking-tight text-slate-900">
            Welcome back
          </h2>
          <p className="mt-2 text-sm text-slate-600">
            Sign in to your Call-E account
          </p>
        </div>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            
            {error && (
              <div className="rounded-md bg-red-50 p-3 text-sm text-red-500">
                {error}
              </div>
            )}

            <FormField
              control={form.control}
              name="email"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="text-slate-700">Work Email</FormLabel>
                  <FormControl>
                    <Input placeholder="admin@company.com" type="email" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="password"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="text-slate-700">Password</FormLabel>
                  <FormControl>
                    <Input placeholder="••••••••" type="password" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* 3. Changed the Button from Blue to Burgundy */}
            <Button type="submit" className="w-full bg-[#800020] hover:bg-[#5e0b17] text-white">
              Sign In
            </Button>
          </form>
        </Form>

        <div className="text-center text-sm text-slate-600">
          Don't have an account?{" "}
          {/* 4. Changed the Link text from Blue to Burgundy */}
          <Link href="/sign-up" className="font-semibold text-[#800020] hover:text-[#5e0b17]">
            Sign up
          </Link>
        </div>
      </div>
    </div>
  )
}