"use client";

import { useEffect, useState } from "react";
import axios from "axios";
import { Users, FileText, CheckCircle, AlertTriangle, XCircle, Database, BrainCircuit, Activity } from "lucide-react";
import Link from "next/link";
import { API_URL } from "@/lib/api";

export default function OfficerDashboard() {
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await axios.get(`${API_URL}/api/officer/dashboard`);
        setStats(res.data);
      } catch (err) {
        console.error("Failed to fetch dashboard stats", err);
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
    
    // Poll every 10 seconds for real-time dashboard updates
    const interval = setInterval(fetchStats, 10000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return <div className="animate-pulse p-4">Loading dashboard data...</div>;

  return (
    <div className="space-y-8">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Command Center</h2>
          <p className="text-gray-500 mt-1">Live overview of land record processing queue.</p>
        </div>
        <div className="flex items-center gap-2 text-sm font-medium text-green-600 bg-green-50 px-3 py-1.5 rounded-full border border-green-200">
          <Activity className="w-4 h-4" />
          Live Updates Active
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard title="Total Received" value={stats?.total_received} icon={<FileText className="w-6 h-6 text-indigo-500" />} />
        <StatCard title="Pending Queue" value={stats?.pending} icon={<Users className="w-6 h-6 text-blue-500" />} />
        <StatCard title="Digitized (OCR)" value={stats?.digitized} icon={<BrainCircuit className="w-6 h-6 text-purple-500" />} />
        <StatCard title="Verified Records" value={stats?.verified} icon={<Database className="w-6 h-6 text-emerald-500" />} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 lg:col-span-2">
          <h3 className="text-lg font-bold text-gray-900 mb-4">Processing Pipeline</h3>
          <div className="flex justify-between items-center px-4 py-8 bg-slate-50 rounded-lg border border-slate-100">
            <PipelineStep label="Received" count={stats?.total_received} active={true} />
            <PipelineDivider />
            <PipelineStep label="Processing" count={stats?.processing} active={stats?.processing > 0} />
            <PipelineDivider />
            <PipelineStep label="Needs Review" count={stats?.needs_review} active={stats?.needs_review > 0} warning={true} />
            <PipelineDivider />
            <PipelineStep label="Verified" count={stats?.verified} active={stats?.verified > 0} success={true} />
          </div>
        </div>
        
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
          <h3 className="text-lg font-bold text-gray-900 mb-4">Attention Required</h3>
          <div className="space-y-4">
            <div className="flex items-center justify-between p-4 bg-orange-50 border border-orange-100 rounded-lg">
              <div className="flex items-center gap-3 text-orange-800 font-medium">
                <AlertTriangle className="w-5 h-5" />
                Low AI Confidence
              </div>
              <span className="text-xl font-bold text-orange-900">{stats?.low_confidence}</span>
            </div>
            <div className="flex items-center justify-between p-4 bg-red-50 border border-red-100 rounded-lg">
              <div className="flex items-center gap-3 text-red-800 font-medium">
                <XCircle className="w-5 h-5" />
                Rejected
              </div>
              <span className="text-xl font-bold text-red-900">{stats?.rejected}</span>
            </div>
            
            <Link href="/officer/submissions" className="block w-full text-center mt-4 px-4 py-2 bg-slate-900 text-white rounded-md text-sm font-medium hover:bg-slate-800 transition-colors">
              Open Queue
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({ title, value, icon }: { title: string, value: number, icon: React.ReactNode }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm relative overflow-hidden">
      <div className="absolute top-0 right-0 p-6 opacity-10 pointer-events-none">
        {icon}
      </div>
      <p className="text-sm font-semibold text-gray-500 uppercase tracking-wider">{title}</p>
      <p className="mt-2 text-4xl font-bold text-gray-900">{value}</p>
    </div>
  );
}

function PipelineStep({ label, count, active, warning, success }: any) {
  let color = "text-gray-400 bg-gray-100";
  if (active) color = "text-blue-600 bg-blue-100";
  if (warning && active) color = "text-orange-600 bg-orange-100";
  if (success && active) color = "text-emerald-600 bg-emerald-100";
  
  return (
    <div className="flex flex-col items-center">
      <div className={`w-12 h-12 rounded-full flex items-center justify-center font-bold text-lg mb-2 ${color}`}>
        {count}
      </div>
      <span className={`text-sm font-medium ${active ? 'text-slate-900' : 'text-slate-500'}`}>{label}</span>
    </div>
  );
}

function PipelineDivider() {
  return <div className="h-0.5 flex-1 bg-gray-200 mx-4"></div>;
}
