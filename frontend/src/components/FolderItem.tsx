import { Folder, File, Plus, Check } from "lucide-react";
import { FileItem } from "@/types/fileSystem";
import { Button } from "@/components/ui/button";

interface FolderItemProps {
  item: FileItem;
  onNavigate: (handle: FileSystemDirectoryHandle) => void;
  onAddToQueue: (handle: FileSystemDirectoryHandle, name: string) => void;
  isInQueue: boolean;
}

export const FolderItem = ({ item, onNavigate, onAddToQueue, isInQueue }: FolderItemProps) => {
  const isDirectory = item.kind === 'directory';
  
  const handleClick = () => {
    if (isDirectory) {
      onNavigate(item.handle as FileSystemDirectoryHandle);
    }
  };

  const handleAddToQueue = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isDirectory && !isInQueue) {
      onAddToQueue(item.handle as FileSystemDirectoryHandle, item.name);
    }
  };

  return (
    <div
      onClick={handleClick}
      className={`group flex items-center gap-3 p-3 rounded-xl border border-transparent transition-all duration-200 animate-fade-in ${
        isDirectory 
          ? "hover:bg-accent hover:border-border cursor-pointer" 
          : "bg-secondary/50"
      }`}
    >
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
        isDirectory 
          ? "bg-accent text-accent-foreground" 
          : "bg-secondary text-muted-foreground"
      }`}>
        {isDirectory ? (
          <Folder className="w-5 h-5" />
        ) : (
          <File className="w-5 h-5" />
        )}
      </div>
      
      <span className="flex-1 truncate text-sm font-medium">{item.name}</span>
      
      {isDirectory && (
        <Button
          variant={isInQueue ? "success" : "ghost"}
          size="icon"
          className={`opacity-0 group-hover:opacity-100 transition-opacity ${isInQueue ? 'opacity-100' : ''}`}
          onClick={handleAddToQueue}
          disabled={isInQueue}
        >
          {isInQueue ? (
            <Check className="w-4 h-4" />
          ) : (
            <Plus className="w-4 h-4" />
          )}
        </Button>
      )}
    </div>
  );
};
