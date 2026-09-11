import React from 'react';
import {
  LayoutDashboard,
  Scan,
  Inbox,
  FileText,
  BarChart3,
  History,
  Settings,
  Shield,
  Radio
} from 'lucide-react';

interface SidebarProps {
  currentTab: string;
  onSelectTab: (tab: string) => void;
  pendingCount?: number;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentTab,
  onSelectTab,
  pendingCount = 0
}) => {
  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'screening', label: 'New Screening', icon: Scan },
    { id: 'queue', label: 'Review Queue', icon: Inbox, badge: pendingCount },
    { id: 'cases', label: 'Cases Archive', icon: FileText },
    { id: 'analytics', label: 'Analytics', icon: BarChart3 },
    { id: 'audit', label: 'Audit Trail', icon: History },
    { id: 'settings', label: 'System Settings', icon: Settings },
  ];

  return (
    <aside className="w-64 bg-slate-950 border-r border-slate-800/80 flex flex-col justify-between shrink-0 select-none">
      <div>
        {/* Brand Header */}
        <div className="p-5 border-b border-slate-800/60 flex items-center gap-3">
          <div className="h-9 w-9 rounded-lg bg-gradient-to-tr from-cyan-600 to-blue-600 flex items-center justify-center shadow-lg shadow-cyan-950/40 border border-cyan-400/30">
            <Shield className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-bold text-base tracking-wider text-slate-100 font-mono">
                BORDER<span className="text-cyan-400">MESH</span>
              </span>
            </div>
            <p className="text-[10px] text-slate-400 font-mono tracking-wide uppercase">
              AI Identity Screening
            </p>
          </div>
        </div>

        {/* Navigation Menu */}
        <nav className="p-3 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = currentTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onSelectTab(item.id)}
                className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-lg text-xs font-medium transition-all cursor-pointer ${
                  active
                    ? 'bg-cyan-950/70 text-cyan-300 border border-cyan-500/30 font-semibold shadow-inner'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60 border border-transparent'
                }`}
              >
                <div className="flex items-center gap-3">
                  <Icon className={`w-4 h-4 ${active ? 'text-cyan-400' : 'text-slate-400'}`} />
                  <span>{item.label}</span>
                </div>
                {item.badge !== undefined && item.badge > 0 && (
                  <span className="px-1.5 py-0.5 rounded-full text-[10px] font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* System Status Footer */}
      <div className="p-4 m-3 rounded-xl bg-slate-900/80 border border-slate-800/80 space-y-2 text-xs">
        <div className="flex items-center justify-between text-slate-300 font-mono text-[11px]">
          <span className="flex items-center gap-1.5 text-slate-400">
            <Radio className="w-3.5 h-3.5 text-emerald-400 animate-pulse" />
            AI Pipeline
          </span>
          <span className="text-emerald-400 font-bold">ONLINE</span>
        </div>
        <div className="flex items-center justify-between gap-2 text-[11px] font-mono text-slate-400">
          <span className="truncate">Watchlist Adapter</span>
          <span className="text-cyan-400 shrink-0">Sandbox Demo</span>
        </div>
        <div className="pt-1.5 border-t border-slate-800 text-[10px] text-slate-400">
          SIH Problem: <span className="text-slate-400">SIH26188</span>
        </div>
      </div>
    </aside>
  );
};
