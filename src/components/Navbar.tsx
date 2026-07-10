"use client"

import React from "react"
import Link from "next/link"
import Image from "next/image"
import { useTheme } from "next-themes"
import { Moon, Sun } from "lucide-react"

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuLabel, 
  DropdownMenuSeparator, 
  DropdownMenuTrigger,
  DropdownMenuGroup 
} from "@/components/ui/dropdown-menu"

export default function Navbar() {
  const { theme, setTheme } = useTheme()

  return (
    <nav className="border-b bg-white/50 backdrop-blur-xl px-6 py-3 flex items-center justify-between shadow-sm dark:bg-slate-950/50 dark:border-slate-800 sticky top-0 z-50">
      <div className="flex items-center gap-6">
        
        {/* --- UPDATED LOGO SECTION START --- */}


<Link href="/dashboard" className="flex items-center gap-3">
  <Image
    src="/logo.jpeg"
    alt="Call-E Logo"
    width={36}
    height={36}
    priority
    className="rounded-lg"
  />

  <span className="text-xl font-bold tracking-tight text-blue-600 dark:text-blue-400">
    Call-E Engine
  </span>
</Link>
        {/* --- UPDATED LOGO SECTION END --- */}

        <div className="hidden md:flex gap-4 text-sm font-medium text-slate-600 dark:text-slate-300">
          <Link href="/dashboard" className="hover:text-black dark:hover:text-white transition-colors">Overview</Link>
          <Link href="/dashboard/logs" className="hover:text-black dark:hover:text-white transition-colors">Call Logs</Link>
          <Link href="/dashboard/settings" className="hover:text-black dark:hover:text-white transition-colors">Agent Settings</Link>
        </div>
      </div>
      
      <div className="flex items-center gap-2">
        {/* Dark Mode Toggle Button */}
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          className="rounded-full w-9 h-9 mr-2"
        >
          <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
          <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
          <span className="sr-only">Toggle theme</span>
        </Button>

        {/* User Profile Dropdown */}
        <DropdownMenu>
          <DropdownMenuTrigger className="focus:outline-none">
            <Avatar className="h-8 w-8 cursor-pointer ring-2 ring-transparent hover:ring-blue-100 dark:hover:ring-slate-800 transition-all">
              <AvatarImage src="" />
              <AvatarFallback className="bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-200">AC</AvatarFallback>
            </Avatar>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            
            {/* Wrap the top section in a Group */}
            <DropdownMenuGroup>
              <DropdownMenuLabel>My Enterprise</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem className="cursor-pointer">Billing & Usage</DropdownMenuItem>
              <DropdownMenuItem className="cursor-pointer">Team Members</DropdownMenuItem>
            </DropdownMenuGroup>
            
            <DropdownMenuSeparator />
            
            <DropdownMenuItem className="text-red-600 focus:bg-red-50 focus:text-red-700 dark:focus:bg-red-950 dark:focus:text-red-400 cursor-pointer">
              Log out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </nav>
  )
}