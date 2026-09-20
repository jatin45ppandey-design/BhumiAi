"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import axios from "axios";
import { API_URL } from "@/lib/api";

export default function Login() {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("user");
  const router = useRouter();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await axios.post(`${API_URL}/api/auth/login`, {
        email,
        name: name,
        password: "password",
        role: role
      });
      
      const user = res.data.user;
      localStorage.setItem("user", JSON.stringify(user));
      
      if (user.role?.toLowerCase() === "officer") {
        router.push("/officer");
      } else {
        router.push("/user");
      }
    } catch (error) {
      console.error("Login failed", error);
    }
  };

  return (
    <div className="flex h-screen w-full items-center justify-center bg-gray-50">
      <div className="w-full max-w-md bg-white p-8 rounded-xl shadow-lg border border-gray-100">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-gray-900">Land Record Platform</h1>
          <p className="text-sm text-gray-500 mt-2">Sign in to your account</p>
        </div>
        
        <form onSubmit={handleLogin} className="space-y-6">
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">Account Type</label>
              <div className="mt-2 flex gap-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="radio" checked={role === "user"} onChange={() => setRole("user")} className="w-4 h-4 text-blue-600" />
                  <span className="text-sm">Citizen / User</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="radio" checked={role === "officer"} onChange={() => setRole("officer")} className="w-4 h-4 text-blue-600" />
                  <span className="text-sm">Verification Officer</span>
                </label>
              </div>
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700">Name</label>
              <input 
                type="text" 
                required
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500" 
                value={name} 
                onChange={(e) => setName(e.target.value)} 
                placeholder="Enter your name"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700">Email address</label>
              <input 
                type="email" 
                required
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500" 
                value={email} 
                onChange={(e) => setEmail(e.target.value)} 
                placeholder="you@example.com"
              />
            </div>
          </div>
          
          <button 
            type="submit" 
            className="w-full rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors"
          >
            Sign In
          </button>
        </form>
        
        <div className="mt-6 text-center text-xs text-gray-500">
          <p>Demo Credentials:</p>
          <p>User: user@example.com</p>
          <p>Officer: officer@example.com</p>
        </div>
      </div>
    </div>
  );
}
