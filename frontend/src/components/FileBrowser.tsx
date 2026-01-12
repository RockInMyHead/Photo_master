import { useState, useEffect } from "react";
import { FolderOpen, RefreshCw, Home, File, Plus, Check, Edit2, ZoomIn, ZoomOut, Maximize2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Breadcrumbs } from "./Breadcrumbs";
import { apiClient, previewUrl } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { Slider } from "@/components/ui/slider";

interface FileBrowserProps {
  queueIds: string[];
  onAddToQueue: (handle: FileSystemDirectoryHandle, name: string, path: string) => void;
}

interface ServerFileItem {
  name: string;
  path: string;
  type: 'file' | 'directory';
  size?: number;
  modified?: string;
  preview_path?: string;
}

export const FileBrowser = ({ queueIds, onAddToQueue }: FileBrowserProps) => {
  const [roots, setRoots] = useState<string[]>([]);
  const [currentPath, setCurrentPath] = useState<string>("");
  const [items, setItems] = useState<ServerFileItem[]>([]);
  const [pathSegments, setPathSegments] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isInitialized, setIsInitialized] = useState(false);
  const [dragOverFolder, setDragOverFolder] = useState<string | null>(null);
  const [renamingPath, setRenamingPath] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [scale, setScale] = useState(1); // 0.8 to 1.5

  // Initialize with root directories
  useEffect(() => {
    const initializeBrowser = async () => {
      try {
        console.log("🔄 Загрузка корневых директорий...");
        const rootDirs = await apiClient.listRoots();
        console.log("✅ Корневые директории загружены:", rootDirs);
        setRoots(rootDirs);
        setIsInitialized(true);
      } catch (error) {
        console.error("❌ Failed to load roots:", error);
        // Set default roots if API fails
        const defaultRoots = ["/", "/Users", "/Volumes"];
        console.log("🔄 Используем стандартные корневые директории:", defaultRoots);
        setRoots(defaultRoots);
        setIsInitialized(true);
      }
    };

    // Add small delay to ensure backend is ready
    setTimeout(initializeBrowser, 500);
  }, []);

  const loadDirectory = async (path: string) => {
    setIsLoading(true);
    
    // Normalize path for Windows/Unix
    let normalizedPath = path;
    const isWindowsRoot = /^[A-Za-z]:/.test(path);
    const hasLeadingSlash = path.startsWith('/');
    
    if (isWindowsRoot) {
      // It's a Windows drive, keep it as is (e.g. "D:/")
      normalizedPath = path;
    } else if (hasLeadingSlash) {
      // It already has a slash, but if it's "/D:/", fix it for Windows
      if (path.length > 2 && path[2] === ':' && /^\/[A-Za-z]:/.test(path)) {
        normalizedPath = path.substring(1);
      } else {
        normalizedPath = path;
      }
    } else {
      // Unix-like or relative, add leading slash
      normalizedPath = '/' + path;
    }

    console.log(`📂 Загрузка директории: ${normalizedPath}`);
    try {
      const dirItems = await apiClient.listDirectory(normalizedPath);
      setItems(dirItems);
      setCurrentPath(normalizedPath);
      
      // Handle path segments for both Windows and Unix paths
      const segments = /^[A-Za-z]:/.test(normalizedPath) ?
        normalizedPath.split(/[/\\]/).filter(Boolean) :
        normalizedPath.split('/').filter(Boolean);
        
      setPathSegments(segments);
      console.log(`📂 Загружено ${dirItems.length} элементов в ${normalizedPath}`);
    } catch (error) {
      console.error("❌ Ошибка загрузки директории:", normalizedPath, error);
      setItems([]);
    } finally {
      setIsLoading(false);
    }
  };

  const navigateToFolder = (item: ServerFileItem) => {
    if (renamingPath) return; // Prevent navigation while renaming
    if (item.type === 'directory') {
      loadDirectory(item.path);
    }
  };

  const navigateToBreadcrumb = (index: number) => {
    if (index === -1) {
      // Navigate to root selection
      setCurrentPath("");
      setPathSegments([]);
      setItems([]);
      return;
    }

    const isWindowsPath = pathSegments.length > 0 && pathSegments[0].includes(':');
    let newPath = '';
    
    if (isWindowsPath) {
      newPath = pathSegments.slice(0, index + 1).join('/');
      // Ensure it has a trailing slash if it's just the drive letter
      if (index === 0 && !newPath.endsWith('/')) {
        newPath += '/';
      }
    } else {
      newPath = '/' + pathSegments.slice(0, index + 1).join('/');
    }
    
    loadDirectory(newPath);
  };

  const handleAddToQueue = (item: ServerFileItem) => {
    console.log(`➕ Добавление в очередь: ${item.name} (${item.path})`);
    // For backend integration, we don't need real handles
    const mockHandle = {} as FileSystemDirectoryHandle;
    onAddToQueue(mockHandle, item.name, item.path);
  };

  const handleDragStart = (e: React.DragEvent, item: ServerFileItem) => {
    if (renamingPath) return;
    e.dataTransfer.setData("application/json", JSON.stringify({
      name: item.name,
      path: item.path,
      type: item.type
    }));
    e.dataTransfer.effectAllowed = "all";
    console.log(`📂 Начато перетаскивание: ${item.name}`);
  };

  const handleDragOverFolder = (e: React.DragEvent, item: ServerFileItem) => {
    if (item.type !== 'directory' || renamingPath) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    if (dragOverFolder !== item.path) {
      setDragOverFolder(item.path);
    }
  };

  const handleDragLeaveFolder = () => {
    setDragOverFolder(null);
  };

  const handleDropMove = async (e: React.DragEvent, targetItem: ServerFileItem) => {
    e.preventDefault();
    setDragOverFolder(null);
    
    if (targetItem.type !== 'directory') return;
    
    try {
      const data = JSON.parse(e.dataTransfer.getData("application/json"));
      if (!data || !data.path || data.path === targetItem.path) return;
      
      console.log(`🎯 Перемещение: ${data.name} -> ${targetItem.name}`);
      const res = await apiClient.move(data.path, targetItem.path);
      
      if (res.ok) {
        toast.success(`Перемещено: ${data.name} в ${targetItem.name}`);
        // Refresh current directory
        loadDirectory(currentPath);
      }
    } catch (err) {
      console.error("Ошибка при перемещении:", err);
      toast.error(`Ошибка перемещения: ${err instanceof Error ? err.message : 'Неизвестная ошибка'}`);
    }
  };

  const startRenaming = (e: React.MouseEvent, item: ServerFileItem) => {
    e.stopPropagation();
    setRenamingPath(item.path);
    setNewName(item.name);
  };

  const cancelRenaming = () => {
    setRenamingPath(null);
    setNewName("");
  };

  const handleRename = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!renamingPath || !newName.trim()) return;

    try {
      console.log(`📝 Переименование: ${renamingPath} -> ${newName}`);
      const res = await apiClient.rename(renamingPath, newName.trim());
      if (res.ok) {
        toast.success("Переименовано");
        loadDirectory(currentPath);
      }
    } catch (err) {
      console.error("Ошибка при переименовании:", err);
      toast.error(`Ошибка: ${err instanceof Error ? err.message : 'Неизвестная ошибка'}`);
    } finally {
      cancelRenaming();
    }
  };

  if (!isInitialized) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <RefreshCw className="w-6 h-6 text-muted-foreground animate-spin" />
      </div>
    );
  }

  if (!currentPath) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-6 p-8">
        <div className="w-24 h-24 rounded-2xl bg-accent flex items-center justify-center">
          <Home className="w-12 h-12 text-accent-foreground" />
        </div>
        <div className="text-center">
          <h2 className="text-xl font-semibold mb-2">Выберите диск</h2>
          <p className="text-muted-foreground text-sm max-w-xs">
            Выберите корневую папку для просмотра файловой системы сервера
          </p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4 w-full max-w-2xl">
          {roots.map((root) => (
            <Card
              key={root}
              className="cursor-pointer transition-all duration-200 hover:shadow-lg hover:scale-105"
              onClick={() => {
                console.log(`🏠 Выбор корневой директории: ${root}`);
                loadDirectory(root);
              }}
            >
              <CardContent className="p-6 text-center">
                <div className="flex flex-col items-center gap-3">
                  <div className="w-16 h-16 rounded-2xl bg-blue-100 text-blue-600 dark:bg-blue-900 dark:text-blue-300 flex items-center justify-center">
                    <FolderOpen className="w-8 h-8" />
                  </div>
                  <span className="font-medium">{root}</span>
                  <span className="text-sm text-muted-foreground">Корневой диск</span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-0" style={{ fontSize: `${scale}rem` }}>
      <div className="p-4 border-b border-border flex items-center justify-between gap-4">
        <Breadcrumbs path={pathSegments} onNavigate={navigateToBreadcrumb} />
        
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-3 bg-accent/50 rounded-lg px-4 py-2 border border-border">
            <ZoomOut className="w-5 h-5 text-muted-foreground cursor-pointer hover:text-foreground" onClick={() => setScale(s => Math.max(0.7, s - 0.1))} />
            <Slider 
              value={[scale]} 
              min={0.7} 
              max={5} 
              step={0.1} 
              onValueChange={(v) => setScale(v[0])}
              className="w-72"
            />
            <ZoomIn className="w-5 h-5 text-muted-foreground cursor-pointer hover:text-foreground" onClick={() => setScale(s => Math.min(5, s + 0.1))} />
          </div>

        <Button
          variant="ghost"
          size="icon"
          onClick={() => loadDirectory(currentPath)}
          disabled={isLoading}
        >
          <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
        </Button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {isLoading ? (
          <div className="flex items-center justify-center h-32">
            <RefreshCw className="w-6 h-6 text-muted-foreground animate-spin" />
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-muted-foreground">
            <p>Папка пуста</p>
          </div>
        ) : (
          <div 
            className="grid gap-3"
            style={{ 
              gridTemplateColumns: `repeat(auto-fill, minmax(${Math.max(80, scale * 100)}px, 1fr))`
            }}
          >
            {items.map((item) => (
              <Card
                key={item.path}
                draggable={!renamingPath}
                onDragStart={(e) => handleDragStart(e, item)}
                onDragOver={(e) => handleDragOverFolder(e, item)}
                onDragLeave={handleDragLeaveFolder}
                onDrop={(e) => handleDropMove(e, item)}
                className={`group cursor-pointer transition-all duration-200 hover:shadow-lg hover:scale-[1.02] border-2 ${
                  queueIds.includes(item.name) ? 'ring-2 ring-green-500 border-green-500' : 
                  dragOverFolder === item.path ? 'ring-2 ring-blue-500 border-blue-500 bg-blue-50/50' :
                  'hover:border-blue-300'
                }`}
                onClick={() => navigateToFolder(item)}
              >
                <CardContent className="p-3 text-center">
                  <div className="flex flex-col items-center gap-2">
                    <div 
                      className={`rounded-lg flex items-center justify-center overflow-hidden ${
                      item.type === 'directory'
                        ? "bg-blue-100 text-blue-600 dark:bg-blue-900 dark:text-blue-300"
                        : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"
                      }`}
                      style={{ 
                        width: `${Math.max(2, scale * 2.5)}rem`, 
                        height: `${Math.max(2, scale * 2.5)}rem` 
                      }}
                    >
                      {item.preview_path ? (
                        <img 
                          src={previewUrl(item.preview_path, 128)} 
                          alt={item.name}
                          className="w-full h-full object-cover"
                          loading="lazy"
                        />
                      ) : item.type === 'directory' ? (
                        <FolderOpen style={{ width: `${scale * 1.25}rem`, height: `${scale * 1.25}rem` }} />
                      ) : (
                        <File style={{ width: `${scale * 1.25}rem`, height: `${scale * 1.25}rem` }} />
                      )}
                    </div>

                    {renamingPath === item.path ? (
                      <form onSubmit={handleRename} className="w-full px-1" onClick={e => e.stopPropagation()}>
                        <Input
                          autoFocus
                          value={newName}
                          onChange={e => setNewName(e.target.value)}
                          onBlur={cancelRenaming}
                          onKeyDown={e => e.key === 'Escape' && cancelRenaming()}
                          className="h-6 px-1 py-0"
                          style={{ fontSize: '0.8em' }}
                        />
                      </form>
                    ) : (
                      <div className="flex items-center gap-1 group/name w-full justify-center">
                        <span className="font-medium text-center leading-tight line-clamp-2 px-1" style={{ fontSize: '0.8em' }} title={item.name}>
                      {item.name}
                    </span>
                        <Button 
                          variant="ghost" 
                          size="icon" 
                          className="w-4 h-4 p-0 opacity-0 group-hover/name:opacity-100 transition-opacity"
                          onClick={(e) => startRenaming(e, item)}
                        >
                          <Edit2 className="w-2.5 h-2.5" />
                        </Button>
                      </div>
                    )}

                    {item.size && (
                      <span className="text-muted-foreground" style={{ fontSize: '0.7em' }}>
                        {item.size > 1024 * 1024
                          ? `${(item.size / (1024 * 1024)).toFixed(1)} MB`
                          : item.size > 1024
                          ? `${(item.size / 1024).toFixed(1)} KB`
                          : `${item.size} B`
                        }
                      </span>
                    )}

                    {item.type === 'directory' && (
                      <Button
                        variant={queueIds.includes(item.name) ? "default" : "ghost"}
                        size="sm"
                        className={`opacity-0 group-hover:opacity-100 transition-opacity w-full h-6 ${
                          queueIds.includes(item.name) ? 'opacity-100 bg-green-600 hover:bg-green-700' : ''
                        }`}
                        style={{ fontSize: '0.7em' }}
                        onClick={(e) => {
                          e.stopPropagation();
                          if (!queueIds.includes(item.name)) {
                            handleAddToQueue(item);
                          }
                        }}
                        disabled={queueIds.includes(item.name)}
                      >
                        {queueIds.includes(item.name) ? (
                          <>
                            <Check className="w-3 h-3 mr-1" />
                            В очереди
                          </>
                        ) : (
                          <>
                            <Plus className="w-3 h-3 mr-1" />
                            Добавить
                          </>
                        )}
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
