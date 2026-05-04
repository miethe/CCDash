import React from 'react';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { DataProvider } from './contexts/DataContext';
import { ModelColorsProvider } from './contexts/ModelColorsContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { Layout } from './components/Layout';

type RouteComponent<TProps = object> = React.ComponentType<TProps>;

function lazyNamed<TProps = object>(
  importer: () => Promise<Record<string, unknown>>,
  exportName: string,
) {
  return React.lazy(async () => {
    const module = await importer();
    const component = module[exportName] as RouteComponent<TProps> | undefined;

    if (!component) {
      throw new Error(`Lazy export "${exportName}" was not found.`);
    }

    return { default: component };
  });
}

const LandingPage = lazyNamed(() => import('./components/LandingPage'), 'LandingPage');
const DocsPage = lazyNamed(() => import('./components/Docs/DocsPage'), 'DocsPage');
const Dashboard = lazyNamed(() => import('./components/Dashboard'), 'Dashboard');
const ProjectBoard = lazyNamed(() => import('./components/ProjectBoard'), 'ProjectBoard');
const SessionInspector = lazyNamed(() => import('./components/SessionInspector'), 'SessionInspector');
const Settings = lazyNamed(() => import('./components/Settings'), 'Settings');
const PlanCatalog = lazyNamed(() => import('./components/PlanCatalog'), 'PlanCatalog');
const AnalyticsDashboard = lazyNamed(() => import('./components/Analytics/AnalyticsDashboard'), 'AnalyticsDashboard');
const SessionMappings = lazyNamed(() => import('./components/SessionMappings'), 'SessionMappings');
const OpsPanel = lazyNamed(() => import('./components/OpsPanel'), 'OpsPanel');
const CodebaseExplorer = lazyNamed(() => import('./components/CodebaseExplorer'), 'CodebaseExplorer');
const FeatureExecutionWorkbench = lazyNamed(() => import('./components/FeatureExecutionWorkbench'), 'FeatureExecutionWorkbench');
const TestingPage = lazyNamed(() => import('./components/TestVisualizer/TestingPage'), 'TestingPage');
const WorkflowRegistryPage = lazyNamed(() => import('./components/Workflows/WorkflowRegistryPage'), 'WorkflowRegistryPage');
const PlanningModule = () => import('./components/Planning');
const PlanningHomePage = lazyNamed(PlanningModule, 'PlanningHomePage');
const PlanningNodeDetail = lazyNamed(PlanningModule, 'PlanningNodeDetail');
const PlanningRouteLayout = lazyNamed(PlanningModule, 'PlanningRouteLayout');
const ArtifactDrillDownPage = lazyNamed(() => import('./components/Planning/ArtifactDrillDownPage'), 'ArtifactDrillDownPage');

function RoutePending() {
  return (
    <div className="flex min-h-[240px] w-full items-center justify-center px-6 py-10" role="status" aria-live="polite" aria-label="Loading page">
      <div className="flex items-center gap-3 text-muted-foreground">
        <Loader2 size={18} className="animate-spin text-info" aria-hidden="true" />
        <span className="text-sm">Loading page...</span>
      </div>
    </div>
  );
}

function withRouteSuspense(element: React.ReactNode) {
  return <React.Suspense fallback={<RoutePending />}>{element}</React.Suspense>;
}

const App: React.FC = () => {
  return (
    <ThemeProvider>
      <HashRouter>
        <Routes>
          <Route path="/" element={withRouteSuspense(<LandingPage />)} />
          <Route path="/docs" element={withRouteSuspense(<DocsPage />)} />
          <Route path="/app" element={<Navigate to="/dashboard" replace />} />
          <Route
            path="/*"
            element={
              <DataProvider>
                <Layout>
                  <ModelColorsProvider>
                    <React.Suspense fallback={<RoutePending />}>
                      <Routes>
                        <Route path="/dashboard" element={<Dashboard />} />
                        <Route path="/board" element={<ProjectBoard />} />
                        <Route path="/plans" element={<PlanCatalog />} />
                        <Route path="/sessions" element={<SessionInspector />} />
                        <Route path="/execution" element={<FeatureExecutionWorkbench />} />
                        <Route element={<PlanningRouteLayout />}>
                          <Route path="/planning" element={<PlanningHomePage />} />
                          <Route path="/planning/feature/:featureId" element={<PlanningNodeDetail />} />
                          <Route path="/planning/artifacts/:type" element={<ArtifactDrillDownPage />} />
                        </Route>
                        <Route path="/tests" element={<TestingPage />} />
                        <Route path="/analytics" element={<AnalyticsDashboard />} />
                        <Route path="/workflows" element={<WorkflowRegistryPage />} />
                        <Route path="/workflows/:workflowId" element={<WorkflowRegistryPage />} />
                        <Route path="/session-mappings" element={<SessionMappings />} />
                        <Route path="/ops" element={<OpsPanel />} />
                        <Route path="/codebase" element={<CodebaseExplorer />} />
                        <Route path="/settings" element={<Settings />} />
                        <Route path="*" element={<Navigate to="/dashboard" replace />} />
                      </Routes>
                    </React.Suspense>
                  </ModelColorsProvider>
                </Layout>
              </DataProvider>
            }
          />
        </Routes>
      </HashRouter>
    </ThemeProvider>
  );
};

export default App;
