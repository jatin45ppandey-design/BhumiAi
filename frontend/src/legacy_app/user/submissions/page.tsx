"use client";

import { useEffect, useState } from "react";
import axios from "axios";
import { Clock, CheckCircle, AlertTriangle, XCircle, FileText } from "lucide-react";
import { format } from "date-fns";
import { API_URL } from "@/lib/api";

export default function MySubmissions() {
  const [submissions, setSubmissions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchSubmissions = async () => {
      try {
        const user = JSON.parse(localStorage.getItem("user") || "{}");
        if (user.id) {
          const res = await axios.get(`${API_URL}/api/user/submissions?user_id=${user.id}`);
          setSubmissions(res.data);
        }
      } catch (err) {
        console.error("Failed to fetch submissions", err);
      } finally {
        setLoading(false);
      }
    };
    fetchSubmissions();
  }, []);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "SUBMITTED":
        return <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800"><Clock className="w-3.5 h-3.5" /> Submitted</span>;
      case "PROCESSING":
        return <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-purple-100 text-purple-800"><Clock className="w-3.5 h-3.5" /> Under Processing</span>;
      case "NEEDS_REVIEW":
        return <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-orange-100 text-orange-800"><AlertTriangle className="w-3.5 h-3.5" /> Needs Review</span>;
      case "VERIFIED":
        return <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800"><CheckCircle className="w-3.5 h-3.5" /> Verified</span>;
      case "REJECTED":
        return <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-100 text-red-800"><XCircle className="w-3.5 h-3.5" /> Rejected</span>;
      default:
        return <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-800">{status}</span>;
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-gray-900">My Submissions</h2>
        <p className="text-gray-500 mt-1">Track the status of your uploaded land records.</p>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-500">Loading...</div>
        ) : submissions.length === 0 ? (
          <div className="p-12 text-center text-gray-500 flex flex-col items-center">
            <FileText className="w-12 h-12 text-gray-300 mb-4" />
            <p>You haven't submitted any documents yet.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="px-6 py-4 text-sm font-semibold text-gray-900">Submission ID</th>
                  <th className="px-6 py-4 text-sm font-semibold text-gray-900">Document Type</th>
                  <th className="px-6 py-4 text-sm font-semibold text-gray-900">Village</th>
                  <th className="px-6 py-4 text-sm font-semibold text-gray-900">Submitted Date</th>
                  <th className="px-6 py-4 text-sm font-semibold text-gray-900">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {submissions.map((sub: any) => (
                  <tr key={sub.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-6 py-4 text-sm font-medium text-gray-900">SUB-{sub.id.toString().padStart(4, '0')}</td>
                    <td className="px-6 py-4 text-sm text-gray-500">{sub.document.document_type}</td>
                    <td className="px-6 py-4 text-sm text-gray-500">{sub.document.village}</td>
                    <td className="px-6 py-4 text-sm text-gray-500">
                      {format(new Date(sub.submitted_at), "MMM d, yyyy HH:mm")}
                    </td>
                    <td className="px-6 py-4">
                      {getStatusBadge(sub.status)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
