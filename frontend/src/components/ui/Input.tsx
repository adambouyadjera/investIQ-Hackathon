import React from 'react';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
  prefix?: string;
  suffix?: string;
}

export function Input({
  label,
  error,
  hint,
  prefix,
  suffix,
  className = '',
  id,
  ...props
}: InputProps) {
  const inputId = id || label?.toLowerCase().replace(/\s+/g, '-');
  return (
    <div className="flex flex-col gap-1">
      {label && (
        <label htmlFor={inputId} className="text-sm font-medium text-gray-300">
          {label}
        </label>
      )}
      <div className="relative flex items-center">
        {prefix && (
          <span className="absolute left-3 text-gray-400 text-sm select-none">{prefix}</span>
        )}
        <input
          id={inputId}
          {...props}
          className={`
            w-full rounded-lg border bg-gray-800 text-gray-100 placeholder-gray-500
            focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent
            transition-colors duration-150
            ${error ? 'border-red-500' : 'border-gray-700'}
            ${prefix ? 'pl-8' : 'pl-3'}
            ${suffix ? 'pr-8' : 'pr-3'}
            py-2 text-sm
            ${className}
          `}
        />
        {suffix && (
          <span className="absolute right-3 text-gray-400 text-sm select-none">{suffix}</span>
        )}
      </div>
      {error && <p className="text-xs text-red-400">{error}</p>}
      {hint && !error && <p className="text-xs text-gray-500">{hint}</p>}
    </div>
  );
}
