import Link from 'next/link';

export default function StatCard({label, value, icon: Icon, tone = 'teal', href}) {
  const content = <><div><p>{label}</p><strong>{value ?? 0}</strong></div>{Icon && <span className="stat-icon"><Icon size={21}/></span>}</>;
  return href ? <Link className={`stat ${tone} stat-link`} href={href}>{content}</Link> : <article className={`stat ${tone}`}>{content}</article>;
}
