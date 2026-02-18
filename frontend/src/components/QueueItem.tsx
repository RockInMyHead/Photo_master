import { Folder, X, CheckCircle2, AlertCircle, Loader2 } from "lucide-react";
import { QueueItem as QueueItemType } from "@/types/fileSystem";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";

interface QueueItemProps {
  item: QueueItemType;
  onRemove: (id: string) => void;
}

const STAGES = [
  { id: 'scan', label: 'Сканирование', min: 3, max: 8 },
  { id: 'init', label: 'Модели', min: 8, max: 25 },
  { id: 'detect', label: 'Лица', min: 25, max: 55 },
  { id: 'cluster', label: 'Кластеры', min: 55, max: 75 },
  { id: 'plan', label: 'План', min: 75, max: 90 },
  { id: 'distribute', label: 'Файлы', min: 90, max: 100 },
];

export const QueueItemComponent = ({ item, onRemove }: QueueItemProps) => {
  const getStatusIcon = () => {
    switch (item.status) {
      case 'processing':
        return <Loader2 className="w-4 h-4 text-primary animate-spin" />;
      case 'completed':
        return <CheckCircle2 className="w-4 h-4 text-success" />;
      case 'error':
        return <AlertCircle className="w-4 h-4 text-destructive" />;
      default:
        return null;
    }
  };

  const getStatusText = () => {
    switch (item.status) {
      case 'processing':
        return item.message || item.stage || 'Обработка...';
      case 'completed':
        if (item.filesCount !== undefined || item.processedCount !== undefined) {
          const total = (item.filesCount || 0) + (item.processedCount || 0);
          const clusters = item.clustersCount || 0;
          const noFaces = item.noFacesCount || 0;
          return (
            <div className="flex flex-col gap-1">
              <span className="text-success font-semibold">Готово: {total} фото обработано</span>
              <div className="flex gap-2 text-[10px] text-muted-foreground">
                <span>👤 Людей: {clusters}</span>
                <span>⚪️ Без лиц: {noFaces}</span>
              </div>
            </div>
          );
        }
        return 'Завершено';
      case 'error':
        if (item.message === 'Ошибка' && item.progress === 100) {
          return 'Ошибка: Недостаточно места на диске';
        }
        return item.message || 'Ошибка';
      default:
        return 'В очереди';
    }
  };

  return (
    <div className={`p-3 rounded-xl border transition-all duration-300 ${
      item.status === 'processing' 
        ? 'border-primary/50 bg-accent/30 shadow-sm' 
        : item.status === 'completed'
        ? 'border-success/30 bg-success/5'
        : item.status === 'error'
        ? 'border-destructive/30 bg-destructive/5'
        : 'border-border bg-card'
    }`}>
      <div className="flex items-start gap-3">
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 transition-colors ${
          item.status === 'processing' ? 'bg-primary text-primary-foreground' : 'bg-accent text-accent-foreground'
        }`}>
          <Folder className="w-4 h-4" />
        </div>
        
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-sm truncate">{item.name}</p>
          <p className="text-[10px] text-muted-foreground truncate mb-2 opacity-70">{item.path}</p>
          
          {item.status === 'processing' ? (
            <div className="space-y-3">
              <div className="flex flex-wrap gap-1.5">
                {STAGES.map((stage) => {
                  const progress = item.progress || 0;
                  const isCompleted = progress >= stage.max;
                  const isCurrent = progress >= stage.min && progress < stage.max;
                  
                  return (
                    <div 
                      key={stage.id}
                      className={`text-[9px] px-1.5 py-0.5 rounded-md border transition-all duration-500 flex items-center gap-1 ${
                        isCompleted 
                          ? "bg-primary/10 border-primary/20 text-primary opacity-100" 
                          : isCurrent
                          ? "bg-primary/5 border-primary/10 text-primary animate-pulse opacity-100 font-bold"
                          : "bg-transparent border-transparent text-muted-foreground opacity-20"
                      }`}
                    >
                      <span className="w-2.5 shrink-0 inline-block text-center">{isCompleted ? "✓" : ""}</span>
                      {stage.label}
                    </div>
                  );
                })}
              </div>
              
              <div className="space-y-1">
                <div className="flex justify-between items-center text-[10px]">
                  <span className="text-primary font-medium animate-pulse">{getStatusText()}</span>
                  <span className="text-muted-foreground">{item.progress || 0}%</span>
                </div>
                <Progress value={item.progress || 0} className="h-1.5 transition-all duration-500" />
              </div>
            </div>
          ) : (
            <div className="flex items-start gap-2 mt-1">
              <div className="mt-0.5">{getStatusIcon()}</div>
              <div className="text-xs text-muted-foreground font-medium">{getStatusText()}</div>
            </div>
          )}
        </div>
        
        {item.status === 'pending' && (
          <Button
            variant="ghost"
            size="icon"
            className="shrink-0 h-8 w-8 text-muted-foreground hover:text-destructive transition-colors"
            onClick={() => onRemove(item.id)}
          >
            <X className="w-4 h-4" />
          </Button>
        )}
      </div>
    </div>
  );
};
