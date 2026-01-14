import { useState, useCallback, useEffect, useRef } from "react";
import { Header } from "@/components/Header";
import { FileBrowser } from "@/components/FileBrowser";
import { ProcessingQueue } from "@/components/ProcessingQueue";
import { QueueItem, ProcessingStatus, BackendJobStatus } from "@/types/fileSystem";
import { apiClient } from "@/lib/api";
import { toast } from "sonner";

const Index = () => {
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const queueRef = useRef<QueueItem[]>([]);
  
  // Keep queueRef in sync with queue state
  useEffect(() => {
    queueRef.current = queue;
  }, [queue]);

  const [status, setStatus] = useState<ProcessingStatus>({
    isProcessing: false,
    currentItem: null,
    totalItems: 0,
    completedItems: 0,
    overallProgress: 0,
  });

  // Map backend status to frontend status
  const mapBackendStatus = (backendStatus: BackendJobStatus['status']): QueueItem['status'] => {
    switch (backendStatus) {
      case 'queued':
      case 'running':
        return 'processing';
      case 'completed':
        return 'completed';
      case 'failed':
      case 'cancelled':
        return 'error';
      default:
        return 'pending';
    }
  };

  // Update job status from backend
  const updateJobStatus = useCallback(async (jobId: string) => {
    try {
      const jobStatus = await apiClient.getJob(jobId);

      console.log(`📊 Статус задачи ${jobId}: ${jobStatus.status} - ${jobStatus.progress}% - ${jobStatus.stage}: ${jobStatus.message}`);

      setQueue(prev => {
        const itemExists = prev.some(item => item.jobId === jobId);
        if (!itemExists) return prev;

        return prev.map(item => {
          if (item.jobId === jobId) {
            const status = mapBackendStatus(jobStatus.status);
            
            return {
              ...item,
              status,
              progress: jobStatus.progress,
              stage: jobStatus.stage,
              message: jobStatus.error || jobStatus.message,
              filesCount: jobStatus.result?.moved || 0,
              processedCount: jobStatus.result?.copied || 0,
              clustersCount: jobStatus.result?.clusters || 0,
              noFacesCount: jobStatus.result?.no_faces || 0,
            };
          }
          return item;
        });
      });

      // Update overall status
      if (['queued', 'running'].includes(jobStatus.status)) {
        setStatus(prev => ({
          ...prev,
          isProcessing: true,
          currentItem: jobStatus.message || jobStatus.stage,
          overallProgress: jobStatus.progress,
        }));
      } else {
        // Если задача завершилась, проверяем остались ли другие активные задачи
        const allJobs = await apiClient.listJobs();
        const hasActiveJobs = allJobs.some(j => ['queued', 'running'].includes(j.status));
        
        setStatus(prev => ({
          ...prev,
          isProcessing: hasActiveJobs,
          completedItems: prev.completedItems + (['completed', 'failed', 'cancelled'].includes(jobStatus.status) ? 1 : 0),
        }));
      }

      // Логируем завершение задач
      if (['completed', 'failed', 'cancelled'].includes(jobStatus.status)) {
        const queueItem = queueRef.current.find(item => item.jobId === jobId);
        if (queueItem) {
          console.log(`✅ Задача "${queueItem.name}" завершена: ${jobStatus.status}`);
          if (jobStatus.result) {
            console.log(`📊 Результаты: ${jobStatus.result.moved} перемещено, ${jobStatus.result.copied} скопировано, ${jobStatus.result.clusters} кластеров`);
          }
          if (jobStatus.error) {
            console.error(`❌ Ошибка в задаче "${queueItem.name}": ${jobStatus.error}`);
          }
        }
      }

    } catch (error) {
      console.error('Failed to update job status:', error);
    }
  }, []);

  // Subscribe to job updates from backend
  useEffect(() => {
    let es: EventSource | null = null;

    const connectEventSource = () => {
      try {
        console.log('🔌 Подключение EventSource...');
        es = apiClient.subscribeToUpdates();

        // Handle named events from backend
        const handleUpdate = (event: MessageEvent) => {
          try {
            const data = JSON.parse(event.data);
            if (data.job_id) {
              console.log(`🔄 Получено обновление задачи ${data.job_id}`);
              updateJobStatus(data.job_id);
            }
          } catch (e) {
            console.debug('Malformed SSE data:', event.data);
          }
        };

        const handlePing = () => {
          // Keep-alive ping from server
          console.debug('SSE: ping');
        };

        es.addEventListener('update', handleUpdate as any);
        es.addEventListener('ping', handlePing as any);

        // Also handle generic messages just in case
        es.onmessage = handleUpdate;

        es.onerror = (error) => {
          console.warn('❌ EventSource connection error:', error);
        };

        es.onopen = () => {
          console.log('✅ EventSource connected');
        };
      } catch (error) {
        console.warn('❌ Failed to create EventSource - using polling mode:', error);
      }
    };

    // Connect EventSource after backend is ready
    setTimeout(connectEventSource, 2000);

    // Check for completed jobs every 2 seconds as backup
    const intervalId = setInterval(async () => {
      try {
        const jobs = await apiClient.listJobs();
        
        // Update all jobs in our queue from the backend state
        for (const job of jobs) {
          updateJobStatus(job.job_id);
        }

        const runningJobs = jobs.filter(job => ['queued', 'running'].includes(job.status));

        // Update overall processing status
        const hasProcessingJobs = runningJobs.length > 0;
        if (hasProcessingJobs) {
          const firstJob = runningJobs[0];
          setStatus(prev => ({
            ...prev,
            isProcessing: true,
            currentItem: firstJob.message || firstJob.stage,
            overallProgress: firstJob.progress,
          }));
        } else {
          setStatus(prev => ({
            ...prev,
            isProcessing: false,
          }));
        }

      } catch (error) {
        // Ignore errors in backup check, but log them
        console.debug('Backup job check failed:', error);
      }
    }, 2000);

    // Check for already completed jobs on mount
    const checkExistingJobs = async () => {
      try {
        console.log('🔄 Проверка существующих задач...');
        const jobs = await apiClient.listJobs();
        console.log('✅ Существующие задачи:', jobs);
        for (const job of jobs) {
          if (['completed', 'failed', 'cancelled'].includes(job.status)) {
            const queueItem = queueRef.current.find(item => item.jobId === job.job_id);
            if (queueItem && queueItem.status === 'processing') {
              console.log(`🔄 Обновление статуса завершенной задачи ${job.job_id}`);
              updateJobStatus(job.job_id);
            }
          }
        }
      } catch (error) {
        console.warn('❌ Failed to check existing jobs:', error);
        // Don't throw error, just log it
      }
    };

    // Delay initialization to ensure backend is ready
    const initTimeout = setTimeout(() => {
      checkExistingJobs();
    }, 1000);

    return () => {
      if (es) {
        es.close();
      }
      clearInterval(intervalId);
      clearTimeout(initTimeout);
    };
  }, [updateJobStatus]);

  const addToQueue = useCallback((handle: FileSystemDirectoryHandle, name: string, path: string) => {
    const id = `${name}-${Date.now()}`;
    console.log(`📋 Добавлена папка в очередь: "${name}" (${path})`);

    // Check if already exists
    setQueue(prev => {
      const exists = prev.some(item => item.path === path);
      if (exists) {
        toast.warning(`"${name}" уже в очереди`);
        return prev;
      }

      const newQueue = [...prev, {
        id,
        name,
        path,
        handle,
        status: 'pending' as const,
      }];
      toast.success(`"${name}" добавлена в очередь`);
      return newQueue;
    });
  }, []);

  const removeFromQueue = useCallback((id: string) => {
    setQueue(prev => prev.filter(item => item.id !== id));
  }, []);

  const clearQueue = useCallback(() => {
    setQueue(prev => prev.filter(item => item.status !== 'pending'));
  }, []);

  const clearCompleted = useCallback(() => {
    setQueue(prev => prev.filter(item => item.status === 'pending' || item.status === 'processing'));
  }, []);

  const processQueue = async () => {
    const pendingItems = queue.filter(item => item.status === 'pending');
    if (pendingItems.length === 0) return;

    console.log(`🚀 Начинаем обработку ${pendingItems.length} элементов из очереди`);

    setStatus({
      isProcessing: true,
      currentItem: null,
      totalItems: pendingItems.length,
      completedItems: 0,
      overallProgress: 0,
    });

    // Create jobs for each pending item
    for (const item of pendingItems) {
      try {
        console.log(`📝 Создание задачи для папки: ${item.path}`);
        const job = await apiClient.createJob({
          path: item.path,
          jointMode: 'combine',
          includeExcluded: false,
          postValidate: false,
        });

        console.log(`✅ Задача создана: ${job.job_id} для "${item.name}"`);

        // Update queue item with job ID and initial status from backend
        setQueue(prev => prev.map(q =>
          q.id === item.id ? { 
            ...q, 
            jobId: job.job_id, 
            status: mapBackendStatus(job.status),
            progress: job.progress,
            stage: job.stage,
            message: job.message
          } : q
        ));

        // If job is already running or completed, update overall status
        if (job.status === 'running' || job.status === 'completed') {
          setStatus(prev => ({
            ...prev,
            isProcessing: job.status === 'running',
            currentItem: job.message || job.stage,
            overallProgress: job.progress,
          }));
        }

        toast.success(`Задача создана для "${item.name}"`);

      } catch (error) {
        console.error(`❌ Ошибка при создании задачи для ${item.name}:`, error);
        setQueue(prev => prev.map(q =>
          q.id === item.id ? { ...q, status: 'error' } : q
        ));
        toast.error(`Ошибка при создании задачи для "${item.name}"`);
      }
    }
  };

  const queuePaths = queue.map(q => q.path);

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Header />

      <main className="flex-1 flex min-h-0">
        <div className="flex-1 flex flex-col bg-card/50">
          <FileBrowser
            queuePaths={queuePaths}
            onAddToQueue={addToQueue}
          />
        </div>

        <ProcessingQueue
          queue={queue}
          status={status}
          onRemoveFromQueue={removeFromQueue}
          onClearQueue={clearQueue}
          onClearCompleted={clearCompleted}
          onStartProcessing={processQueue}
          onAddToQueue={addToQueue}
        />
      </main>
    </div>
  );
};

export default Index;
