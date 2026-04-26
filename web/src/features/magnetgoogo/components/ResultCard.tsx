import { motion } from 'framer-motion';
import { Copy } from 'lucide-react';
import { pillClassForTag, ResultCardModel } from '../models';

const CARD_MOTION = {
  initial: { opacity: 0, y: 16, scale: 0.985 },
  animate: { opacity: 1, y: 0, scale: 1 },
  exit: { opacity: 0, y: 8, scale: 0.99 },
  transition: { duration: 0.22, ease: 'easeOut' as const },
};

export function ResultCard({
  model,
  copied,
  onCopy,
}: {
  model: ResultCardModel;
  copied: boolean;
  onCopy: (magnet: string) => void;
}) {
  const Icon = model.theme.icon;

  return (
    <motion.article
      layout
      {...CARD_MOTION}
      className="rounded-[32px] bg-[linear-gradient(180deg,rgba(255,255,255,0.99),rgba(255,255,255,0.95))] px-5 py-5 shadow-[0_24px_54px_rgba(228,223,214,0.38)] ring-1 ring-[#f2efea]"
    >
      <div className="grid grid-cols-[56px_minmax(0,1fr)_90px] grid-rows-[auto_auto_auto] items-start gap-x-4 gap-y-0">
        <div
          className={`row-span-2 mt-[8px] flex h-[52px] w-[52px] shrink-0 items-center justify-center self-start rounded-[16px] bg-gradient-to-br ${model.theme.tileClassName} shadow-[inset_0_1px_0_rgba(255,255,255,0.7)]`}
        >
          <Icon className={`h-5.5 w-5.5 ${model.theme.iconClassName}`} strokeWidth={1.85} />
        </div>

        <h3 className="col-start-2 col-end-4 line-clamp-2 pr-1 text-[14px] font-semibold leading-[1.34] tracking-[-0.012em] text-[#262b35] md:text-[15px]">
          {model.title}
        </h3>

        <div className="col-start-2 col-end-4 mt-[6px] flex items-center text-[12px] font-medium text-[#9aa3b4]">
          <span>{model.kindLabel}</span>
          {model.sizeLabel ? (
            <>
              <span className="mx-2 text-[#d0d5de]">|</span>
              <span>{model.sizeLabel}</span>
            </>
          ) : null}
          {model.fileCountLabel ? (
            <>
              <span className="mx-2 text-[#d0d5de]">|</span>
              <span>{model.fileCountLabel}</span>
            </>
          ) : null}
        </div>

        {model.tags.length > 0 ? (
          <div className="col-start-1 col-end-3 mt-[10px] flex flex-nowrap items-center gap-1.5 self-end overflow-hidden pr-2">
            {model.tags.map((tag) => (
              <span
                key={`${model.id}-${tag}`}
                className={`shrink-0 whitespace-nowrap rounded-full px-3 py-[5px] text-[11px] font-semibold leading-none shadow-[inset_0_1px_0_rgba(255,255,255,0.5)] ${pillClassForTag(tag)}`}
              >
                {tag}
              </span>
            ))}
          </div>
        ) : (
          <div className="col-start-1 col-end-3 mt-[10px] h-[28px]" />
        )}

        <button
          type="button"
          onClick={() => onCopy(model.magnet)}
          className="col-start-3 row-start-3 flex h-[28px] w-[86px] items-center justify-center gap-1 self-end rounded-[10px] bg-[linear-gradient(180deg,#4e8aff_0%,#2c63f4_100%)] px-2 font-semibold leading-none tracking-[-0.01em] text-white whitespace-nowrap shadow-[0_6px_14px_rgba(55,111,248,0.20)] transition hover:scale-[1.02]"
          style={{ fontSize: '12px' }}
        >
          <Copy className="h-4 w-4 shrink-0" strokeWidth={2.2} />
          {copied ? '已复制' : '复制磁力'}
        </button>
      </div>
    </motion.article>
  );
}
