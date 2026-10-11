import React, { useEffect, useRef } from 'react';

interface Star {
  x: number;
  y: number;
  radius: number;
  baseAlpha: number;
  alpha: number;
  twinkleSpeed: number;
  twinklePhase: number;
  vx: number;
  vy: number;
  color: string;
}

interface Meteor {
  x: number;
  y: number;
  length: number;
  speed: number;
  angle: number;
  opacity: number;
  fadeSpeed: number;
  thickness: number;
}

export const CelestialBackground: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    const handleResize = () => {
      if (!canvas) return;
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    };

    window.addEventListener('resize', handleResize);

    // Color palette for starry night
    const starColors = [
      '#ffffff', // Pure white
      '#e0f2fe', // Icy sky blue
      '#f0f9ff', // Pale starlight
      '#fef08a', // Warm golden dwarf
      '#e9d5ff', // Soft violet
    ];

    // Generate ~180 stars
    const starCount = Math.floor(Math.min(width, 1920) * 0.14);
    const stars: Star[] = Array.from({ length: starCount }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      radius: Math.random() * 1.5 + 0.4,
      baseAlpha: Math.random() * 0.6 + 0.25,
      alpha: Math.random(),
      twinkleSpeed: Math.random() * 0.03 + 0.008,
      twinklePhase: Math.random() * Math.PI * 2,
      vx: (Math.random() - 0.5) * 0.08, // Slow gentle drift
      vy: Math.random() * 0.06 + 0.02,
      color: starColors[Math.floor(Math.random() * starColors.length)],
    }));

    // Meteors / Shooting stars array
    const meteors: Meteor[] = [];
    let lastMeteorTime = Date.now();

    const spawnMeteor = () => {
      const startX = Math.random() * (width * 0.8) + width * 0.1;
      const startY = Math.random() * (height * 0.35);
      meteors.push({
        x: startX,
        y: startY,
        length: Math.random() * 90 + 70,
        speed: Math.random() * 10 + 14,
        angle: Math.PI / 4 + (Math.random() - 0.5) * 0.2, // ~45 degrees diagonal
        opacity: 1,
        fadeSpeed: Math.random() * 0.015 + 0.012,
        thickness: Math.random() * 1.6 + 1.0,
      });
    };

    let time = 0;

    const render = () => {
      time += 0.016;
      ctx.clearRect(0, 0, width, height);

      // 1. Draw subtle deep-space nebula haze
      const gradient = ctx.createRadialGradient(
        width * 0.82,
        height * 0.18,
        10,
        width * 0.82,
        height * 0.18,
        500
      );
      gradient.addColorStop(0, 'rgba(56, 189, 248, 0.06)'); // Lunar cyan aura
      gradient.addColorStop(0.5, 'rgba(99, 102, 241, 0.025)'); // Cosmic indigo
      gradient.addColorStop(1, 'rgba(0, 0, 0, 0)');
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, width, height);

      // Secondary deep nebula on the left
      const leftHaze = ctx.createRadialGradient(
        width * 0.15,
        height * 0.7,
        20,
        width * 0.15,
        height * 0.7,
        600
      );
      leftHaze.addColorStop(0, 'rgba(147, 51, 234, 0.035)');
      leftHaze.addColorStop(1, 'rgba(0, 0, 0, 0)');
      ctx.fillStyle = leftHaze;
      ctx.fillRect(0, 0, width, height);

      // 2. Render and update Stars
      for (const star of stars) {
        // Subtle drift in motion
        star.x += star.vx;
        star.y += star.vy;

        // Wrap around borders
        if (star.x < 0) star.x = width;
        if (star.x > width) star.x = 0;
        if (star.y > height) star.y = 0;

        // Sinusoidal twinkle
        star.twinklePhase += star.twinkleSpeed;
        const currentAlpha = Math.max(
          0.1,
          star.baseAlpha + Math.sin(star.twinklePhase) * 0.35
        );

        ctx.save();
        ctx.beginPath();
        ctx.arc(star.x, star.y, star.radius, 0, Math.PI * 2);
        ctx.fillStyle = star.color;
        ctx.globalAlpha = Math.min(1, currentAlpha);

        // Soft halo on larger stars
        if (star.radius > 1.2) {
          ctx.shadowBlur = 6;
          ctx.shadowColor = star.color;
        }

        ctx.fill();
        ctx.restore();
      }

      // 3. Spawn & Render Meteors
      const now = Date.now();
      if (now - lastMeteorTime > 4500 && Math.random() < 0.4) {
        spawnMeteor();
        lastMeteorTime = now;
      }

      for (let i = meteors.length - 1; i >= 0; i--) {
        const m = meteors[i];

        // Move
        const dx = Math.cos(m.angle) * m.speed;
        const dy = Math.sin(m.angle) * m.speed;
        m.x += dx;
        m.y += dy;
        m.opacity -= m.fadeSpeed;

        if (m.opacity <= 0 || m.x > width || m.y > height) {
          meteors.splice(i, 1);
          continue;
        }

        // Draw meteor trail
        const tailX = m.x - Math.cos(m.angle) * m.length;
        const tailY = m.y - Math.sin(m.angle) * m.length;

        const meteorGrad = ctx.createLinearGradient(m.x, m.y, tailX, tailY);
        meteorGrad.addColorStop(0, `rgba(255, 255, 255, ${m.opacity})`);
        meteorGrad.addColorStop(0.2, `rgba(186, 230, 253, ${m.opacity * 0.8})`);
        meteorGrad.addColorStop(0.6, `rgba(147, 197, 253, ${m.opacity * 0.3})`);
        meteorGrad.addColorStop(1, 'rgba(255, 255, 255, 0)');

        ctx.save();
        ctx.beginPath();
        ctx.moveTo(m.x, m.y);
        ctx.lineTo(tailX, tailY);
        ctx.strokeStyle = meteorGrad;
        ctx.lineWidth = m.thickness;
        ctx.lineCap = 'round';
        ctx.shadowBlur = 8;
        ctx.shadowColor = 'rgba(224, 242, 254, 0.9)';
        ctx.stroke();

        // Meteor Head Spark
        ctx.beginPath();
        ctx.arc(m.x, m.y, m.thickness * 1.2, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255, 255, 255, ${m.opacity})`;
        ctx.shadowBlur = 12;
        ctx.shadowColor = '#ffffff';
        ctx.fill();
        ctx.restore();
      }

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <div className="fixed inset-0 pointer-events-none overflow-hidden z-0 bg-black">
      {/* 2D Canvas for Starfield & Shooting Stars */}
      <canvas ref={canvasRef} className="absolute inset-0 block w-full h-full" />

      {/* Atmospheric Cosmic Backdrop Glow */}
      <div className="absolute top-0 right-1/4 w-[600px] h-[600px] rounded-full bg-sky-500/[0.03] blur-[120px] pointer-events-none" />
      <div className="absolute bottom-10 left-10 w-[500px] h-[500px] rounded-full bg-indigo-500/[0.025] blur-[140px] pointer-events-none" />

      {/* Luminous Motion Moon Container */}
      <div
        className="celestial-moon-anchor fixed top-6 right-8 md:top-10 md:right-16 lg:right-24 z-0 pointer-events-none select-none"
        aria-hidden="true"
      >
        {/* Outer Lunar Aura Waves */}
        <div className="moon-diffuse-glow absolute -inset-16 rounded-full bg-sky-300/[0.08] blur-[60px] animate-pulse-subtle" />
        <div className="moon-diffuse-glow-2 absolute -inset-8 rounded-full bg-blue-100/[0.12] blur-[35px]" />

        {/* The Moon Sphere */}
        <div className="moon-body relative w-24 h-24 md:w-32 md:h-32 lg:w-36 lg:h-36 rounded-full overflow-hidden shadow-2xl">
          {/* Base Lunar Surface Gradient */}
          <div className="absolute inset-0 rounded-full bg-gradient-to-tr from-slate-300 via-slate-100 to-white" />

          {/* Lunar Maria (Dark Basaltic Plains) */}
          {/* Mare Imbrium */}
          <div className="absolute top-4 left-6 w-9 h-7 rounded-full bg-slate-400/35 blur-[2.5px] rotate-12" />
          {/* Oceanus Procellarum */}
          <div className="absolute top-10 left-3 w-12 h-14 rounded-full bg-slate-400/30 blur-[3px] -rotate-6" />
          {/* Mare Serenitatis */}
          <div className="absolute top-6 right-7 w-8 h-8 rounded-full bg-slate-400/40 blur-[2px]" />
          {/* Mare Tranquillitatis */}
          <div className="absolute top-12 right-6 w-10 h-7 rounded-full bg-slate-500/35 blur-[2.5px] rotate-45" />
          {/* Mare Crisium */}
          <div className="absolute top-10 right-2 w-5 h-6 rounded-full bg-slate-500/45 blur-[1.5px]" />
          {/* Mare Fecunditatis */}
          <div className="absolute bottom-7 right-8 w-9 h-8 rounded-full bg-slate-400/35 blur-[2px]" />

          {/* Prominent Impact Craters with Bright Ejecta Rays */}
          {/* Tycho Crater at bottom */}
          <div className="absolute bottom-4 left-10 w-3 h-3 rounded-full bg-slate-200/90 shadow-[0_0_8px_rgba(255,255,255,0.9)]">
            <div className="absolute inset-0.5 rounded-full bg-slate-600/40" />
            <div className="absolute -top-3 -left-3 w-9 h-9 rounded-full bg-white/20 blur-[1px] pointer-events-none" />
          </div>
          {/* Copernicus Crater */}
          <div className="absolute top-14 left-11 w-3 h-3 rounded-full bg-slate-200/80 shadow-[0_0_6px_rgba(255,255,255,0.7)]">
            <div className="absolute inset-0.5 rounded-full bg-slate-500/50" />
          </div>
          {/* Kepler Crater */}
          <div className="absolute top-13 left-6 w-2 h-2 rounded-full bg-slate-200/80">
            <div className="absolute inset-0.5 rounded-full bg-slate-600/50" />
          </div>

          {/* Realistic Waxing 3D Spherical Shadow (Terminator Line) */}
          <div
            className="absolute inset-0 rounded-full"
            style={{
              background:
                'radial-gradient(circle at 68% 32%, transparent 45%, rgba(15, 23, 42, 0.45) 75%, rgba(2, 6, 23, 0.92) 100%)',
              boxShadow:
                'inset -12px -12px 28px rgba(2, 6, 23, 0.95), inset 4px 4px 12px rgba(255, 255, 255, 0.95)',
            }}
          />

          {/* Luminous Inner Atmosphere Rim */}
          <div className="absolute inset-0 rounded-full ring-1 ring-white/60 pointer-events-none" />
        </div>

        {/* Moon Halo Rings */}
        <div className="moon-halo-ring absolute -inset-6 rounded-full border border-sky-300/10 pointer-events-none animate-spin-slow" />
        <div className="moon-halo-ring-2 absolute -inset-12 rounded-full border border-sky-400/5 pointer-events-none" />
      </div>
    </div>
  );
};
