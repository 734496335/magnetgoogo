import { AnimatePresence, motion } from 'framer-motion';
import { Search } from 'lucide-react';
import { MagnetResult } from '@/core/types';
import { SiteStatus, toResultCardModel } from '../models';
import { BrandWordmark } from './BrandWordmark';
import { ResultCard } from './ResultCard';
import { SearchField } from './SearchField';

export function ResultsScreen({
  query,
  searching,
  searched,
  results,
  copiedMagnet,
  elapsed,
  statuses,
  onSubmit,
  onQueryChange,
  onClear,
  onCopy,
}: {
  query: string;
  searching: boolean;
  searched: boolean;
  results: MagnetResult[];
  copiedMagnet: string | null;
  elapsed: number;
  statuses: Record<string, SiteStatus>;
  onSubmit: (event?: React.FormEvent) => Promise<void>;
  onQueryChange: (value: string) => void;
  onClear: () => void;
  onCopy: (magnet: string) => void;
}) {
  const cardModels = results.map(toResultCardModel);
  const doneCount = Object.values(statuses).filter((item) => item === 'done').length;
  const totalCount = Object.keys(statuses).length;

  return (
    <div className="flex min-h-[792px] flex-col">
      <div className="pt-2">
        <BrandWordmark compact />
      </div>

      <form onSubmit={onSubmit} className="mt-7">
        <SearchField
          value={query}
          onChange={onQueryChange}
          onClear={onClear}
          placeholder="搜索你想要的资源"
        />
      </form>

      <div className="mt-7 flex-1">
        {!searched && !searching ? <IdlePanel /> : null}

        {searching && cardModels.length === 0 ? <LoadingPanel /> : null}

        {cardModels.length > 0 ? (
          <>
            {searching ? (
              <div className="mb-5 flex items-center justify-between px-1 text-[13px] font-medium text-[#a0a8b8]">
                <span>正在整理结果 {doneCount}/{Math.max(totalCount, 1)}</span>
                <span>{(elapsed / 1000).toFixed(2)}s</span>
              </div>
            ) : null}

            <motion.div layout className="space-y-4">
              <AnimatePresence initial={false}>
                {cardModels.map((model) => (
                  <ResultCard
                    key={model.id}
                    model={model}
                    copied={copiedMagnet === model.magnet}
                    onCopy={onCopy}
                  />
                ))}
              </AnimatePresence>
            </motion.div>

            <div className="pt-6 text-center text-[13px] font-medium text-[#a0a8b8]">
              已显示 {cardModels.length} 条结果
            </div>
          </>
        ) : null}

        {!searching && searched && cardModels.length === 0 ? <EmptyPanel /> : null}
      </div>
    </div>
  );
}

function LoadingPanel() {
  return (
    <div className="space-y-4">
      {[0, 1, 2, 3].map((item) => (
        <div
          key={item}
          className="rounded-[30px] bg-white/98 px-4 py-4 shadow-[0_24px_56px_rgba(228,223,214,0.4)] ring-1 ring-[#f2efea]"
        >
          <div className="flex items-center gap-4">
            <div className="h-[64px] w-[64px] animate-pulse rounded-[18px] bg-[#faf4ea]" />
            <div className="min-w-0 flex-1">
              <div className="h-5 w-3/4 animate-pulse rounded-full bg-[#f2f1ef]" />
              <div className="mt-3 h-4 w-1/2 animate-pulse rounded-full bg-[#f4f3f1]" />
              <div className="mt-4 flex gap-2">
                <div className="h-8 w-16 animate-pulse rounded-full bg-[#f5f4f2]" />
                <div className="h-8 w-20 animate-pulse rounded-full bg-[#f5f4f2]" />
                <div className="h-8 w-24 animate-pulse rounded-full bg-[#f5f4f2]" />
              </div>
            </div>
            <div className="hidden h-[46px] w-[120px] animate-pulse rounded-[16px] bg-[#edf3ff] md:block" />
          </div>
        </div>
      ))}
    </div>
  );
}

function IdlePanel() {
  return (
    <div className="flex min-h-[560px] items-center justify-center rounded-[32px] border border-dashed border-[#efebe5] bg-white/56 px-8 text-center">
      <div>
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-[linear-gradient(135deg,#eff4ff,#f7f3ff)]">
          <Search className="h-6 w-6 text-[#7181e8]" strokeWidth={2} />
        </div>
        <p className="mt-5 text-[18px] font-semibold tracking-[-0.01em] text-[#4d5567]">输入关键词开始搜索</p>
        <p className="mt-2 text-[14px] leading-6 text-[#98a1b2]">
          搜索结果会按相关性排序，只保留最值得复制的磁力。
        </p>
      </div>
    </div>
  );
}

function EmptyPanel() {
  return (
    <div className="flex min-h-[560px] items-center justify-center rounded-[32px] bg-white/72 px-8 text-center shadow-[0_18px_46px_rgba(228,223,214,0.34)] ring-1 ring-[#f2efea]">
      <div>
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-[linear-gradient(135deg,#fff0f0,#fff8eb)]">
          <Search className="h-6 w-6 text-[#ff7f63]" strokeWidth={2} />
        </div>
        <p className="mt-5 text-[18px] font-semibold tracking-[-0.01em] text-[#4d5567]">没有找到足够匹配的磁力</p>
        <p className="mt-2 text-[14px] leading-6 text-[#98a1b2]">
          试试更短的关键词，或加入年份、清晰度、字幕信息。
        </p>
      </div>
    </div>
  );
}
