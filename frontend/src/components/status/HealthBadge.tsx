"use client";

import type { HealthStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Activity, Wifi, WifiOff } from "lucide-react";
import { Tooltip } from "@/components/ui/tooltip";

interface HealthBadgeProps {
  health: HealthStatus | null;
  className?: string;
}

export function HealthBadge({ health, className }: HealthBadgeProps) {
  if (!health) {
    return (
      <div className={cn("flex items-center gap-1.5 text-xs text-muted-foreground", className)}>
        <div className="w-2 h-2 rounded-full bg-muted-foreground animate-pulse" />
        <span>Checking...</span>
      </div>
    );
  }

  const statusConfig = {
    healthy: {
      color: "bg-success",
      text: "Connected",
      icon: Wifi,
    },
    degraded: {
      color: "bg-warning",
      text: "Degraded",
      icon: Activity,
    },
    offline: {
      color: "bg-destructive",
      text: "Offline",
      icon: WifiOff,
    },
  };

  const config = statusConfig[health.status];
  const Icon = config.icon;

  const tooltipText = health.status === "offline"
    ? "Backend is unreachable"
    : `v${health.version} | ${health.documents_indexed} docs indexed | Search: ${health.search_connected ? "connected" : "disconnected"}`;

  return (
    <Tooltip content={tooltipText}>
      <div className={cn("flex items-center gap-1.5 text-xs", className)}>
        <div className={cn("w-2 h-2 rounded-full", config.color)} />
        <Icon className="w-3 h-3 text-muted-foreground" />
        <span className="text-muted-foreground">{config.text}</span>
      </div>
    </Tooltip>
  );
}
