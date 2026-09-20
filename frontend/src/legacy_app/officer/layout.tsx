import Link from "next/link";
import { LogOut, LayoutDashboard, Inbox, Database, FileClock, CheckCircle, ShieldCheck } from "lucide-react";

export default function OfficerLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <aside className="w-64 bg-slate-900 flex flex-col text-white">
        <div className="p-6">
          <h2 className="text-xl font-bold text-white tracking-tight">AI Land Records</h2>
          <p className="text-xs text-slate-400 mt-1 uppercase tracking-wider font-semibold">Officer Portal</p>
        </div>
        
        <nav className="flex-1 px-4 space-y-2 mt-4">
          <Link href="/officer" className="flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-md text-white bg-slate-800 hover:bg-slate-700 transition-colors">
            <LayoutDashboard className="w-5 h-5 text-blue-400" />
            Dashboard
          </Link>
          <Link href="/officer/submissions" className="flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-md text-slate-300 hover:bg-slate-800 hover:text-white transition-colors">
            <Inbox className="w-5 h-5 text-slate-400" />
            Incoming Submissions
          </Link>
          <Link href="/officer/records" className="flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-md text-slate-300 hover:bg-slate-800 hover:text-white transition-colors">
            <Database className="w-5 h-5 text-slate-400" />
            Verified Records
          </Link>
          <Link href="/officer/audit" className="flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-md text-slate-300 hover:bg-slate-800 hover:text-white transition-colors">
            <ShieldCheck className="w-5 h-5 text-slate-400" />
            Audit Trail
          </Link>
        </nav>
        
        <div className="p-4 border-t border-slate-800">
          <Link href="/login" className="flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-md text-red-400 hover:bg-red-900/30 transition-colors">
            <LogOut className="w-5 h-5" />
            Logout
          </Link>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto">
        <header className="bg-white border-b border-gray-200 h-16 flex items-center justify-between px-8 shadow-sm z-10 sticky top-0">
          <h1 className="text-lg font-semibold text-gray-900">Officer Workspace</h1>
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-slate-900 flex items-center justify-center text-white font-bold text-xs">
              OFF
            </div>
            <span className="text-sm font-semibold text-gray-800">Verification Officer</span>
          </div>
        </header>
        <div className="p-8 max-w-7xl mx-auto">
          {children}
        </div>
      </main>
    </div>
  );
}
