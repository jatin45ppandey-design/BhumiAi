'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { ClipboardList, Database, Files, LayoutDashboard, LogOut, MapPinned, ScrollText, ShieldCheck, Upload } from 'lucide-react';
import { getUser, signOut } from '../../lib/auth';

const links = {
  user: [
    ['Overview', '/user', LayoutDashboard],
    ['Digitize Record', '/user/upload', Upload],
    ['My Submissions', '/user/submissions', Files],
    ['Verified Records', '/user/records', ShieldCheck],
  ],
  officer: [
    ['Overview', '/officer', LayoutDashboard],
    ['Digitize Record', '/officer/upload', Upload],
    ['Review Queue', '/officer/submissions', ClipboardList],
    ['Verified Records', '/officer/records', Database],
    ['Audit Trail', '/officer/audit', ScrollText],
  ],
};

export default function PortalShell({ role, children }) {
  const path = usePathname();
  const router = useRouter();
  const user = getUser();
  const workspace = role === 'officer' ? 'Verification workspace' : 'Land record workspace';
  const [primaryLink, ...recordLinks] = links[role];
  const activeLink = links[role].find(([, href]) => path === href || path.startsWith(`${href}/`)) || primaryLink;
  const roleLabel = role === 'officer' ? 'Verification Officer' : 'Record submitter';

  function logout() {
    signOut();
    router.push('/login');
  }

  return <div className="portal">
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
        <button onClick={logout}><LogOut size={16} /> Sign out</button>
      </div>
    </aside>
    <div className="main">
      <header className="topbar"><div><span className="crumb">BHUMIAI / {workspace.toUpperCase()} / {activeLink[0].toUpperCase()}</span><h1>{activeLink[0]}</h1></div><div className="topbar-context"><span className="role-chip">{roleLabel}</span><MapPinned size={15} /><span>Traceable digital records</span></div></header>
      <main className="page">{children}</main>
    </div>
  </div>;
}
