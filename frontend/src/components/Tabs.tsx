import React, { useState } from 'react';
import { LucideIcon } from 'lucide-react';

export interface TabItem {
  id: string;
  label: string;
  icon?: LucideIcon;
}

interface TabsProps {
  tabs: TabItem[];
  defaultTabId?: string;
  children: (activeTabId: string) => React.ReactNode;
}

export const Tabs: React.FC<TabsProps> = ({ tabs, defaultTabId, children }) => {
  const [activeTabId, setActiveTabId] = useState(defaultTabId || tabs[0]?.id);

  return (
    <div className="space-y-4">
      <div
        role="tablist"
        className="flex items-center gap-1 bg-graphite-950 p-1 rounded-lg border border-graphite-800 text-xs overflow-x-auto"
      >
        {tabs.map((tab) => {
          const isActive = tab.id === activeTabId;
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              role="tab"
              aria-selected={isActive}
              onClick={() => setActiveTabId(tab.id)}
              className={`px-3 py-1.5 rounded transition-colors cursor-pointer flex items-center gap-1.5 whitespace-nowrap ${
                isActive
                  ? 'bg-brass-950 text-brass-300 border border-brass-500/40 font-semibold'
                  : 'text-graphite-400 hover:text-graphite-200 border border-transparent'
              }`}
            >
              {Icon && <Icon className="w-3.5 h-3.5" />}
              {tab.label}
            </button>
          );
        })}
      </div>

      <div role="tabpanel">{children(activeTabId)}</div>
    </div>
  );
};
