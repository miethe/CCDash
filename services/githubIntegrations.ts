import {
  GitHubCredentialValidationRequest,
  GitHubCredentialValidationResponse,
  GitHubIntegrationSettingsResponse,
  GitHubIntegrationSettingsUpdateRequest,
  GitHubPathValidationRequest,
  GitHubPathValidationResponse,
  GitHubWorkspaceRefreshRequest,
  GitHubWorkspaceRefreshResponse,
  GitHubWriteCapabilityRequest,
  GitHubWriteCapabilityResponse,
  ProjectResolvedPathsDTO,
} from '../types';
import { apiRequestJson } from './apiClient';

const GITHUB_API_BASE = '/api/integrations/github';
const PROJECT_API_BASE = '/api/projects';

const requestJson = apiRequestJson;

export const getGitHubSettings = (): Promise<GitHubIntegrationSettingsResponse> => (
  requestJson<GitHubIntegrationSettingsResponse>(`${GITHUB_API_BASE}/settings`)
);

export const updateGitHubSettings = (
  settings: GitHubIntegrationSettingsUpdateRequest,
): Promise<GitHubIntegrationSettingsResponse> => (
  requestJson<GitHubIntegrationSettingsResponse>(`${GITHUB_API_BASE}/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  })
);

export const validateGitHubCredential = (
  payload: GitHubCredentialValidationRequest,
): Promise<GitHubCredentialValidationResponse> => (
  requestJson<GitHubCredentialValidationResponse>(`${GITHUB_API_BASE}/validate-credential`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
);

export const validateGitHubPath = (
  payload: GitHubPathValidationRequest,
): Promise<GitHubPathValidationResponse> => (
  requestJson<GitHubPathValidationResponse>(`${GITHUB_API_BASE}/validate-path`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
);

export const refreshGitHubWorkspace = (
  payload: GitHubWorkspaceRefreshRequest,
): Promise<GitHubWorkspaceRefreshResponse> => (
  requestJson<GitHubWorkspaceRefreshResponse>(`${GITHUB_API_BASE}/refresh-workspace`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
);

export const checkGitHubWriteCapability = (
  payload: GitHubWriteCapabilityRequest,
): Promise<GitHubWriteCapabilityResponse> => (
  requestJson<GitHubWriteCapabilityResponse>(`${GITHUB_API_BASE}/check-write-capability`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
);

export const getProjectResolvedPaths = (projectId: string): Promise<ProjectResolvedPathsDTO> => (
  requestJson<ProjectResolvedPathsDTO>(`${PROJECT_API_BASE}/${encodeURIComponent(projectId)}/paths`)
);
