"use client";

import { Map, Languages, Brain, Sparkles, ArrowRight } from "lucide-react";

export default function AdvancedFeatures() {
  return (
    <div className="space-y-8 max-w-5xl mx-auto">
      <div>
        <h2 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Sparkles className="w-6 h-6 text-purple-600" /> Advanced Capabilities
        </h2>
        <p className="text-gray-500 mt-1">Explore upcoming and beta features powered by Bhashini and AI.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <FeatureCard 
          icon={<Languages className="w-8 h-8 text-blue-600" />}
          title="Bhashini Translation"
          description="Automatically translate complex legal Hindi land records into 22+ regional languages instantly."
          status="BETA"
          statusColor="bg-blue-100 text-blue-700"
        />
        
        <FeatureCard 
          icon={<Map className="w-8 h-8 text-emerald-600" />}
          title="GIS Parcel Validation"
          description="Cross-reference Khasra numbers with live satellite GIS mapping to detect area discrepancies."
          status="COMING SOON"
          statusColor="bg-emerald-100 text-emerald-700"
        />

        <FeatureCard 
          icon={<Brain className="w-8 h-8 text-purple-600" />}
          title="Cross-Record Intelligence"
          description="Detect fragmented land holdings across different tehsils using fuzzy matching on owner names."
          status="EXPERIMENTAL"
          statusColor="bg-purple-100 text-purple-700"
        />
      </div>

      <div className="bg-gradient-to-r from-slate-900 to-slate-800 rounded-xl p-8 text-white mt-12 flex items-center justify-between shadow-xl">
        <div>
          <h3 className="text-xl font-bold">Join the Beta Program</h3>
          <p className="text-slate-300 mt-2 max-w-xl">Get early access to our Bhashini translation layer and provide feedback on regional language accuracy.</p>
        </div>
        <button className="bg-white text-slate-900 font-bold px-6 py-3 rounded-lg hover:bg-slate-100 transition-colors flex items-center gap-2">
          Opt-in Now <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}

function FeatureCard({ icon, title, description, status, statusColor }: any) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm hover:shadow-md transition-shadow relative overflow-hidden group">
      <div className="absolute top-0 right-0 w-24 h-24 bg-gray-50 rounded-bl-full -mr-4 -mt-4 transition-transform group-hover:scale-110 -z-10"></div>
      
      <div className="mb-4 bg-gray-50 inline-block p-3 rounded-lg border border-gray-100">
        {icon}
      </div>
      
      <h3 className="text-lg font-bold text-gray-900 mb-2">{title}</h3>
      <p className="text-sm text-gray-600 mb-6 line-clamp-3">{description}</p>
      
      <div className="mt-auto flex items-center justify-between">
        <span className={`text-xs font-bold px-2.5 py-1 rounded-full ${statusColor}`}>
          {status}
        </span>
        <button className="text-gray-400 hover:text-gray-900 transition-colors">
          <ArrowRight className="w-5 h-5" />
        </button>
      </div>
    </div>
  );
}
