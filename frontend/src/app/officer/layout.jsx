'use client';

import {useEffect, useState} from 'react';
import {useRouter} from 'next/navigation';
import PortalShell from '../../components/layout/PortalShell';
import {saveUser} from '../../lib/auth';
import {api} from '../../lib/api';
import {Loader} from '../../components/common/UI';

export default function OfficerLayout({children}) {
  const [user, setUser] = useState(null); const router = useRouter();
  useEffect(() => { api.me().then(me => { if (me.role !== 'officer') throw new Error('Wrong workspace'); saveUser(me); setUser(me); }).catch(() => router.replace('/login')); }, [router]);
  return user ? <PortalShell role="officer" user={user}>{children}</PortalShell> : <Loader label="Checking secure session…"/>;
}
