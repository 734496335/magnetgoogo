import { BrandWordmark } from './BrandWordmark';
import { GradientSearchButton } from './GradientSearchButton';
import { SearchField } from './SearchField';

export function HomeScreen({
  query,
  onChange,
  onSubmit,
  searching,
}: {
  query: string;
  onChange: (value: string) => void;
  onSubmit: (event?: React.FormEvent) => Promise<void>;
  searching: boolean;
}) {
  return (
    <div className="relative flex min-h-[792px] flex-col items-center justify-center pb-20 pt-8">
      <div className="pointer-events-none absolute inset-x-0 top-18 h-60 bg-[radial-gradient(circle_at_50%_50%,rgba(255,255,255,0.92),rgba(255,255,255,0))]" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-52 bg-[radial-gradient(circle_at_50%_100%,rgba(244,241,236,0.96),rgba(255,255,255,0))]" />
      <div className="pointer-events-none absolute inset-x-5 bottom-4 h-36 opacity-75 [background:repeating-linear-gradient(171deg,transparent,transparent_10px,rgba(244,240,234,0.96)_11px,transparent_12px)]" />
      <div className="pointer-events-none absolute inset-x-8 bottom-10 h-24 bg-[radial-gradient(circle_at_50%_50%,rgba(255,255,255,0.5),rgba(255,255,255,0))]" />

      <div className="relative z-10 flex w-full flex-col items-center">
        <div className="translate-y-[-2px]">
          <BrandWordmark />
        </div>
        <p className="mt-[18px] text-center text-[17px] font-medium tracking-[0.01em] text-[#7d8496]">
          最快找到最值得点击的磁力
        </p>

        <form onSubmit={onSubmit} className="mt-[44px] flex w-full flex-col items-center gap-[18px] px-3">
          <SearchField
            value={query}
            onChange={onChange}
            placeholder="搜索电影、剧集、动漫、纪录片..."
            large
          />
          <GradientSearchButton disabled={!query.trim() || searching} searching={searching} />
        </form>
      </div>
    </div>
  );
}
