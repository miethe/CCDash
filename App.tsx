import React from 'react';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Dashboard } from './components/Dashboard';
import { ProjectBoard } from './components/ProjectBoard';
import { SessionInspector } from './components/SessionInspector';
import { Settings } from './components/Settings';
import { PlanCatalog } from './components/PlanCatalog';

const App: React.FC = () => {
  return (
    <HashRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/board" element={<ProjectBoard />} />
          <Route path="/plans" element={<PlanCatalog />} />
          <Route path="/sessions" element={<SessionInspector />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Layout>
    </HashRouter>
  );
};

export default App;