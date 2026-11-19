"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { Bot } from "@/components/animate-ui/icons/bot";
import { List } from "@/components/animate-ui/icons/list";
import { Play } from "@/components/animate-ui/icons/play";
import { Settings } from "@/components/animate-ui/icons/settings";
import { Zap } from "@/components/animate-ui/icons/zap";
import { AccountMenu } from "@/components/shared/account-menu";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
} from "@/components/ui/sidebar";

const NAV = [
  { href: "/agents", label: "Agents", Icon: Bot },
  { href: "/scenarios", label: "Scenarios", Icon: List },
  { href: "/runs", label: "Runs", Icon: Play },
] as const;

export function AppShell({ children, defaultOpen }: { children: ReactNode; defaultOpen: boolean }) {
  const pathname = usePathname();
  return (
    <SidebarProvider defaultOpen={defaultOpen}>
      <Sidebar collapsible="icon">
        <SidebarHeader>
          <div className="flex h-8 items-center gap-2 px-2 text-sm font-semibold">
            <Zap size={16} />
            <span>Gauntlet</span>
          </div>
        </SidebarHeader>
        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupLabel>Test</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {NAV.map(({ href, label, Icon }) => {
                  const active = pathname === href || pathname.startsWith(`${href}/`);
                  return (
                    <SidebarMenuItem key={href}>
                      <SidebarMenuButton
                        isActive={active}
                        tooltip={label}
                        render={<Link href={href} aria-current={active ? "page" : undefined} />}
                      >
                        <Icon size={16} animateOnHover />
                        <span>{label}</span>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  );
                })}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
          <SidebarGroup>
            <SidebarGroupLabel>Settings</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                <SidebarMenuItem>
                  <SidebarMenuButton
                    isActive={pathname.startsWith("/settings/models")}
                    tooltip="Models"
                    render={<Link href="/settings/models" aria-current={pathname.startsWith("/settings/models") ? "page" : undefined} />}
                  >
                    <Settings size={16} animateOnHover />
                    <span>Models</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
        <SidebarFooter>
          <AccountMenu />
        </SidebarFooter>
        <SidebarRail />
      </Sidebar>
      <SidebarInset className="min-w-0">{children}</SidebarInset>
    </SidebarProvider>
  );
}
