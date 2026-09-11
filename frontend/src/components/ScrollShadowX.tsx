import React, { useCallback, useEffect, useRef, useState } from 'react';

interface ScrollShadowXProps {
  children: React.ReactNode;
  className?: string;
}

/**
 * Wraps a horizontally-scrollable region (a wide table, typically) and adds
 * a soft inset shadow on whichever edge still has hidden content -- the
 * only visible signal these tables were scrollable at all was the cursor
 * changing, which is easy to miss entirely on a data-dense dashboard.
 */
export const ScrollShadowX: React.FC<ScrollShadowXProps> = ({ children, className }) => {
  const ref = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  const update = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    setCanScrollLeft(el.scrollLeft > 2);
    setCanScrollRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 2);
  }, []);

  useEffect(() => {
    update();
    const el = ref.current;
    if (!el) return;
    const resizeObserver = new ResizeObserver(update);
    resizeObserver.observe(el);
    return () => resizeObserver.disconnect();
  }, [update, children]);

  const shadowParts: string[] = [];
  if (canScrollLeft) shadowParts.push('inset 16px 0 12px -12px rgba(0,0,0,0.55)');
  if (canScrollRight) shadowParts.push('inset -16px 0 12px -12px rgba(0,0,0,0.55)');

  return (
    <div
      ref={ref}
      onScroll={update}
      className={`overflow-x-auto ${className || ''}`}
      style={shadowParts.length ? { boxShadow: shadowParts.join(', ') } : undefined}
    >
      {children}
    </div>
  );
};
