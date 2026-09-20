'use client';

import {useEffect, useState} from 'react';
import {useRouter} from 'next/navigation';
import PortalShell from '../../components/layout/PortalShell';
import {saveUser} from '../../lib/auth';
import {api} from '../../lib/api';
import {Loader} from '../../components/common/UI';

export default function UserLayout({children}) {
  const [user, setUser] = useState(null); const router = useRouter();
  useEffect(() => {
    api.me().then(me => {
      if (me.role !== 'user') throw new Error('Wrong workspace');
      saveUser(me); setUser(me);
      if (!me.phone_verified || !me.profile_completed) router.replace('/user/profile');
    }).catch(() => router.replace('/login'));
  }, [router]);
  return user ? <PortalShell role="user" user={user}>{children}</PortalShell> : <Loader label="Checking secure session…"/>;
}
