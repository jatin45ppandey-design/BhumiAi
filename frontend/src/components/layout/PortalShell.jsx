'use client';

import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
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
  const searchParams = useSearchParams();
  const router = useRouter();
  const [developerMode, setDeveloperMode] = useState(false);
  const [routePending, setRoutePending] = useState(false);
  const [pendingRoute, setPendingRoute] = useState('');
  const [loggingOut, setLoggingOut] = useState(false);
  const workspace = role === 'officer' ? 'Verification workspace' : 'Land record workspace';
  const query = searchParams.toString();
  const routeKey = `${path}${query ? `?${query}` : ''}`;
  const isActiveRoute = (href) => {
    const currentPath = pendingRoute || path;
    return href === `/${role}`
      ? currentPath === href
      : currentPath === href || currentPath.startsWith(`${href}/`);
  };
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

  useEffect(() => {
    setRoutePending(false);
    setPendingRoute('');
  }, [routeKey]);

  useEffect(() => {
    if (!routePending) return undefined;
    const timeout = window.setTimeout(() => {
      setRoutePending(false);
      setPendingRoute('');
    }, 5000);
    return () => window.clearTimeout(timeout);
  }, [routePending]);

  function handleNavigationClick(event) {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const anchor = event.target?.closest?.('a');
    const href = anchor?.getAttribute('href');
    if (!href || href.startsWith('#')) return;
    const target = new URL(href, window.location.origin);
    if (target.origin !== window.location.origin) return;
    const targetKey = `${target.pathname}${target.search}`;
    if (targetKey === routeKey) return;
    setPendingRoute(target.pathname);
    setRoutePending(true);
  }

  async function logout() {
    if (loggingOut) return;
    setLoggingOut(true);
    try { await api.logout(); } catch { /* Session may already be expired. */ }
    signOut();
    router.push('/login');
  }

  return <div className={`portal ${developerMode ? 'developer-mode' : ''}`} onClickCapture={handleNavigationClick}>
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
        <button onClick={logout} disabled={loggingOut} aria-busy={loggingOut}><LogOut size={16} /><span>{loggingOut ? 'Signing out…' : 'Sign out'}</span></button>
      </div>
    </aside>
    <div className="main">
      <div className={`route-progress ${routePending ? 'visible' : ''}`} role="progressbar" aria-label="Loading page" aria-hidden={!routePending} />
      <header className="topbar"><div><span className="crumb">BHUMIAI / {workspace.toUpperCase()} / {activeLink[0].toUpperCase()}</span><h1>{workspace}</h1></div><div className="topbar-context"><span className="role-chip">{roleLabel}</span><MapPinned size={15} /><span>Traceable digital records</span></div></header>
      <main className="page" aria-busy={routePending}><div key={routeKey} className="route-content">{children}</div></main>
    </div>
  </div>;
}
