import { apiRequestJson } from './apiClient';

export interface CodebaseFileContentResponse {
  filePath: string;
  absolutePath: string;
  content: string;
  sizeBytes: number;
  truncated: boolean;
  originalSize?: number | null;
}

export interface CodebaseTreeResponse<TNode = unknown> {
  nodes: TNode[];
}

export interface CodebaseFilesResponse<TFile = unknown> {
  items: TFile[];
  total: number;
}

const API_BASE = '/api/codebase';

export async function getCodebaseFileContent(filePath: string): Promise<CodebaseFileContentResponse> {
  const params = new URLSearchParams({
    path: filePath,
  });
  return apiRequestJson<CodebaseFileContentResponse>(`${API_BASE}/file-content?${params.toString()}`);
}

export async function getCodebaseTree<TNode = unknown>(params: URLSearchParams): Promise<CodebaseTreeResponse<TNode>> {
  return apiRequestJson<CodebaseTreeResponse<TNode>>(`${API_BASE}/tree?${params.toString()}`);
}

export async function listCodebaseFiles<TFile = unknown>(params: URLSearchParams): Promise<CodebaseFilesResponse<TFile>> {
  return apiRequestJson<CodebaseFilesResponse<TFile>>(`${API_BASE}/files?${params.toString()}`);
}

export async function getCodebaseFileDetail<TDetail = unknown>(
  filePath: string,
  options?: { activityLimit?: number },
): Promise<TDetail> {
  const normalized = filePath.split('/').map(encodeURIComponent).join('/');
  const params = new URLSearchParams({
    activity_limit: String(options?.activityLimit ?? 120),
  });
  return apiRequestJson<TDetail>(`${API_BASE}/files/${normalized}?${params.toString()}`);
}
