import { Camera } from "lucide-react";

export const Header = () => {
  return (
    <header className="h-16 border-b border-border bg-card px-6 flex items-center gap-3 shadow-card">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl gradient-primary flex items-center justify-center shadow-md">
          <Camera className="w-5 h-5 text-primary-foreground" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-foreground">PhotoMaster</h1>
          <p className="text-xs text-muted-foreground">Обработка фотографий</p>
        </div>
      </div>
    </header>
  );
};
