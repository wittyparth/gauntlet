"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useRouter } from "next/navigation";

import {
  ThemeTogglerButton,
  ThemeTogglerButtonIcon,
  type ThemeSelection,
  type Resolved,
} from "@/components/animate-ui/buttons/theme-toggler";
import { ChevronDown } from "@/components/animate-ui/icons/chevron-down";
import { LogOut } from "@/components/animate-ui/icons/log-out";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SidebarMenuButton } from "@/components/ui/sidebar";
import { useCurrentProject } from "@/lib/api/hooks/read";

export function AccountMenu() {
  const { project } = useCurrentProject();
  const { theme, resolvedTheme, setTheme } = useTheme();
  const router = useRouter();

  async function signOut() {
    await fetch("/api/session", { method: "DELETE" });
    router.push("/login");
    router.refresh();
  }

  return (
    <div className="flex items-center gap-1">
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <SidebarMenuButton size="lg" tooltip="Account" aria-label="Account menu" className="data-popup-open:bg-sidebar-accent" />
          }
        >
          <span className="bg-sidebar-primary text-sidebar-primary-foreground flex size-6 shrink-0 items-center justify-center rounded-md text-xs font-semibold">
            {(project?.name ?? "G").slice(0, 1).toUpperCase()}
          </span>
          <span className="flex min-w-0 flex-1 flex-col text-left leading-tight">
            <span className="truncate text-sm font-medium">{project?.name ?? "Project"}</span>
            <span className="text-muted-foreground text-xs">Project</span>
          </span>
          <ChevronDown size={14} />
        </DropdownMenuTrigger>
        <DropdownMenuContent side="top" align="start" className="w-56">
          <DropdownMenuGroup>
            <DropdownMenuLabel>{project?.name ?? "Project"}</DropdownMenuLabel>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={signOut}>
            <LogOut size={14} animateOnHover /> Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <ThemeTogglerButton
        variant="ghost"
        size="sm"
        aria-label="Toggle theme"
        theme={(theme ?? "dark") as ThemeSelection}
        resolvedTheme={(resolvedTheme ?? "dark") as Resolved}
        setTheme={setTheme}
      >
        <ThemeTogglerButtonIcon light={<Sun />} dark={<Moon />} system={<Monitor />} />
      </ThemeTogglerButton>
    </div>
  );
}
