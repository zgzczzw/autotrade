"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, Search, X } from "lucide-react";
import { fetchSymbols } from "@/lib/api";

interface SymbolSelectorProps {
  value: string;
  onChange: (symbol: string) => void;
}

export function SymbolSelector({ value, onChange }: SymbolSelectorProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [symbols, setSymbols] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 点击外部关闭
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // debounce 搜索
  useEffect(() => {
    if (!open) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const result = await fetchSymbols(query);
        setSymbols(result as string[]);
      } catch {
        setSymbols([]);
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, open]);

  // 打开时加载初始列表
  const handleOpen = async () => {
    setOpen(true);
    setQuery("");
    setLoading(true);
    try {
      const result = await fetchSymbols("");
      setSymbols(result as string[]);
    } catch {
      setSymbols([]);
    } finally {
      setLoading(false);
    }
  };

  const handleSelect = (symbol: string) => {
    onChange(symbol);
    setOpen(false);
    setQuery("");
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        onClick={open ? () => setOpen(false) : handleOpen}
        className="flex items-center gap-2 px-4 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white hover:border-slate-500 transition-colors min-w-[160px]"
      >
        <span className="font-mono font-semibold flex-1 text-left">{value}</span>
        <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="absolute top-full left-0 mt-1 w-64 bg-slate-800 border border-slate-700 rounded-xl shadow-2xl z-50 overflow-hidden">
          {/* 搜索框 */}
          <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-700">
            <Search className="w-4 h-4 text-slate-400 shrink-0" />
            <input
              autoFocus
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索交易对..."
              className="flex-1 bg-transparent text-sm text-white placeholder-slate-500 outline-none"
            />
            {query && (
              <button onClick={() => setQuery("")}>
                <X className="w-3 h-3 text-slate-400 hover:text-white" />
              </button>
            )}
          </div>

          {/* 列表 */}
          <div className="max-h-64 overflow-y-auto">
            {loading ? (
              <p className="text-center text-xs text-slate-500 py-4">加载中...</p>
            ) : symbols.length === 0 ? (
              <p className="text-center text-xs text-slate-500 py-4">未找到结果</p>
            ) : (
              symbols.map((s) => (
                <button
                  key={s}
                  onClick={() => handleSelect(s)}
                  className={`w-full text-left px-4 py-2 text-sm font-mono hover:bg-slate-700 transition-colors ${
                    s === value ? "text-blue-400 bg-blue-500/10" : "text-slate-200"
                  }`}
                >
                  {s}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ==================== Multi-Symbol Selector ====================

interface MultiSymbolSelectorProps {
  value: string[];
  onChange: (symbols: string[]) => void;
}

export function MultiSymbolSelector({ value, onChange }: MultiSymbolSelectorProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [symbols, setSymbols] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Click outside to close
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Debounce search
  useEffect(() => {
    if (!open) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const result = await fetchSymbols(query);
        setSymbols((result as string[]).filter((s) => !value.includes(s)));
      } catch {
        setSymbols([]);
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [query, open, value]);

  const handleOpen = async () => {
    setOpen(true);
    setQuery("");
    setLoading(true);
    try {
      const result = await fetchSymbols("");
      setSymbols((result as string[]).filter((s) => !value.includes(s)));
    } catch {
      setSymbols([]);
    } finally {
      setLoading(false);
    }
  };

  const handleSelect = (symbol: string) => {
    onChange([...value, symbol]);
    setQuery("");
  };

  const handleRemove = (symbol: string) => {
    onChange(value.filter((s) => s !== symbol));
  };

  return (
    <div ref={containerRef} className="relative">
      <div
        className="flex flex-wrap gap-1.5 min-h-[42px] px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg cursor-text"
        onClick={!open ? handleOpen : undefined}
      >
        {value.map((s) => (
          <span
            key={s}
            className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-500/20 text-blue-400 text-xs font-mono rounded"
          >
            {s}
            <button
              onClick={(e) => { e.stopPropagation(); handleRemove(s); }}
              className="hover:text-blue-200"
            >
              <X className="w-3 h-3" />
            </button>
          </span>
        ))}
        {value.length === 0 && (
          <span className="text-slate-500 text-sm">点击添加交易对...</span>
        )}
      </div>

      {open && (
        <div className="absolute top-full left-0 mt-1 w-72 bg-slate-800 border border-slate-700 rounded-xl shadow-2xl z-50 overflow-hidden">
          <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-700">
            <Search className="w-4 h-4 text-slate-400 shrink-0" />
            <input
              autoFocus
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索交易对..."
              className="flex-1 bg-transparent text-sm text-white placeholder-slate-500 outline-none"
            />
          </div>
          <div className="max-h-48 overflow-y-auto">
            {loading ? (
              <p className="text-center text-xs text-slate-500 py-4">加载中...</p>
            ) : symbols.length === 0 ? (
              <p className="text-center text-xs text-slate-500 py-4">未找到结果</p>
            ) : (
              symbols.map((s) => (
                <button
                  key={s}
                  onClick={() => handleSelect(s)}
                  className="w-full text-left px-4 py-2 text-sm font-mono text-slate-200 hover:bg-slate-700 transition-colors"
                >
                  {s}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
