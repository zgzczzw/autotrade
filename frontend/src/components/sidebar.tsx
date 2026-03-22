"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Bot, History, BarChart2, Settings, LogOut, User } from "lucide-react";
import { authLogout } from "@/lib/api";

const navItems = [
  { icon: LayoutDashboard, label: "仪表盘", href: "/" },
  { icon: Bot, label: "策略", href: "/strategies" },
  { icon: History, label: "日志", href: "/triggers" },
  { icon: BarChart2, label: "大盘", href: "/market" },
  { icon: Settings, label: "设置", href: "/settings" },
];

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
      <aside className="hidden md:flex w-64 bg-slate-900 border-r border-slate-800 flex-col">
        <div className="p-6">
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <Bot className="w-6 h-6" />
            AutoTrade
          </h1>
          <p className="text-xs text-slate-400 mt-1">加密货币自动交易平台</p>
        </div>

        <nav className="flex-1 px-4">
          <ul className="space-y-2">
            {navItems.map((item) => (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                    isActive(item.href)
                      ? "bg-blue-600 text-white"
                      : "text-slate-400 hover:bg-slate-800 hover:text-slate-100"
                  }`}
                >
                  <item.icon className="w-5 h-5" />
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        <div className="p-4 border-t border-slate-800 space-y-2">
          {username && (
            <div className="flex items-center gap-2 px-2 py-1 text-slate-400">
              <User className="w-4 h-4" />
              <span className="text-sm truncate">{username}</span>
            </div>
          )}
          <button
            onClick={handleLogout}
            className="flex items-center gap-2 w-full px-2 py-1 text-slate-400 hover:text-red-400 transition-colors text-sm"
          >
            <LogOut className="w-4 h-4" />
            退出登录
          </button>
        </div>
      </aside>

      {/* 移动端底部导航栏 */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-slate-900 border-t border-slate-800">
        <ul className="flex items-center justify-around">
          {navItems.map((item) => (
            <li key={item.href} className="flex-1">
              <Link
                href={item.href}
                className={`flex flex-col items-center gap-1 py-2 transition-colors ${
                  isActive(item.href)
                    ? "text-blue-400"
                    : "text-slate-500 hover:text-slate-300"
                }`}
              >
                <item.icon className="w-5 h-5" />
                <span className="text-[10px]">{item.label}</span>
              </Link>
            </li>
          ))}
          <li className="flex-1">
            <button
              onClick={handleLogout}
              className="flex flex-col items-center gap-1 py-2 w-full text-slate-500 hover:text-red-400 transition-colors"
            >
              <LogOut className="w-5 h-5" />
              <span className="text-[10px]">退出</span>
            </button>
          </li>
        </ul>
      </nav>
    </>
  );
}
