import Image from 'next/image';

export function BrandWordmark({ compact = false }: { compact?: boolean }) {
  return (
    <div className={compact ? 'w-[210px]' : 'w-[286px] md:w-[302px]'}>
      <Image
        src="/magnetgoogo-logo.png"
        alt="MagnetGoogo"
        width={860}
        height={215}
        priority
        className="h-auto w-full select-none"
      />
    </div>
  );
}
