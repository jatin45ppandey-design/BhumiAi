"use client";

import { useEffect, useState, use } from "react";
import axios from "axios";
import { useRouter } from "next/navigation";
import { Check, X, AlertTriangle, ChevronRight, Edit2, CheckCircle2, Image as ImageIcon, Save, ArrowLeft, FileText, BrainCircuit, Database } from "lucide-react";
import { API_URL } from "@/lib/api";
import Link from "next/link";
import clsx from "clsx";

export default function DocumentVerification({ params }: { params: Promise<{ id: string }> }) {
  const router = useRouter();
  const resolvedParams = use(params);
  const id = resolvedParams.id;
  
  const [submission, setSubmission] = useState<any>(null);
  const [fields, setFields] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [processingState, setProcessingState] = useState(0); // 0: uploaded, 1: preprocessed, 2: ocr, 3: extracted
  const [processedImage, setProcessedImage] = useState<string | null>(null);
  const [ocrId, setOcrId] = useState<number | null>(null);
  const [editingField, setEditingField] = useState<number | null>(null);
  const [editValue, setEditValue] = useState("");
  const [showOriginal, setShowOriginal] = useState(true);

  useEffect(() => {
    const fetchSub = async () => {
      try {
        const res = await axios.get(`${API_URL}/api/officer/submissions/${id}`);
        setSubmission(res.data);
        
        // Check if OCR already exists
        const fieldRes = await axios.get(`${API_URL}/api/officer/documents/${res.data.document_id}/fields`);
        if (fieldRes.data && fieldRes.data.length > 0) {
          setFields(fieldRes.data);
          setProcessingState(3); // Already processed
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchSub();
  }, [id]);

  const runPipeline = async () => {
    if (!submission) return;
    const docId = submission.document_id;
    
    try {
      // 1. Preprocess
      setProcessingState(1);
      const preRes = await axios.post(`${API_URL}/api/officer/documents/${docId}/preprocess`);
      setProcessedImage(preRes.data.processed_file_path);
      
      // 2. OCR
      setProcessingState(2);
      const ocrRes = await axios.post(`${API_URL}/api/officer/documents/${docId}/ocr?processed_path=${encodeURIComponent(preRes.data.processed_file_path)}`);
      setOcrId(ocrRes.data.ocr_id);
      
      // 3. Extract Fields
      setProcessingState(3);
      await axios.post(`${API_URL}/api/officer/documents/${docId}/extract?ocr_id=${ocrRes.data.ocr_id}`);
      
      // Fetch fields
      const fieldRes = await axios.get(`${API_URL}/api/officer/documents/${docId}/fields`);
      setFields(fieldRes.data);
      
    } catch (err) {
      console.error("Pipeline failed", err);
      alert("Processing pipeline failed.");
      setProcessingState(0);
    }
  };

  const saveFieldEdit = async (fieldId: number) => {
    if (!submission) return;
    try {
      const user = JSON.parse(localStorage.getItem("user") || "{}");
      await axios.patch(`${API_URL}/api/officer/documents/${submission.document_id}/fields/${fieldId}?officer_id=${user.id}`, {
        officer_value: editValue
      });
      
      // Update local state
      setFields(fields.map(f => f.id === fieldId ? { ...f, officer_value: editValue, edited: true } : f));
      setEditingField(null);
    } catch (err) {
      console.error(err);
      alert("Failed to save edit.");
    }
  };

  const handleAction = async (action: string) => {
    if (!submission) return;
    try {
      const user = JSON.parse(localStorage.getItem("user") || "{}");
      await axios.post(`${API_URL}/api/officer/documents/${submission.document_id}/${action}?officer_id=${user.id}`);
      router.push("/officer/submissions");
    } catch (err) {
      console.error(err);
      alert(`Action ${action} failed.`);
    }
  };

  if (loading || !submission) return <div className="p-8">Loading verification interface...</div>;

  return (
    <div className="h-full flex flex-col bg-gray-50 -mx-8 -mt-8 -mb-8 overflow-hidden">
      {/* Top Bar */}
      <div className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-4">
          <Link href="/officer/submissions" className="text-gray-500 hover:text-gray-900">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold text-gray-900">Verification: SUB-{submission.id}</h1>
              <span className="px-2 py-0.5 rounded text-xs font-semibold bg-purple-100 text-purple-800 uppercase tracking-wider">
                {submission.status}
              </span>
            </div>
            <p className="text-sm text-gray-500">{submission.document.document_type} | {submission.document.village}, {submission.document.district}</p>
          </div>
        </div>

        {processingState === 3 && (
          <div className="flex gap-3">
            <button onClick={() => handleAction('reject')} className="px-4 py-2 border border-red-200 text-red-600 bg-red-50 hover:bg-red-100 font-medium rounded-md text-sm transition-colors flex items-center gap-2">
              <X className="w-4 h-4" /> Reject
            </button>
            <button onClick={() => handleAction('mark-review')} className="px-4 py-2 border border-orange-200 text-orange-600 bg-orange-50 hover:bg-orange-100 font-medium rounded-md text-sm transition-colors flex items-center gap-2">
              <AlertTriangle className="w-4 h-4" /> Needs Review
            </button>
            <button onClick={() => handleAction('approve')} className="px-6 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded-md text-sm transition-colors shadow-sm flex items-center gap-2">
              <Check className="w-4 h-4" /> Verify & Approve
            </button>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-hidden flex">
        {/* Left Panel: Document View */}
        <div className="w-1/2 border-r border-gray-200 bg-slate-100 flex flex-col">
          <div className="p-3 bg-white border-b border-gray-200 flex justify-between items-center shrink-0">
            <h3 className="font-semibold text-gray-700 flex items-center gap-2">
              <ImageIcon className="w-4 h-4" /> Document Viewer
            </h3>
            <div className="flex bg-gray-100 p-1 rounded-md">
              <button 
                onClick={() => setShowOriginal(true)} 
                className={clsx("px-3 py-1 text-xs font-medium rounded", showOriginal ? "bg-white shadow-sm text-gray-900" : "text-gray-500 hover:text-gray-900")}
              >
                Original
              </button>
              <button 
                onClick={() => setShowOriginal(false)} 
                disabled={!processedImage}
                className={clsx("px-3 py-1 text-xs font-medium rounded disabled:opacity-50", !showOriginal ? "bg-white shadow-sm text-gray-900" : "text-gray-500 hover:text-gray-900")}
              >
                Enhanced
              </button>
            </div>
          </div>
          <div className="flex-1 overflow-auto p-4 flex items-center justify-center">
            {/* Mock Image Display */}
            <div className="w-full max-w-lg aspect-[3/4] bg-white shadow-lg border border-gray-300 rounded flex flex-col items-center justify-center text-gray-400 relative overflow-hidden">
              <img 
                src={`${API_URL}/${showOriginal ? submission.document.file_path.replace(/\\/g, '/') : (processedImage || submission.document.file_path).replace(/\\/g, '/')}`} 

                alt="Document" 
                className="w-full h-full object-contain"
                onError={(e) => {
                  (e.target as HTMLImageElement).style.display = 'none';
                  (e.target as HTMLImageElement).nextElementSibling?.classList.remove('hidden');
                }}
              />
              <div className="hidden absolute inset-0 flex-col items-center justify-center bg-gray-100">
                <FileText className="w-16 h-16 text-gray-300 mb-4" />
                <p className="text-gray-500">Document Image not found in local dir</p>
                <p className="text-xs text-gray-400 mt-2">{showOriginal ? "Original" : "Preprocessed"}</p>
              </div>
            </div>
          </div>
        </div>

        {/* Right Panel: Extraction & Verification */}
        <div className="w-1/2 bg-white flex flex-col">
          {processingState < 3 ? (
            <div className="flex-1 flex flex-col items-center justify-center p-12 text-center">
              <div className="w-20 h-20 bg-blue-50 text-blue-600 rounded-full flex items-center justify-center mb-6">
                <BrainCircuit className="w-10 h-10" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 mb-2">AI Extraction Pipeline</h2>
              <p className="text-gray-500 max-w-md mx-auto mb-8">
                Run the document through our AI pipeline to deskew, denoise, perform OCR, and structure the land record fields.
              </p>
              
              <div className="w-full max-w-xs space-y-4 mb-8 text-left">
                <PipelineProgress step={1} current={processingState} label="Image Preprocessing (OpenCV)" />
                <PipelineProgress step={2} current={processingState} label="OCR Engine (PaddleOCR)" />
                <PipelineProgress step={3} current={processingState} label="Structured Field Extraction" />
              </div>

              <button 
                onClick={runPipeline}
                disabled={processingState > 0}
                className="bg-blue-600 hover:bg-blue-700 text-white px-8 py-3 rounded-lg font-bold shadow-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {processingState > 0 ? "Processing..." : "Run AI Extraction"}
                {processingState === 0 && <ChevronRight className="w-5 h-5" />}
              </button>
            </div>
          ) : (
            <div className="flex-1 overflow-auto flex flex-col">
              <div className="p-4 bg-slate-900 text-white flex justify-between items-center shrink-0">
                <h3 className="font-semibold flex items-center gap-2">
                  <Database className="w-4 h-4 text-blue-400" /> Structured Digital Record
                </h3>
                <span className="text-xs text-slate-400">Review AI extracted fields against original</span>
              </div>
              
              <div className="p-6 space-y-4 flex-1">
                {fields.map(field => {
                  const confColor = field.ai_confidence >= 0.9 ? "text-emerald-600 bg-emerald-50 border-emerald-200" : 
                                    field.ai_confidence >= 0.7 ? "text-yellow-600 bg-yellow-50 border-yellow-200" : 
                                    "text-red-600 bg-red-50 border-red-200";
                  
                  const isEditing = editingField === field.id;
                  const displayValue = field.edited ? field.officer_value : field.ai_value;

                  return (
                    <div key={field.id} className={clsx("border rounded-lg p-4 transition-all", editingField === field.id ? "border-blue-500 ring-1 ring-blue-500 shadow-md bg-blue-50/10" : field.edited ? "border-blue-200 bg-blue-50/30" : "border-gray-200 hover:border-gray-300")}>
                      <div className="flex justify-between items-start mb-2">
                        <label className="text-xs font-bold text-gray-500 uppercase tracking-wider">{field.field_name.replace(/_/g, ' ')}</label>
                        {!field.edited && field.ai_confidence > 0 && (
                          <div className={clsx("px-2 py-0.5 rounded text-xs font-semibold border", confColor)}>
                            {Math.round(field.ai_confidence * 100)}% Conf.
                          </div>
                        )}
                        {field.edited && (
                          <div className="px-2 py-0.5 rounded text-xs font-semibold border text-blue-700 bg-blue-50 border-blue-200 flex items-center gap-1">
                            <CheckCircle2 className="w-3 h-3" /> Edited
                          </div>
                        )}
                      </div>

                      {isEditing ? (
                        <div className="flex gap-2 mt-2">
                          <input 
                            type="text" 
                            className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                            value={editValue}
                            onChange={(e) => setEditValue(e.target.value)}
                            autoFocus
                          />
                          <button onClick={() => saveFieldEdit(field.id)} className="p-2 bg-blue-600 text-white rounded-md hover:bg-blue-700">
                            <Save className="w-4 h-4" />
                          </button>
                          <button onClick={() => setEditingField(null)} className="p-2 bg-white border border-gray-300 text-gray-600 rounded-md hover:bg-gray-50">
                            <X className="w-4 h-4" />
                          </button>
                        </div>
                      ) : (
                        <div className="flex justify-between items-center group">
                          <div className="font-medium text-gray-900 text-lg">
                            {displayValue || <span className="text-gray-400 italic">Not extracted</span>}
                          </div>
                          <button 
                            onClick={() => {
                              setEditingField(field.id);
                              setEditValue(displayValue || "");
                            }}
                            className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded opacity-0 group-hover:opacity-100 transition-all"
                            title="Edit value"
                          >
                            <Edit2 className="w-4 h-4" />
                          </button>
                        </div>
                      )}
                      
                      {field.ai_confidence < 0.7 && !field.edited && !isEditing && field.ai_value && (
                        <div className="mt-2 text-xs text-red-600 flex items-center gap-1">
                          <AlertTriangle className="w-3 h-3" /> Low confidence. Manual verification required.
                        </div>
                      )}
                      
                      {field.edited && !isEditing && (
                        <div className="mt-2 text-xs text-gray-500 flex items-center gap-1 line-through">
                          Original AI: {field.ai_value}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function PipelineProgress({ step, current, label }: any) {
  const isDone = current >= step;
  const isCurrent = current === step - 1;
  
  return (
    <div className="flex items-center gap-3">
      <div className={clsx(
        "w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold",
        isDone ? "bg-emerald-500 text-white" : isCurrent ? "bg-blue-500 text-white animate-pulse" : "bg-gray-200 text-gray-500"
      )}>
        {isDone ? <Check className="w-3 h-3" /> : step}
      </div>
      <span className={clsx("text-sm font-medium", isDone ? "text-gray-900" : isCurrent ? "text-blue-700" : "text-gray-400")}>
        {label}
      </span>
    </div>
  );
}
