"use client";

import { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import axios from "axios";
import { useRouter } from "next/navigation";
import { UploadCloud, File, AlertTriangle, CheckCircle, ArrowRight, FileText } from "lucide-react";
import { API_URL } from "@/lib/api";

export default function UploadDocument() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [docType, setDocType] = useState("Khatauni");
  const [state, setStateName] = useState("Uttar Pradesh");
  const [district, setDistrict] = useState("");
  const [tehsil, setTehsil] = useState("");
  const [village, setVillage] = useState("");
  
  const [step, setStep] = useState(1);
  const [docId, setDocId] = useState<number | null>(null);
  const [duplicateCheck, setDuplicateCheck] = useState<{duplicate: boolean, message: string} | null>(null);
  const [loading, setLoading] = useState(false);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    if (acceptedFiles.length > 0) {
      setFile(acceptedFiles[0]);
    }
  }, []);
  const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop, accept: {'image/*': ['.png', '.jpg', '.jpeg'], 'application/pdf': ['.pdf']}, maxFiles: 1 });

  const handleUploadAndCheck = async () => {
    if (!file || !district || !tehsil || !village) {
      alert("Please fill all required fields and select a file.");
      return;
    }
    
    setLoading(true);
    const formData = new FormData();
    formData.append("file", file);
    formData.append("document_type", docType);
    formData.append("state", state);
    formData.append("district", district);
    formData.append("tehsil", tehsil);
    formData.append("village", village);
    
    try {
      // 1. Upload Document
      const uploadRes = await axios.post(`${API_URL}/api/documents/upload`, formData);
      const newDocId = uploadRes.data.document_id;
      setDocId(newDocId);
      
      // 2. Prototype Duplicate Check
      const dupRes = await axios.post(`${API_URL}/api/documents/${newDocId}/duplicate-check`);
      setDuplicateCheck(dupRes.data);
      setStep(2);
    } catch (err) {
      console.error(err);
      alert("Upload failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmitToOfficer = async () => {
    if (!docId) return;
    setLoading(true);
    try {
      const user = JSON.parse(localStorage.getItem("user") || "{}");
      await axios.post(`${API_URL}/api/documents/${docId}/submit?user_id=${user.id}`);
      router.push("/user/submissions");
    } catch (err) {
      console.error(err);
      alert("Submission failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-gray-900">Upload Land Record</h2>
        <p className="text-gray-500 mt-1">Submit your documents for AI processing and officer verification.</p>
      </div>

      {step === 1 && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="p-6 md:p-8 space-y-8">
            {/* Metadata Fields */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Document Type *</label>
                <select 
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
                  value={docType}
                  onChange={e => setDocType(e.target.value)}
                >
                  <option>Khatauni</option>
                  <option>Khasra</option>
                  <option>Jamabandi</option>
                  <option>Deed</option>
                  <option>Mutation Record</option>
                  <option>Other</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">State *</label>
                <input 
                  type="text" className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm bg-gray-50"
                  value={state} readOnly
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">District *</label>
                <input 
                  type="text" className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
                  placeholder="e.g. Lucknow" value={district} onChange={e => setDistrict(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Tehsil *</label>
                <input 
                  type="text" className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
                  placeholder="e.g. Sadar" value={tehsil} onChange={e => setTehsil(e.target.value)}
                />
              </div>
              <div className="md:col-span-2">
                <label className="block text-sm font-medium text-gray-700 mb-1">Village *</label>
                <input 
                  type="text" className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
                  placeholder="e.g. Rampur" value={village} onChange={e => setVillage(e.target.value)}
                />
              </div>
            </div>

            {/* Dropzone */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Document File *</label>
              <div 
                {...getRootProps()} 
                className={`border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors ${
                  isDragActive ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:bg-gray-50'
                }`}
              >
                <input {...getInputProps()} />
                <div className="flex flex-col items-center">
                  <UploadCloud className="w-12 h-12 text-gray-400 mb-4" />
                  {file ? (
                    <div className="flex items-center gap-2 text-blue-600 font-medium">
                      <File className="w-5 h-5" />
                      {file.name}
                    </div>
                  ) : (
                    <>
                      <p className="text-gray-700 font-medium text-lg">Drag & drop your file here</p>
                      <p className="text-gray-500 text-sm mt-1">or click to browse (PDF, PNG, JPG)</p>
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>
          
          <div className="bg-gray-50 px-6 py-4 border-t border-gray-200 flex justify-end">
            <button 
              onClick={handleUploadAndCheck}
              disabled={loading || !file}
              className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-md font-medium flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? "Processing..." : "Next Step"}
              {!loading && <ArrowRight className="w-4 h-4" />}
            </button>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="p-6 md:p-8 space-y-6">
            <div className="flex items-center gap-4 pb-6 border-b border-gray-200">
              <div className="bg-blue-100 text-blue-600 p-3 rounded-full">
                <FileText className="w-8 h-8" />
              </div>
              <div>
                <h3 className="text-xl font-bold text-gray-900">Document Summary</h3>
                <p className="text-gray-500 text-sm">Review your submission details</p>
              </div>
            </div>
            
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div className="bg-gray-50 p-4 rounded-md">
                <span className="text-gray-500 block mb-1">Document Type</span>
                <span className="font-semibold text-gray-900">{docType}</span>
              </div>
              <div className="bg-gray-50 p-4 rounded-md">
                <span className="text-gray-500 block mb-1">File Name</span>
                <span className="font-semibold text-gray-900 truncate block">{file?.name}</span>
              </div>
              <div className="bg-gray-50 p-4 rounded-md">
                <span className="text-gray-500 block mb-1">Village</span>
                <span className="font-semibold text-gray-900">{village}</span>
              </div>
              <div className="bg-gray-50 p-4 rounded-md">
                <span className="text-gray-500 block mb-1">District</span>
                <span className="font-semibold text-gray-900">{district}</span>
              </div>
            </div>
            
            {/* Duplicate Check Prototype Result */}
            <div className={`p-4 rounded-lg border ${duplicateCheck?.duplicate ? 'bg-orange-50 border-orange-200' : 'bg-green-50 border-green-200'}`}>
              <div className="flex items-start gap-3">
                {duplicateCheck?.duplicate ? (
                  <AlertTriangle className="w-6 h-6 text-orange-600 flex-shrink-0 mt-0.5" />
                ) : (
                  <CheckCircle className="w-6 h-6 text-green-600 flex-shrink-0 mt-0.5" />
                )}
                <div>
                  <h4 className={`font-semibold ${duplicateCheck?.duplicate ? 'text-orange-900' : 'text-green-900'}`}>
                    Prototype Duplicate Submission Check
                  </h4>
                  <p className={`text-sm mt-1 ${duplicateCheck?.duplicate ? 'text-orange-700' : 'text-green-700'}`}>
                    {duplicateCheck?.message}
                    {duplicateCheck?.duplicate && " Are you sure you want to proceed with this submission?"}
                  </p>
                </div>
              </div>
            </div>
          </div>
          
          <div className="bg-gray-50 px-6 py-4 border-t border-gray-200 flex justify-between">
            <button 
              onClick={() => setStep(1)}
              className="text-gray-600 hover:text-gray-900 font-medium px-4 py-2"
            >
              Back
            </button>
            <button 
              onClick={handleSubmitToOfficer}
              disabled={loading}
              className="bg-blue-600 hover:bg-blue-700 text-white px-8 py-2 rounded-md font-bold shadow-sm disabled:opacity-50"
            >
              {loading ? "Submitting..." : "SUBMIT TO OFFICER"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
