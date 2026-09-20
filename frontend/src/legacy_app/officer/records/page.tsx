"use client";

import { useEffect, useState } from "react";
import axios from "axios";
import { format } from "date-fns";
import { Search, Database, FileText } from "lucide-react";
import Link from "next/link";
import { API_URL } from "@/lib/api";

export default function VerifiedRecords() {
  const [records, setRecords] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  const fetchRecords = async (query = "") => {
    setLoading(true);
    try {
      const res = await axios.get(`${API_URL}/api/verified-records${query ? `?search=${query}` : ''}`);
      setRecords(res.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRecords();
  }, []);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    fetchRecords(search);
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-end">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Verified Records Repository</h2>
          <p className="text-gray-500 mt-1">Search and view finalized permanent land records.</p>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
        <form onSubmit={handleSearch} className="flex gap-4">
          <div className="relative flex-1">
            <Search className="w-5 h-5 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input 
              type="text" 
              placeholder="Search by Record ID, Owner, Khasra, Village..." 
              className="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <button type="submit" className="px-6 py-3 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700">
            Search
          </button>
        </form>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-500">Searching repository...</div>
        ) : records.length === 0 ? (
          <div className="p-16 text-center text-gray-500 flex flex-col items-center">
            <Database className="w-12 h-12 text-gray-300 mb-4" />
            <p className="text-lg font-medium text-gray-900">No records found</p>
            <p>Adjust your search filters or check back later.</p>
          </div>
        ) : (
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50 border-b border-gray-200">
                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Record ID</th>
                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Owner</th>
                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Khasra / Khata</th>
                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Location</th>
                <th className="px-6 py-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">Verified Date</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {records.map((record: any) => (
                <tr key={record.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-4">
                    <Link href={`/officer/records/${record.id}`} className="text-sm font-bold text-blue-600 hover:underline">
                      {record.record_id}
                    </Link>
                  </td>
                  <td className="px-6 py-4 text-sm font-medium text-gray-900">{record.owner_name}</td>
                  <td className="px-6 py-4 text-sm text-gray-500">{record.khasra_number} / {record.khata_number}</td>
                  <td className="px-6 py-4 text-sm text-gray-500">{record.village}, {record.district}</td>
                  <td className="px-6 py-4 text-sm text-gray-500">
                    {format(new Date(record.verified_at), "MMM d, yyyy")}
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
