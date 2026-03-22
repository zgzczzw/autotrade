"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Sidebar } from "@/components/sidebar";
import { authMe, fetchSettings } from "@/lib/api";
import { setTimezone } from "@/lib/utils";

const AUTH_PATHS = ["/login", "/register"];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [username, setUsername] = useState<string | null>(null);
  const isAuthPage = AUTH_PATHS.includes(pathname);

  useEffect(() => {
    if (!isAuthPage) {
      authMe().then((res) => {
        setUsername(res.user?.username ?? null);
      }).catch(() => {});
      fetchSettings().then((data: any) => {
        if (data?.timezone) setTimezone(data.timezone);
      }).catch(() => {});
    }
  }, [isAuthPage]);

  if (isAuthPage) {
    return <>{children}</>;
  }

  return (
    <div className="flex h-dvh">
      <Sidebar username={username} />
      <main className="flex-1 overflow-auto p-4 md:p-8 pb-[calc(5rem+env(safe-area-inset-bottom))] md:pb-8">
        {children}
      </main>
    </div>
  );
}
