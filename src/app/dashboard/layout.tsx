import React from "react"
import Link from "next/link"

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="flex min-h-screen bg-slate-50">
      
      {/* The Sidebar - Deep Burgundy */}
      <aside className="w-64 bg-[#800020] text-white flex flex-col shadow-xl z-10">
        <div className="flex h-16 items-center px-6 text-2xl font-bold border-b border-[#5e0b17]">
          Call-E
        </div>
        <nav className="flex-1 p-4 space-y-2 text-sm font-medium">
          <Link href="/dashboard" className="block px-4 py-3 rounded-md bg-[#5e0b17] text-white">
            Dashboard
          </Link>
          <Link href="/dashboard/api-settings" className="block px-4 py-3 rounded-md text-slate-300 hover:bg-[#5e0b17] hover:text-white transition-colors">
            API Settings
          </Link>
          <Link href="/dashboard/billing" className="block px-4 py-3 rounded-md text-slate-300 hover:bg-[#5e0b17] hover:text-white transition-colors">
            Payment and Bills
          </Link>
        </nav>
      </aside>

      {/* The Main Content Area */}
      <main className="flex-1 flex flex-col min-w-0">
        
        {/* Top Navbar - Clean White */}
        <header className="h-16 bg-white border-b border-slate-200 flex items-center justify-between px-8 shadow-sm">
          <h1 className="text-lg font-semibold text-slate-800">Workspace</h1>
          <div className="flex items-center space-x-4">
            <div className="h-8 w-8 rounded-full bg-[#800020] text-white flex items-center justify-center font-bold">
              C
            </div>
          </div>
        </header>
        
        {/* The White Workspace where all your children pages render */}
        <div className="p-8 flex-1 overflow-auto">
          {children}
        </div>
      </main>
    </div>
  )
}