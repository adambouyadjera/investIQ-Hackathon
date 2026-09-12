import { useEffect, useState } from 'react';
import { getUser, subscribe } from '../store/auth';
import type { User as UserType } from '../types';

export function useAuth() {
  const [user, setUser] = useState<UserType | null>(getUser());

  useEffect(() => {
    const unsub = subscribe(() => setUser(getUser()));
    return unsub;
  }, []);

  return {
    user,
    isAuthenticated: !!user,
  };
}
