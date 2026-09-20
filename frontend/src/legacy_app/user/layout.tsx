import Link from "next/link";
import { LogOut, Home, Upload, FileText, Settings, User } from "lucide-react";

export default function UserLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-gray-200 flex flex-col">
        <div className="p-6">
          <h2 className="text-xl font-bold text-gray-900">Land Record AI</h2>
          <p className="text-xs text-gray-500 mt-1">Citizen Portal</p>
        </div>
        
        <nav className="flex-1 px-4 space-y-1">
          <Link href="/user" className="flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-md text-gray-900 bg-gray-100 hover:bg-gray-200 transition-colors">
            <Home className="w-5 h-5 text-gray-500" />
            Dashboard
          </Link>
          <Link href="/user/upload" className="flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-md text-gray-600 hover:bg-gray-50 hover:text-gray-900 transition-colors">
            <Upload className="w-5 h-5 text-gray-400" />
            Upload Document
          </Link>
          <Link href="/user/submissions" className="flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-md text-gray-600 hover:bg-gray-50 hover:text-gray-900 transition-colors">
            <FileText className="w-5 h-5 text-gray-400" />
            My Submissions
          </Link>
          <Link href="/user/advanced" className="flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-md text-gray-600 hover:bg-gray-50 hover:text-gray-900 transition-colors">
            <Settings className="w-5 h-5 text-gray-400" />
            Advanced Features
          </Link>
        </nav>
        
        <div className="p-4 border-t border-gray-200">
          <Link href="/login" className="flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-md text-red-600 hover:bg-red-50 transition-colors">
            <LogOut className="w-5 h-5" />
            Logout
          </Link>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto">
        <header className="bg-white border-b border-gray-200 h-16 flex items-center justify-between px-8">
          <h1 className="text-lg font-semibold text-gray-900">Citizen Dashboard</h1>
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center text-blue-700 font-bold">
              <User className="w-4 h-4" />
            </div>
            <span className="text-sm font-medium text-gray-700">Citizen Account</span>
          </div>
        </header>
        <div className="p-8 max-w-7xl mx-auto">
          {children}
        </div>
      </main>
    </div>
  );
}
