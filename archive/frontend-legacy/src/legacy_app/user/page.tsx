"use client";

import { useEffect, useState } from "react";
import axios from "axios";
import { FileText, Clock, CheckCircle, AlertTriangle, XCircle } from "lucide-react";
import Link from "next/link";
import { API_URL } from "@/lib/api";

interface DashboardStats {
  total_submitted: number;
  pending_review: number;
  verified: number;
  needs_review: number;
  rejected: number;
}

export default function UserDashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const user = JSON.parse(localStorage.getItem("user") || "{}");
        if (user.id) {
          const res = await axios.get(`${API_URL}/api/user/dashboard?user_id=${user.id}`);
          setStats(res.data);
        }
      } catch (err) {
        console.error("Failed to fetch dashboard stats", err);
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
  }, []);

  if (loading) return <div className="animate-pulse flex space-x-4"><div className="flex-1 space-y-6 py-1"><div className="h-2 bg-slate-200 rounded"></div><div className="space-y-3"><div className="grid grid-cols-3 gap-4"><div className="h-2 bg-slate-200 rounded col-span-2"></div><div className="h-2 bg-slate-200 rounded col-span-1"></div></div><div className="h-2 bg-slate-200 rounded"></div></div></div></div>;

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-gray-900">Welcome Back</h2>
        <p className="text-gray-500 mt-1">Here is an overview of your submitted land records.</p>
      </div>

      {stats?.total_submitted === 0 ? (
        <div className="bg-white rounded-xl border border-dashed border-gray-300 p-12 text-center flex flex-col items-center justify-center">
          <div className="w-16 h-16 bg-blue-50 text-blue-600 rounded-full flex items-center justify-center mb-4">
            <FileText className="w-8 h-8" />
          </div>
          <h3 className="text-xl font-semibold text-gray-900">No documents submitted yet.</h3>
          <p className="text-gray-500 mt-2 max-w-md">Upload your first land record (Khatauni, Khasra, etc.) for AI digitization and officer verification.</p>
          <Link href="/user/upload" className="mt-6 inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700">
            Upload your first land record
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <StatCard title="Total Submitted" value={stats?.total_submitted} icon={<FileText className="w-6 h-6 text-gray-500" />} />
          <StatCard title="Pending Review" value={stats?.pending_review} icon={<Clock className="w-6 h-6 text-yellow-500" />} />
          <StatCard title="Verified" value={stats?.verified} icon={<CheckCircle className="w-6 h-6 text-green-500" />} />
          <StatCard title="Needs Review" value={stats?.needs_review} icon={<AlertTriangle className="w-6 h-6 text-orange-500" />} />
        </div>
      )}

      {stats?.total_submitted !== 0 && (
        <div className="mt-8 bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="p-6 border-b border-gray-200 flex justify-between items-center">
            <h3 className="text-lg font-medium text-gray-900">Recent Activity</h3>
            <Link href="/user/submissions" className="text-sm text-blue-600 hover:text-blue-800 font-medium">View all</Link>
          </div>
          <div className="p-6 text-center text-gray-500">
            Click "View all" to see your submissions.
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({ title, value, icon }: { title: string, value: number | undefined, icon: React.ReactNode }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500 truncate">{title}</p>
          <p className="mt-1 text-3xl font-semibold text-gray-900">{value || 0}</p>
        </div>
        <div className="p-3 bg-gray-50 rounded-lg">
          {icon}
        </div>
      </div>
    </div>
  );
}
