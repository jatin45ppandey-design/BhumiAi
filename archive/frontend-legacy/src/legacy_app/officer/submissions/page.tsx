"use client";

import { useEffect, useState } from "react";
import axios from "axios";
import Link from "next/link";
import { format } from "date-fns";
import { Search, Filter, Inbox } from "lucide-react";
import { API_URL } from "@/lib/api";

export default function IncomingSubmissions() {
  const [submissions, setSubmissions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchSubmissions = async () => {
      try {
        const res = await axios.get(`${API_URL}/api/officer/submissions`);
        setSubmissions(res.data);
      } catch (err) {
        console.error("Failed to fetch submissions", err);
      } finally {
        setLoading(false);
      }
    };
    fetchSubmissions();
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-end">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Incoming Submissions</h2>
          <p className="text-gray-500 mt-1">Review and process uploaded land documents.</p>
        </div>
        <div className="flex gap-3">
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input 
              type="text" 
              placeholder="Search..." 
              className="pl-9 pr-4 py-2 border border-gray-300 rounded-md text-sm focus:ring-slate-900 focus:border-slate-900 w-64"
            />
          </div>
          <button className="flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-md text-sm font-medium hover:bg-gray-50">
            <Filter className="w-4 h-4" /> Filter
          </button>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-500">Loading...</div>
        ) : submissions.length === 0 ? (
          <div className="p-16 text-center text-gray-500 flex flex-col items-center">
            <Inbox className="w-12 h-12 text-gray-300 mb-4" />
            <p className="text-lg font-medium text-gray-900">Queue is empty</p>
            <p>There are no pending submissions for review.</p>
          </div>
        ) : (
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50 border-b border-gray-200">
                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">ID</th>
                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Type & Location</th>
                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Submitted</th>
                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Status</th>
                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {submissions.map((sub: any) => (
                <tr key={sub.id} className="hover:bg-gray-50 transition-colors group">
                  <td className="px-6 py-4 text-sm font-bold text-slate-900">#{sub.id}</td>
                  <td className="px-6 py-4">
                    <div className="text-sm font-medium text-gray-900">{sub.document.document_type}</div>
                    <div className="text-xs text-gray-500">{sub.document.village}, {sub.document.district}</div>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">
                    {format(new Date(sub.submitted_at), "MMM d, yyyy")}
                    <div className="text-xs">{format(new Date(sub.submitted_at), "HH:mm")}</div>
                  </td>
                  <td className="px-6 py-4">
                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                      sub.status === 'SUBMITTED' ? 'bg-blue-100 text-blue-800' : 
                      sub.status === 'PROCESSING' ? 'bg-purple-100 text-purple-800' :
                      sub.status === 'NEEDS_REVIEW' ? 'bg-orange-100 text-orange-800' :
                      sub.status === 'VERIFIED' ? 'bg-green-100 text-green-800' :
                      'bg-gray-100 text-gray-800'
                    }`}>
                      {sub.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <Link 
                      href={`/officer/submissions/${sub.id}`}
                      className="inline-flex items-center px-4 py-2 bg-slate-900 text-white text-sm font-medium rounded-md hover:bg-slate-800 transition-colors shadow-sm"
                    >
                      Review
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
