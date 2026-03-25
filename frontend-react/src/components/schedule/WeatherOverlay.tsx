import { Sun, Cloud, CloudRain, Wind, Snowflake } from 'lucide-react';
import { cn } from '@/lib/utils';

interface DayForecast {
  temp_high: number;
  temp_low: number;
  wind_max: number;
  precip_mm: number;
  status: 'clear' | 'do_not_build' | 'scheduler_decision';
}

export function WeatherOverlay({ forecast }: { forecast?: DayForecast | null }) {
  if (!forecast) return null;

  const Icon =
    forecast.precip_mm > 5
      ? CloudRain
      : forecast.precip_mm > 0
        ? Cloud
        : forecast.temp_low < 32
          ? Snowflake
          : forecast.wind_max > 25
            ? Wind
            : Sun;

  return (
    <div
      className={cn(
        'flex items-center gap-1.5 rounded-md px-2 py-1 text-[10px]',
        forecast.status === 'clear' && 'bg-green-50 text-green-700',
        forecast.status === 'do_not_build' && 'bg-red-50 text-red-700',
        forecast.status === 'scheduler_decision' && 'bg-yellow-50 text-yellow-700'
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      <span className="tabular-nums">
        {forecast.temp_low}°-{forecast.temp_high}°F
      </span>
      {forecast.wind_max > 15 && (
        <span className="tabular-nums">{forecast.wind_max}mph</span>
      )}
    </div>
  );
}
