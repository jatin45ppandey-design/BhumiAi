export const API='http://127.0.0.1:8000';
export const token=()=>typeof window==='undefined'?'':localStorage.getItem('token')||'';
export async function api(path:string,options:RequestInit={}){const h=new Headers(options.headers);h.set('Authorization','Bearer '+token());const r=await fetch(API+path,{...options,headers:h});if(!r.ok)throw new Error((await r.json().catch(()=>({detail:r.statusText}))).detail);return r.json()}
export async function form(path:string,data:FormData){return api(path,{method:'POST',body:data})}
