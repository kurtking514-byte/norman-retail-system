/**
 * Full-width shop sign: the store name in the sign's red-on-white lettering
 * over the rice-terrace photo, framed by the woven cloth from the real banner.
 * Anything passed as children sits on the right (account controls); with no
 * children the name is centered and the optional tagline shows under it.
 */
export default function ShopBanner({ children, tagline }) {
  return (
    <header className={`flex flex-shrink-0 bg-terrace-700 ${tagline ? 'h-28 lg:h-32' : 'h-20 lg:h-24'}`}>
      <div className="banner-cloth w-3 sm:w-5 flex-shrink-0" />
      <div className={`banner-terraces relative flex-1 min-w-0 flex items-center gap-4 px-4 sm:px-6 ${children ? '' : 'justify-center text-center'}`}>
        <div className="absolute inset-0 bg-black/20" aria-hidden="true" />
        <div className="relative min-w-0">
          <p className="sign-text leading-none xl:whitespace-nowrap">
            <span className="block xl:inline xl:mr-[0.05em] text-[28px] sm:text-[36px] xl:text-[28px] 2xl:text-[36px]">Norman</span>{' '}
            <span className="block xl:inline mt-1 xl:mt-0 text-[12px] sm:text-[16px] xl:text-[28px] 2xl:text-[36px]">
              Cellphone Center &amp; Accessories
            </span>
          </p>
          {tagline && (
            <p className="mt-1.5 sm:mt-2 font-display text-[11px] sm:text-base font-bold uppercase tracking-[0.06em] sm:tracking-[0.12em] text-white [text-shadow:0_1px_4px_rgba(0,0,0,0.7)]">
              {tagline}
            </p>
          )}
        </div>
        {children && <div className="relative ml-auto flex-shrink-0">{children}</div>}
      </div>
      <div className="banner-cloth w-3 sm:w-5 flex-shrink-0" />
    </header>
  );
}
