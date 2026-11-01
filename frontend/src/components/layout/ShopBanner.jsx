/**
 * Full-width shop sign: the store name in the sign's red-on-white lettering,
 * centered over the rice terraces and framed by woven-cloth panels like the
 * real banner. A red rule underneath separates it from the page.
 */
export default function ShopBanner({ tagline }) {
  return (
    <header className="flex-shrink-0 border-b-4 border-brand-600">
      <div className={`flex ${tagline ? 'h-28 sm:h-32' : 'h-[88px] lg:h-[97px]'}`}>
        <div className="banner-cloth w-8 sm:w-16 flex-shrink-0 border-r-2 border-ink-900" />
        <div className="banner-terraces relative flex-1 min-w-0 flex items-center justify-center px-3 text-center">
          <div className="absolute inset-0 bg-terrace-800/60" aria-hidden="true" />
          <div className="relative min-w-0">
            <p className="sign-text leading-none xl:whitespace-nowrap">
              <span className="block xl:inline text-[28px] sm:text-[38px] xl:text-[30px] 2xl:text-[38px]">Norman</span>{' '}
              <span className="block xl:inline mt-1 xl:mt-0 text-[12px] sm:text-[17px] xl:text-[30px] 2xl:text-[38px]">
                Cellphone Center &amp; Accessories
              </span>
            </p>
            {tagline && (
              <p className="mt-1.5 sm:mt-2 font-display text-[11px] sm:text-base font-bold uppercase tracking-[0.06em] sm:tracking-[0.12em] text-white [text-shadow:0_1px_4px_rgba(0,0,0,0.7)]">
                {tagline}
              </p>
            )}
          </div>
        </div>
        <div className="banner-cloth w-8 sm:w-16 flex-shrink-0 border-l-2 border-ink-900" />
      </div>
    </header>
  );
}
