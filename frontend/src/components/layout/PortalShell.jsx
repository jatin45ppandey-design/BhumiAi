'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { Activity, ClipboardList, Code2, Database, Files, LayoutDashboard, LogOut, MapPinned, ShieldCheck, Upload, UserRound } from 'lucide-react';
import { signOut } from '../../lib/auth';
import { api } from '../../lib/api';

const navigation = {
  user: [
    ['WORKSPACE', [
      ['Overview', '/user', LayoutDashboard],
      ['Digitize record', '/user/upload', Upload],
      ['My submissions', '/user/submissions', Files],
    ]],
    ['RECORDS', [['Verified records', '/user/records', ShieldCheck]]],
  ],
  officer: [
    ['WORKSPACE', [
      ['Overview', '/officer', LayoutDashboard],
      ['Review Queue', '/officer/submissions', ClipboardList],
      ['Verified Records', '/officer/records', Database],
    ]],
  ],
};

export default function PortalShell({ role, user, children }) {
  const path = usePathname();
  const router = useRouter();
  const [developerMode, setDeveloperMode] = useState(false);
  const workspace = role === 'officer' ? 'Verification workspace' : 'Land record workspace';
  const isActiveRoute = (href) => href === `/${role}`
    ? path === href
    : path === href || path.startsWith(`${href}/`);
  const roleLabel = role === 'officer' ? 'Verification Officer' : 'Record submitter';

  useEffect(() => {
    if (role === 'officer') setDeveloperMode(window.localStorage.getItem('bhumiai-developer-mode') === 'on');
  }, [role]);

  function toggleDeveloperMode() {
    const next = !developerMode;
    setDeveloperMode(next);
    window.localStorage.setItem('bhumiai-developer-mode', next ? 'on' : 'off');
    if (!next && role === 'officer' && path.startsWith('/officer/audit')) router.replace('/officer');
  }

  const officerNavigation = role === 'officer' && developerMode
    ? [...navigation.officer, ['DEVELOPER TOOLS', [['System Audit', '/officer/audit', Activity]]]]
    : navigation[role];
  const visibleNavigation = role === 'officer' ? officerNavigation : navigation[role];
  const allLinks = visibleNavigation.flatMap(([, items]) => items);
  const activeLink = allLinks.find(([, href]) => isActiveRoute(href)) || allLinks[0];

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
        {visibleNavigation.map(([group, items]) => <section className="nav-group" key={group} aria-label={group}>
          <span className="nav-label">{group}</span>
          {items.map(([label, href, Icon]) => <Link className={isActiveRoute(href) ? 'active' : ''} aria-current={isActiveRoute(href) ? 'page' : undefined} href={href} key={href}>
            <Icon size={17} />{label}
          </Link>)}
        </section>)}
      </nav>
      <div className="sidebar-bottom">
        <div className="sidebar-user"><span>{user?.name?.slice(0, 1) || 'U'}</span><div><b>{user?.name || 'Portal user'}</b><small>{roleLabel}</small></div></div>
        {role === 'user' && <Link className="sidebar-account-link" href="/user/profile"><UserRound size={16} /> Profile & settings</Link>}
        {role === 'officer' && <button className="developer-toggle" type="button" aria-label={`Developer Mode ${developerMode ? 'on' : 'off'}`} aria-pressed={developerMode} onClick={toggleDeveloperMode}><Code2 size={16} /> Developer Mode <span>{developerMode ? 'On' : 'Off'}</span></button>}
        <button onClick={logout}><LogOut size={16} /> Sign out</button>
      </div>
    </aside>
    <div className="main">
      <header className="topbar"><div><span className="crumb">BHUMIAI / {workspace.toUpperCase()} / {activeLink[0].toUpperCase()}</span><h1>{workspace}</h1></div><div className="topbar-context"><span className="role-chip">{roleLabel}</span><MapPinned size={15} /><span>Traceable digital records</span></div></header>
      <main className="page">{children}</main>
    </div>
  </div>;
}
