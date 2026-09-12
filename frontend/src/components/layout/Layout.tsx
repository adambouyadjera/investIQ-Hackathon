import React from 'react';
import { Navbar } from './Navbar';
import { useAuth } from '../../hooks/useAuth';

export function Layout({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <Navbar />
      {user?.is_guest && (
        <div
          role="status"
          className="bg-indigo-900/40 border-b border-indigo-700 px-4 sm:px-6 py-2"
        >
          <p className="max-w-7xl mx-auto text-xs text-indigo-200">
            <span className="font-semibold">Demo session.</span>{' '}
            Sample data, discarded when you log out. Figures are real
            calculations on historical prices, not a record of anyone's account.
          </p>
        </div>
      )}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6">{children}</main>
    </div>
  );
}
