import React from 'react';

interface CardProps {
  children: React.ReactNode;
  className?: string;
  title?: string;
  subtitle?: string;
  action?: React.ReactNode;
}

export function Card({ children, className = '', title, subtitle, action }: CardProps) {
  return (
    <div className={`bg-gray-800 rounded-xl border border-gray-700 ${className}`}>
      {(title || action) && (
        <div className="flex items-center justify-between px-5 pt-5 pb-3">
          <div>
            {title && <h3 className="text-sm font-semibold text-gray-100">{title}</h3>}
            {subtitle && <p className="text-xs text-gray-400 mt-0.5">{subtitle}</p>}
          </div>
          {action && <div>{action}</div>}
        </div>
      )}
      <div className="px-5 pb-5">{children}</div>
    </div>
  );
}

export function StatCard({
  label,
  value,
  sub,
  color,
  tooltip,
}: {
  label: string;
  value: string;
  sub?: string;
  color?: 'green' | 'red' | 'yellow' | 'default';
  tooltip?: string;
}) {
  const colorMap = {
    green: 'text-emerald-400',
    red: 'text-red-400',
    yellow: 'text-amber-400',
    default: 'text-gray-100',
  };
  return (
    <div
      className="bg-gray-800 rounded-xl border border-gray-700 p-4 flex flex-col gap-1"
      title={tooltip}
    >
      <p className="text-xs text-gray-400">{label}</p>
      <p className={`text-xl font-bold ${colorMap[color || 'default']}`}>{value}</p>
      {sub && <p className="text-xs text-gray-500">{sub}</p>}
    </div>
  );
}
