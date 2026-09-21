'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { Activity, ClipboardList, Code2, Database, Files, LayoutDashboard, LogOut, MapPinned, ShieldCheck, Upload, UserRound } from 'lucide-react';
import { signOut } from '../../lib/auth';
import { api } from '../../lib/api';

const links = {
  user: [
    ['Overview', '/user', LayoutDashboard],
    ['Digitize Record', '/user/upload', Upload],
    ['My Submissions', '/user/submissions', Files],
    ['Verified Records', '/user/records', ShieldCheck],
    ['Profile', '/user/profile', UserRound],
  ],
  officer: [
    ['Overview', '/officer', LayoutDashboard],
    ['Digitize Record', '/officer/upload', Upload],
    ['Review Queue', '/officer/submissions', ClipboardList],
    ['Verified Records', '/officer/records', Database],
    ['Activity History', '/officer/audit', Activity],
  ],
};

export default function PortalShell({ role, user, children }) {
  const path = usePathname();
  const router = useRouter();
  const [developerMode, setDeveloperMode] = useState(false);
  const workspace = role === 'officer' ? 'Verification workspace' : 'Land record workspace';
  const [primaryLink, ...recordLinks] = links[role];
  const activeLink = links[role].find(([, href]) => path === href || path.startsWith(`${href}/`)) || primaryLink;
  const roleLabel = role === 'officer' ? 'Verification Officer' : 'Record submitter';

  useEffect(() => {
    if (role === 'officer') setDeveloperMode(window.localStorage.getItem('bhumiai-developer-mode') === 'on');
  }, [role]);

  function toggleDeveloperMode() {
    const next = !developerMode;
    setDeveloperMode(next);
    window.localStorage.setItem('bhumiai-developer-mode', next ? 'on' : 'off');
  }

  async function logout() {
    try { await api.logout(); } catch { /* Session may already be expired. */ }
    signOut();
    router.push('/login');
  }

  return <div className={`portal ${developerMode ? 'developer-mode' : ''}`}>
    <aside className="sidebar">
      <Link href={`/${role}`} className="brand" aria-label="BhumiAI home">
        <span className="brand-mark"><MapPinned size={19} /></span>
        <strong>Bhumi<span>AI</span></strong>
        <small>LAND RECORD WORKSPACE</small>
      </Link>
      <nav aria-label="Primary navigation">
        <span className="nav-label">WORKSPACE</span>
        {[primaryLink].map(([label, href, Icon]) => <Link className={path === href || path.startsWith(`${href}/`) ? 'active' : ''} href={href} key={href}>
          <Icon size={17} />{label}
        </Link>)}
        <span className="nav-label records-label">RECORDS</span>
        {recordLinks.map(([label, href, Icon]) => <Link className={path === href || path.startsWith(`${href}/`) ? 'active' : ''} href={href} key={href}>
          <Icon size={17} />{label}
        </Link>)}
      </nav>
      <div className="sidebar-bottom">
        <div className="sidebar-user"><span>{user?.name?.slice(0, 1) || 'U'}</span><div><b>{user?.name || 'Portal user'}</b><small>{roleLabel}</small></div></div>
        {role === 'officer' && <button className="developer-toggle" type="button" aria-label={`Developer Mode ${developerMode ? 'on' : 'off'}`} aria-pressed={developerMode} onClick={toggleDeveloperMode}><Code2 size={16} /> Developer Mode <span>{developerMode ? 'On' : 'Off'}</span></button>}
        <button onClick={logout}><LogOut size={16} /> Sign out</button>
      </div>
    </aside>
    <div className="main">
      <header className="topbar"><div><span className="crumb">BHUMIAI / {workspace.toUpperCase()} / {activeLink[0].toUpperCase()}</span><h1>{activeLink[0]}</h1></div><div className="topbar-context"><span className="role-chip">{roleLabel}</span><MapPinned size={15} /><span>Traceable digital records</span></div></header>
      <main className="page">{children}</main>
    </div>
  </div>;
}
