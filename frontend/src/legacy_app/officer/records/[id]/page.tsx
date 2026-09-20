"use client";

import { useEffect, useState, use } from "react";
import axios from "axios";
import { format } from "date-fns";
import { ArrowLeft, Database, Activity, CheckCircle, FileText, Download } from "lucide-react";
import Link from "next/link";
import { API_URL } from "@/lib/api";

export default function RecordDetail({ params }: { params: Promise<{ id: string }> }) {
  const resolvedParams = use(params);
  const id = resolvedParams.id;
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchDetail = async () => {
      try {
        const res = await axios.get(`${API_URL}/api/verified-records/${id}`);
        setData(res.data);
      } catch (err) {
        console.error("Failed to load record details", err);
      } finally {
        setLoading(false);
      }
    };
    fetchDetail();
  }, [id]);

  if (loading || !data) return <div className="p-8 animate-pulse text-gray-500 font-medium">Loading record detail...</div>;

  const { record, document, ocr, audit_trail } = data;

  return (
    <div className="space-y-6 pb-10">
      <div className="flex items-center gap-4 border-b border-gray-200 pb-4">
        <Link href="/officer/records" className="text-gray-500 hover:text-gray-900 transition-colors">
          <ArrowLeft className="w-6 h-6" />
        </Link>
        <div>
          <h2 className="text-2xl font-bold text-gray-900 flex items-center gap-3">
            <Database className="w-6 h-6 text-blue-600" /> 
            {record.record_id}
          </h2>
          <p className="text-gray-500 text-sm mt-1">Immutable Verified Land Record</p>
        </div>
        <div className="ml-auto flex gap-3">
          <button className="px-4 py-2 border border-gray-300 bg-white text-gray-700 font-medium rounded-lg shadow-sm hover:bg-gray-50 transition-colors flex items-center gap-2">
            <Download className="w-4 h-4" /> Export PDF
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          {/* Permanent Record Card */}
          <div className="bg-white rounded-xl shadow-sm border border-emerald-200 overflow-hidden">
            <div className="bg-emerald-50 px-6 py-4 border-b border-emerald-200 flex justify-between items-center">
              <h3 className="font-bold text-emerald-900 flex items-center gap-2">
                <CheckCircle className="w-5 h-5 text-emerald-600" />
                Finalized Property Details
              </h3>
              <span className="text-xs font-semibold text-emerald-700 bg-emerald-100 px-3 py-1 rounded-full">
                VERIFIED
              </span>
            </div>
            <div className="p-6 grid grid-cols-2 gap-y-6 gap-x-4">
              <DetailItem label="Owner Name" value={record.owner_name} />
              <DetailItem label="Father/Guardian Name" value={record.father_guardian_name || "N/A"} />
              <DetailItem label="Khasra Number" value={record.khasra_number} />
              <DetailItem label="Khata Number" value={record.khata_number} />
              <DetailItem label="Area" value={record.area} />
              <DetailItem label="Village" value={record.village} />
              <DetailItem label="Tehsil" value={record.tehsil} />
              <DetailItem label="District" value={record.district} />
              <DetailItem label="State" value={record.state} />
              <DetailItem label="Verified At" value={format(new Date(record.verified_at), "PPP p")} className="col-span-2" />
            </div>
          </div>

          {/* AI Extraction Overview */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200">
              <h3 className="font-bold text-gray-900 flex items-center gap-2">
                <FileText className="w-5 h-5 text-gray-500" />
                Original Document & AI Text
              </h3>
            </div>
            <div className="p-6">
              <div className="flex flex-col gap-4">
                <div className="text-sm">
                  <span className="text-gray-500 font-medium">OCR Engine Used:</span> <span className="font-semibold text-gray-900">{ocr.engine}</span>
                </div>
                <div>
                  <span className="text-sm text-gray-500 font-medium block mb-2">Raw Extracted Text:</span>
                  <div className="bg-gray-50 border border-gray-200 rounded p-4 text-xs font-mono text-gray-700 max-h-48 overflow-y-auto whitespace-pre-wrap">
                    {ocr.raw_text || "No text extracted."}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Audit Trail Sidebar */}
        <div className="lg:col-span-1">
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden sticky top-6">
            <div className="px-6 py-4 border-b border-gray-200 bg-gray-50">
              <h3 className="font-bold text-gray-900 flex items-center gap-2">
                <Activity className="w-5 h-5 text-blue-600" />
                Immutable Audit Trail
              </h3>
            </div>
            <div className="p-6">
              <div className="space-y-6 relative before:absolute before:inset-0 before:ml-5 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-slate-300 before:to-transparent">
                {audit_trail.map((log: any, idx: number) => (
                  <div key={idx} className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
                    <div className="flex items-center justify-center w-10 h-10 rounded-full border border-white bg-blue-100 text-blue-600 shadow shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2">
                      <CheckCircle className="w-4 h-4" />
                    </div>
                    <div className="w-[calc(100%-4rem)] md:w-[calc(50%-2.5rem)] bg-white p-4 rounded border border-gray-200 shadow-sm">
                      <div className="flex items-center justify-between space-x-2 mb-1">
                        <div className="font-bold text-slate-900 text-sm">{log.action}</div>
                        <time className="text-xs font-medium text-blue-600">{format(new Date(log.timestamp), "MMM d, HH:mm")}</time>
                      </div>
                      <div className="text-xs text-slate-500">User ID: {log.user_id || "System"}</div>
                      {log.metadata && <div className="text-xs text-slate-400 mt-1 italic">{log.metadata}</div>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function DetailItem({ label, value, className = "" }: { label: string, value: string, className?: string }) {
  return (
    <div className={className}>
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">{label}</p>
      <p className="text-sm font-medium text-gray-900">{value}</p>
    </div>
  );
}
