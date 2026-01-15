// API client for backend communication
const API_BASE = 'http://localhost:8000/api';

export interface JobCreateRequest {
  path: string;
  includeExcluded?: boolean;
  jointMode?: 'copy' | 'combine';
  postValidate?: boolean;
}

export interface JobStatus {
  job_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  stage: string;
  message: string;
  result?: {
    moved: number;
    copied: number;
    clusters: number;
    no_faces: number;
    unreadable: number;
  };
  error?: string;
}

export interface FileSystemItem {
  name: string;
  path: string;
  type: 'file' | 'directory';
  size?: number;
  modified?: string;
  preview_path?: string;
}

export interface ReviewCandidatesResponse {
  root: string;
  image_path: string;
  faces: Array<{
    face_index: number;
    bbox: [number, number, number, number];
    det_score: number;
    candidates: Array<{
      cluster_id: number | string;
      folder_name: string;
      folder_path: string;
      score: number;
      percent: number;
      example_image?: string | null;
    }>;
  }>;
}

export class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE) {
    this.baseUrl = baseUrl;
  }

  async createJob(request: JobCreateRequest): Promise<JobStatus> {
    const response = await fetch(`${this.baseUrl}/jobs/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw new Error(`Failed to create job: ${response.statusText}`);
    }

    return response.json();
  }

  async getJob(jobId: string): Promise<JobStatus> {
    const response = await fetch(`${this.baseUrl}/jobs/${jobId}`);

    if (!response.ok) {
      throw new Error(`Failed to get job: ${response.statusText}`);
    }

    return response.json();
  }

  async listJobs(): Promise<JobStatus[]> {
    const response = await fetch(`${this.baseUrl}/jobs/`);

    if (!response.ok) {
      throw new Error(`Failed to list jobs: ${response.statusText}`);
    }

    return response.json();
  }

  async cancelJob(jobId: string): Promise<void> {
    const response = await fetch(`${this.baseUrl}/jobs/${jobId}/cancel`, {
      method: 'POST',
    });

    if (!response.ok) {
      throw new Error(`Failed to cancel job: ${response.statusText}`);
    }
  }

  async listRoots(): Promise<string[]> {
    const response = await fetch(`${this.baseUrl}/fs/roots`);

    if (!response.ok) {
      throw new Error(`Failed to list roots: ${response.statusText}`);
    }

    return response.json();
  }

  async listDirectory(path: string): Promise<FileSystemItem[]> {
    const response = await fetch(`${this.baseUrl}/fs/list?path=${encodeURIComponent(path)}`);

    if (!response.ok) {
      throw new Error(`Failed to list directory: ${response.statusText}`);
    }

    return response.json();
  }

  async rename(path: string, newName: string): Promise<{ ok: boolean; new_path: string }> {
    const response = await fetch(`${this.baseUrl}/fs/rename?path=${encodeURIComponent(path)}&new_name=${encodeURIComponent(newName)}`, {
      method: 'POST',
    });

    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || `Failed to rename: ${response.statusText}`);
    }

    return response.json();
  }

  async move(src: string, dst: string): Promise<{ ok: boolean; new_path: string }> {
    const response = await fetch(`${this.baseUrl}/fs/move`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ src, dst }),
    });

    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || `Failed to move: ${response.statusText}`);
    }

    return response.json();
  }

  async getCandidates(root: string, path: string, topK: number = 5): Promise<ReviewCandidatesResponse> {
    const url = `${this.baseUrl}/review/candidates?root=${encodeURIComponent(root)}&path=${encodeURIComponent(path)}&top_k=${topK}`;
    const response = await fetch(url);
    if (!response.ok) {
      const err = await response.json().catch(() => ({} as any));
      throw new Error(err.detail || `Failed to get candidates: ${response.statusText}`);
    }
    return response.json();
  }

  subscribeToUpdates(): EventSource {
    return new EventSource(`${this.baseUrl}/jobs/stream`);
  }
}

export const apiClient = new ApiClient();

// Legacy API functions for backward compatibility
export async function apiList(path: string): Promise<FileSystemItem[]> {
  return apiClient.listDirectory(path);
}

export function previewUrl(path: string, size: number = 384): string {
  return `${API_BASE}/fs/preview?path=${encodeURIComponent(path)}&size=${size}`;
}

export async function apiJob(request: JobCreateRequest): Promise<JobStatus> {
  return apiClient.createJob(request);
}

export async function apiListJobs(): Promise<JobStatus[]> {
  return apiClient.listJobs();
}

export async function apiCancelJob(jobId: string): Promise<void> {
  return apiClient.cancelJob(jobId);
}

export async function apiRoots(): Promise<string[]> {
  return apiClient.listRoots();
}

export async function apiCreateJob(request: JobCreateRequest): Promise<JobStatus> {
  return apiClient.createJob(request);
}

export type FsEntry = FileSystemItem;
