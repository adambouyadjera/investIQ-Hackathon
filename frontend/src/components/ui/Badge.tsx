import React from 'react';

type Color = 'green' | 'red' | 'yellow' | 'blue' | 'purple' | 'gray';

const colors: Record<Color, string> = {
  green: 'bg-emerald-900/50 text-emerald-300 border-emerald-700',
  red: 'bg-red-900/50 text-red-300 border-red-700',
  yellow: 'bg-amber-900/50 text-amber-300 border-amber-700',
  blue: 'bg-blue-900/50 text-blue-300 border-blue-700',
  purple: 'bg-indigo-900/50 text-indigo-300 border-indigo-700',
  gray: 'bg-gray-700 text-gray-300 border-gray-600',
};

export function Badge({
  children,
  color = 'gray',
}: {
  children: React.ReactNode;
  color?: Color;
}) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium border ${colors[color]}`}
    >
      {children}
    </span>
  );
}
