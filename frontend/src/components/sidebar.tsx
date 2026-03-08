"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Bot, History, BarChart2, Settings } from "lucide-react";

const navItems = [
  { icon: LayoutDashboard, label: "仪表盘", href: "/" },
  { icon: Bot, label: "策略", href: "/strategies" },
  { icon: History, label: "触发日志", href: "/triggers" },
  { icon: BarChart2, label: "大盘", href: "/market" },
  { icon: Settings, label: "设置", href: "/settings" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 bg-slate-900 border-r border-slate-800 flex flex-col">
      <div className="p-6">
        <h1 className="text-xl font-bold text-white flex items-center gap-2">
          <Bot className="w-6 h-6" />
          AutoTrade
        </h1>
        <p className="text-xs text-slate-400 mt-1">加密货币自动交易平台</p>
      </div>

      <nav className="flex-1 px-4">
        <ul className="space-y-2">
          {navItems.map((item) => {
            const isActive = pathname === item.href || pathname?.startsWith(`${item.href}/`);
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                    isActive
                      ? "bg-blue-600 text-white"
                      : "text-slate-400 hover:bg-slate-800 hover:text-slate-100"
                  }`}
                >
                  <item.icon className="w-5 h-5" />
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="p-4 border-t border-slate-800">
        <p className="text-xs text-slate-500 text-center">
          AutoTrade v0.1.0
        </p>
      </div>
    </aside>
  );
}
