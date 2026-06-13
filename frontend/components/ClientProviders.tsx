'use client';

import { AuthProvider } from '../contexts/AuthContext';
import { WatchlistProvider } from '../contexts/WatchlistContext';

export default function ClientProviders({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <WatchlistProvider>
        {children}
      </WatchlistProvider>
    </AuthProvider>
  );
}
