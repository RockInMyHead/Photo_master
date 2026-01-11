export interface FileItem {
  name: string;
  kind: 'file' | 'directory';
  handle: FileSystemHandle;
}

export interface QueueItem {
  id: string;
  name: string;
  path: string;
  handle?: FileSystemDirectoryHandle; // Optional for backend integration
  status: 'pending' | 'processing' | 'completed' | 'error';
  progress?: number;
  stage?: string;
  message?: string;
  filesCount?: number;
  processedCount?: number;
  clustersCount?: number;
  noFacesCount?: number;
  jobId?: string; // Backend job ID
}

export interface ProcessingStatus {
  isProcessing: boolean;
  currentItem: string | null;
  totalItems: number;
  completedItems: number;
  overallProgress: number;
}

// Backend-compatible types
export interface BackendJobStatus {
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
