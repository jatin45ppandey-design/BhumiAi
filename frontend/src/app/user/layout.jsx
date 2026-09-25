'use client';

import {useEffect, useState} from 'react';
import {usePathname, useRouter} from 'next/navigation';
import PortalShell from '../../components/layout/PortalShell';
import {saveUser} from '../../lib/auth';
import {api} from '../../lib/api';
import {Loader} from '../../components/common/UI';

export default function UserLayout({children}) {
  const [user, setUser] = useState(null);
  const [resolved, setResolved] = useState(false);
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    setResolved(false);
    api.me().then(me => {
      if (me.role !== 'user') throw new Error('Wrong workspace');
      saveUser(me);
      setUser(me);
      if ((!me.phone_verified || !me.profile_completed) && pathname !== '/user/profile') {
        router.replace('/user/profile');
        return;
      }
      setResolved(true);
    }).catch(() => router.replace('/login'));
  }, [pathname, router]);

  const profileIncomplete = user && (!user.phone_verified || !user.profile_completed);
  const mayRenderRoute = user && (!profileIncomplete || pathname === '/user/profile');
  if (!resolved || !mayRenderRoute) return <Loader label="Checking secure session…"/>;
  return <PortalShell role="user" user={user}>{children}</PortalShell>;
}
