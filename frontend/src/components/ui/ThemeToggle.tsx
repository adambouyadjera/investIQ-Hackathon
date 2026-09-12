import { Moon, Sun, Monitor } from 'lucide-react';
import { useTheme } from '../../store/theme';

const ICONS = { dark: Moon, light: Sun, system: Monitor } as const;
const LABELS = {
  dark: 'Dark theme',
  light: 'Light theme',
  system: 'Matching your system theme',
} as const;

export function ThemeToggle() {
  const { theme, cycleTheme } = useTheme();
  const Icon = ICONS[theme];

  return (
    <button
      type="button"
      onClick={cycleTheme}
      title={`${LABELS[theme]} — click to change`}
      aria-label={`${LABELS[theme]}. Click to change theme.`}
      className="p-2 rounded-lg text-gray-400 hover:text-gray-200 hover:bg-gray-800
                 transition-colors focus:outline-none focus-visible:ring-2
                 focus-visible:ring-indigo-400"
    >
      <Icon className="w-4 h-4" />
    </button>
  );
}
