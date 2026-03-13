import React, { createContext, useContext, useMemo } from 'react';
import { createApiClient, type ApiClient } from '../services/apiClient';

const DataClientContext = createContext<ApiClient | null>(null);

export const DataClientProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const client = useMemo(() => createApiClient(), []);
  return (
    <DataClientContext.Provider value={client}>
      {children}
    </DataClientContext.Provider>
  );
};

export function useDataClient(): ApiClient {
  const client = useContext(DataClientContext);
  if (!client) {
    throw new Error('useDataClient must be used within a DataClientProvider');
  }
  return client;
}
