import { Play, Trash2, ListChecks, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { QueueItemComponent } from "./QueueItem";
import { QueueItem, ProcessingStatus } from "@/types/fileSystem";
import { useState } from "react";
import { toast } from "sonner";

interface ProcessingQueueProps {
  queue: QueueItem[];
  status: ProcessingStatus;
  onRemoveFromQueue: (id: string) => void;
  onClearQueue: () => void;
  onClearCompleted: () => void;
  onStartProcessing: (includeShared: boolean) => void;
  onAddToQueue: (handle: FileSystemDirectoryHandle, name: string, path: string) => void;
}

export const ProcessingQueue = ({
  queue,
  status,
  onRemoveFromQueue,
  onClearQueue,
  onClearCompleted,
  onStartProcessing,
  onAddToQueue,
}: ProcessingQueueProps) => {
  const [isDraggingOver, setIsDraggingOver] = useState(false);
  const [includeShared, setIncludeShared] = useState(false);
  const pendingCount = queue.filter(q => q.status === 'pending').length;
  const completedCount = queue.filter(q => q.status === 'completed').length;
  const errorCount = queue.filter(q => q.status === 'error').length;
  const finishedCount = completedCount + errorCount;

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
    if (!isDraggingOver) setIsDraggingOver(true);
  };

  const handleDragLeave = () => {
    setIsDraggingOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDraggingOver(false);
    
    try {
      const data = JSON.parse(e.dataTransfer.getData("application/json"));
      if (data && data.name && data.path && data.type === 'directory') {
        console.log(`🎯 Перетянута папка: ${data.name}`);
        // For backend integration, we don't need real handles
        const mockHandle = {} as FileSystemDirectoryHandle;
        onAddToQueue(mockHandle, data.name, data.path);
      } else if (data && data.type !== 'directory') {
        toast.error("В очередь можно добавлять только папки");
      }
    } catch (err) {
      console.error("Ошибка при обработке Drop:", err);
    }
  };

  return (
    <div 
      className={`w-80 border-l border-border bg-card flex flex-col transition-colors duration-200 relative ${
        isDraggingOver ? 'bg-primary/5 ring-2 ring-primary/20 ring-inset' : ''
      }`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <div className="p-4 border-b border-border">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <ListChecks className="w-5 h-5 text-primary" />
            <h2 className="font-semibold">Очередь</h2>
          </div>
          {queue.length > 0 && (
            <span className="px-2 py-0.5 rounded-full bg-accent text-accent-foreground text-xs font-medium">
              {queue.length}
            </span>
          )}
        </div>
        
        <div className="space-y-2">
          <div className="flex items-center space-x-2">
            <Checkbox
              id="includeShared"
              checked={includeShared}
              onCheckedChange={(checked) => setIncludeShared(checked === true)}
            />
            <Label
              htmlFor="includeShared"
              className="text-sm font-normal cursor-pointer"
            >
              Общая фотография
            </Label>
          </div>
          
          <div className="flex gap-2">
            <Button
              variant="primary"
              className="flex-1"
              disabled={pendingCount === 0 || status.isProcessing}
              onClick={() => onStartProcessing(includeShared)}
            >
              <Play className="w-4 h-4" />
              {status.isProcessing ? 'Обработка...' : 'Обработать'}
            </Button>

          <Button
            variant="outline"
            size="icon"
            disabled={queue.length === 0 || status.isProcessing}
            onClick={onClearQueue}
            title="Очистить ожидающие"
          >
            <Trash2 className="w-4 h-4" />
          </Button>

          {finishedCount > 0 && (
            <Button
              variant="outline"
              size="icon"
              disabled={status.isProcessing}
              onClick={onClearCompleted}
              title="Очистить завершенные"
              className="text-orange-600 hover:text-orange-700"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </Button>
          )}
          </div>
        </div>
      </div>

      {/* Drag and Drop Hint */}
      {isDraggingOver && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-primary/10 backdrop-blur-[1px] pointer-events-none border-2 border-dashed border-primary m-2 rounded-xl">
          <Download className="w-10 h-10 text-primary animate-bounce mb-2" />
          <p className="text-sm font-semibold text-primary">Отпустите, чтобы добавить</p>
        </div>
      )}

      {/* Status Summary */}
      {status.isProcessing && (
        <div className="p-4 border-b border-border bg-accent/50">
          <div className="flex items-center justify-between text-sm mb-2">
            <div className="flex flex-col">
              <span className="text-muted-foreground text-[10px] uppercase tracking-wider font-bold">Общий прогресс</span>
              <span className="text-primary font-medium text-xs">{status.currentItem || 'Подготовка...'}</span>
            </div>
            <span className="font-bold text-primary">{status.completedItems}/{status.totalItems}</span>
          </div>
          <div className="h-2 bg-secondary rounded-full overflow-hidden shadow-inner">
            <div 
              className="h-full gradient-primary transition-all duration-1000 rounded-full"
              style={{ width: `${status.overallProgress}%` }}
            />
          </div>
        </div>
      )}

      {/* Queue Items */}
      <div className="flex-1 overflow-y-auto p-4">
        {queue.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-center">
            <div className="w-12 h-12 rounded-xl bg-secondary flex items-center justify-center mb-3">
              <ListChecks className="w-6 h-6 text-muted-foreground" />
            </div>
            <p className="text-sm text-muted-foreground">
              Добавьте папки для обработки
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {queue.map((item) => (
              <QueueItemComponent
                key={item.id}
                item={item}
                onRemove={onRemoveFromQueue}
              />
            ))}
          </div>
        )}
      </div>

      {/* Completed Summary */}
      {finishedCount > 0 && !status.isProcessing && (
        <div className="p-4 border-t border-border bg-success/5">
          <div className="flex justify-center items-center gap-4 text-sm">
            {completedCount > 0 && (
              <span className="text-success font-medium">
                ✓ Успешно: {completedCount}
              </span>
            )}
            {errorCount > 0 && (
              <span className="text-destructive font-medium">
                ❌ Ошибок: {errorCount}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
