"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Bot, Zap, BarChart2, Settings, LogOut, User, Bell } from "lucide-react";
import { authLogout } from "@/lib/api";

const navItems = [
  { icon: LayoutDashboard, label: "仪表盘", href: "/" },
  { icon: Bot, label: "策略", href: "/strategies" },
  { icon: Zap, label: "触发历史", href: "/triggers" },
  { icon: BarChart2, label: "大盘", href: "/market" },
  { icon: Bell, label: "消息", href: "/notifications" },
  { icon: Settings, label: "设置", href: "/settings" },
];

const mobileNavItems = navItems.filter(
  (item) => item.href !== "/notifications"
);

interface SidebarProps {
  username?: string | null;
}

export function Sidebar({ username }: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname === href || pathname?.startsWith(`${href}/`);

  async function handleLogout() {
    try {
      await authLogout();
    } finally {
      router.push("/login");
    }
  }

  return (
    <>
      {/* 桌面端侧边栏 */}
      <aside className="hidden md:flex w-64 bg-slate-900/80 backdrop-blur-sm border-r border-slate-800 flex-col">
        <div className="px-6 py-5">
          <h1 className="text-lg font-bold text-white flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center">
              <Bot className="w-4.5 h-4.5 text-white" />
            </div>
            AutoTrade
          </h1>
          <p className="text-[11px] text-slate-500 mt-1 ml-[42px]">加密货币自动交易</p>
        </div>

        <nav className="flex-1 px-3 mt-2">
          <ul className="space-y-1">
            {navItems.map((item) => {
              const active = isActive(item.href);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all ${
                      active
                        ? "bg-blue-600/15 text-blue-400 font-medium"
                        : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
                    }`}
                  >
                    <item.icon className={`w-[18px] h-[18px] ${active ? "text-blue-400" : ""}`} />
                    {item.label}
                    {active && (
                      <div className="ml-auto w-1.5 h-1.5 rounded-full bg-blue-400" />
                    )}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="p-3 mx-3 mb-3 rounded-lg bg-slate-800/50 border border-slate-700/50">
          {username && (
            <div className="flex items-center gap-2.5 mb-2">
              <div className="w-7 h-7 rounded-full bg-slate-700 flex items-center justify-center">
                <User className="w-3.5 h-3.5 text-slate-300" />
              </div>
              <span className="text-sm text-slate-300 truncate font-medium">{username}</span>
            </div>
          )}
          <button
            onClick={handleLogout}
            className="flex items-center gap-2 w-full px-2 py-1.5 text-slate-500 hover:text-red-400 transition-colors text-xs rounded"
          >
            <LogOut className="w-3.5 h-3.5" />
            退出登录
          </button>
        </div>
      </aside>

      {/* 移动端底部导航栏 */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-slate-900/95 backdrop-blur-md border-t border-slate-800 pb-[env(safe-area-inset-bottom)]">
        <ul className="flex items-center justify-around">
          {mobileNavItems.map((item) => {
            const active = isActive(item.href);
            return (
              <li key={item.href} className="flex-1">
                <Link
                  href={item.href}
                  className={`flex flex-col items-center gap-0.5 py-2 transition-colors relative ${
                    active
                      ? "text-blue-400"
                      : "text-slate-500 hover:text-slate-300"
                  }`}
                >
                  {active && (
                    <div className="absolute -top-px left-1/2 -translate-x-1/2 w-6 h-0.5 bg-blue-400 rounded-full" />
                  )}
                  <item.icon className="w-5 h-5" />
                  <span className="text-[10px]">{item.label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </>
  );
}
