import { ChevronRight, Home } from "lucide-react";

interface BreadcrumbsProps {
  path: string[];
  onNavigate: (index: number) => void;
  scale?: number;
}

export const Breadcrumbs = ({ path, onNavigate }: BreadcrumbsProps) => {
  return (
    <nav className="flex items-center gap-1 overflow-x-auto pb-1 text-sm">
      <button
        onClick={() => onNavigate(-1)}
        className="flex items-center gap-1 px-2 py-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
      >
        <Home className="w-4 h-4" />
      </button>
      
      {path.map((segment, index) => (
        <div key={index} className="flex items-center gap-1 animate-fade-in">
          <ChevronRight className="w-4 h-4 text-muted-foreground/50" />
          <button
            onClick={() => onNavigate(index)}
            className={`px-2 py-1 rounded-md transition-colors truncate ${
              index === path.length - 1
                ? "text-foreground font-medium bg-accent"
                : "text-muted-foreground hover:text-foreground hover:bg-accent"
            }`}
            style={{ maxWidth: '300px' }}
          >
            {segment}
          </button>
        </div>
      ))}
    </nav>
  );
};
