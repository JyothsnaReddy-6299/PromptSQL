import { useEffect, useRef } from "react";

export function useMagnetic(strength = 0.3) {
  const ref = useRef<any>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const handleMouseMove = (e: MouseEvent) => {
      const rect = el.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;

      const dx = e.clientX - cx;
      const dy = e.clientY - cy;
      const dist = Math.sqrt(dx * dx + dy * dy);

      // Magnetic effect trigger radius
      if (dist < 75) {
        const tx = dx * strength;
        const ty = dy * strength;
        el.style.transform = `translate3d(${tx}px, ${ty}px, 0)`;
        el.style.transition = "transform 0.1s cubic-bezier(0.25, 1, 0.5, 1)";
      } else {
        el.style.transform = "";
        el.style.transition = "transform 0.4s cubic-bezier(0.25, 1, 0.5, 1)";
      }
    };

    const handleMouseLeave = () => {
      el.style.transform = "";
      el.style.transition = "transform 0.4s cubic-bezier(0.25, 1, 0.5, 1)";
    };

    window.addEventListener("mousemove", handleMouseMove);
    el.addEventListener("mouseleave", handleMouseLeave);

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      el.removeEventListener("mouseleave", handleMouseLeave);
    };
  }, [strength]);

  return ref;
}
