import React from 'react';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import { DataProvider } from './contexts/DataContext';
import { ModelColorsProvider } from './contexts/ModelColorsContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { Layout } from './components/Layout';
import { Dashboard } from './components/Dashboard';
import { ProjectBoard } from './components/ProjectBoard';
import { SessionInspector } from './components/SessionInspector';
import { Settings } from './components/Settings';
import { PlanCatalog } from './components/PlanCatalog';
import { AnalyticsDashboard } from './components/Analytics/AnalyticsDashboard';
import { SessionMappings } from './components/SessionMappings';
import { OpsPanel } from './components/OpsPanel';
import { CodebaseExplorer } from './components/CodebaseExplorer';
import { FeatureExecutionWorkbench } from './components/FeatureExecutionWorkbench';
import { TestingPage } from './components/TestVisualizer/TestingPage';
import { WorkflowRegistryPage } from './components/Workflows/WorkflowRegistryPage';

const App: React.FC = () => {
  return (
    <ThemeProvider>
      <DataProvider>
        <ModelColorsProvider>
          <HashRouter>
            <Layout>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/board" element={<ProjectBoard />} />
                <Route path="/plans" element={<PlanCatalog />} />
                <Route path="/sessions" element={<SessionInspector />} />
                <Route path="/execution" element={<FeatureExecutionWorkbench />} />
                <Route path="/tests" element={<TestingPage />} />
                <Route path="/analytics" element={<AnalyticsDashboard />} />
                <Route path="/workflows" element={<WorkflowRegistryPage />} />
                <Route path="/workflows/:workflowId" element={<WorkflowRegistryPage />} />
                <Route path="/session-mappings" element={<SessionMappings />} />
                <Route path="/ops" element={<OpsPanel />} />
                <Route path="/codebase" element={<CodebaseExplorer />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </Layout>
          </HashRouter>
        </ModelColorsProvider>
      </DataProvider>
    </ThemeProvider>
  );
};

export default App;
