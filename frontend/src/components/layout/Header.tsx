"use client";

import { useEffect, useState } from "react";
import { Moon, Sun, Menu, Stethoscope, ShieldCheck, Download } from "lucide-react";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";
import { HealthBadge } from "@/components/status/HealthBadge";
import { getRole, setRole } from "@/lib/role";
import type { HealthStatus, UserRole } from "@/lib/types";

interface HeaderProps {
  health: HealthStatus | null;
  onToggleSidebar?: () => void;
  showMenuButton?: boolean;
  /** Download the active conversation; omit/undefined to hide the button. */
  onExportConversation?: () => void;
}

export function Header({
  health,
  onToggleSidebar,
  showMenuButton,
  onExportConversation,
}: HeaderProps) {
  const { theme, setTheme } = useTheme();

  // Role governs server-side PHI reveal on the assistant's output. Initialized
  // after mount to avoid SSR/localStorage hydration mismatch.
  const [role, setRoleState] = useState<UserRole>("general");
  useEffect(() => setRoleState(getRole()), []);

  const changeRole = (next: UserRole) => {
    setRole(next);
    setRoleState(next);
  };

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
        {/* Permission role: clinician sees unmasked PHI, general sees masked. */}
        <div
          className="flex items-center rounded-md border p-0.5 text-xs"
          role="group"
          aria-label="PHI visibility role"
        >
          <ShieldCheck className="w-3.5 h-3.5 text-muted-foreground ml-1.5 mr-0.5" />
          <button
            type="button"
            onClick={() => changeRole("general")}
            aria-pressed={role === "general"}
            className={`px-2 py-1 rounded transition-colors ${
              role === "general"
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            General
          </button>
          <button
            type="button"
            onClick={() => changeRole("clinician")}
            aria-pressed={role === "clinician"}
            className={`px-2 py-1 rounded transition-colors ${
              role === "clinician"
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Clinician
          </button>
        </div>
        <HealthBadge health={health} />
        {onExportConversation && (
          <Button
            variant="ghost"
            size="icon"
            onClick={onExportConversation}
            aria-label="Export conversation"
            title="Export conversation as Markdown"
          >
            <Download className="w-4 h-4" />
          </Button>
        )}
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
