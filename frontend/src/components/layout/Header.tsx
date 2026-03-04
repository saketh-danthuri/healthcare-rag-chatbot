"use client";

import { Moon, Sun, Menu, Stethoscope } from "lucide-react";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";
import { HealthBadge } from "@/components/status/HealthBadge";
import type { HealthStatus } from "@/lib/types";

interface HeaderProps {
  health: HealthStatus | null;
  onToggleSidebar?: () => void;
  showMenuButton?: boolean;
}

export function Header({ health, onToggleSidebar, showMenuButton }: HeaderProps) {
  const { theme, setTheme } = useTheme();

  return (
    <header className="h-14 border-b bg-card flex items-center justify-between px-4 shrink-0">
      <div className="flex items-center gap-3">
        {showMenuButton && (
          <Button variant="ghost" size="icon" onClick={onToggleSidebar}>
            <Menu className="w-5 h-5" />
          </Button>
        )}
        <div className="flex items-center gap-2">
          <Stethoscope className="w-5 h-5 text-primary" />
          <h1 className="font-semibold text-base">Healthcare Ops AI</h1>
        </div>
      </div>

      <div className="flex items-center gap-4">
        <HealthBadge health={health} />
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label="Toggle theme"
        >
          <Sun className="w-4 h-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
          <Moon className="absolute w-4 h-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
        </Button>
      </div>
    </header>
  );
}
