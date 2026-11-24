"use client";

import { Blur } from "@animate-ui/react/primitives/effects/blur";
import Link from "next/link";
import { useRef, useState } from "react";

import { Play } from "@/components/animate-ui/icons/play";

const DURATION = 169;
const TICKS = [0, 0.25, 0.5, 0.75, 1];

function clock(s: number) {
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.round(s % 60)).padStart(2, "0")}`;
}

export function Hero() {
  const video = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);

  function watch() {
    const v = video.current;
    if (!v) return;
    void v.play();
    v.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  return (
    <section className="lp-wrap lp-hero" id="film" data-film={playing ? "playing" : "idle"}>
      <div>
        <Blur initialBlur={14} delay={80}>
          <h1 className="lp-title">
            Test, attack, and guard your <em>AI agents.</em>
          </h1>
        </Blur>
        <Blur initialBlur={10} delay={260}>
          <p className="lp-abstract">
            Gauntlet simulates customers, red-teams your agent with 297 real attacks, turns each confirmed hole into a
            policy rule, then replays the attack to prove the rule holds. This page shows one real run, and the
            benchmarks that did not flatter us.
          </p>
        </Blur>
        <Blur initialBlur={8} delay={440}>
          <div className="lp-cta">
            <button type="button" className="lp-btn" onClick={watch}>
              <Play animateOnHover aria-hidden />
              Watch the film (2:49)
            </button>
            <Link className="lp-link" href="/arena">
              Try the arena
            </Link>
          </div>
        </Blur>
      </div>

      <Blur initialBlur={18} delay={200}>
        <figure className="lp-fig1" aria-labelledby="fig1-cap">
          <div className="lp-fig1-frame">
            <video
              ref={video}
              controls={playing}
              preload="none"
              poster="/media/poster.jpg"
              playsInline
              onPlay={() => setPlaying(true)}
              aria-label="Gauntlet product film, 2 minutes 49 seconds"
            >
              <source src="/media/gauntlet-tour-16x9.mp4" type="video/mp4" />
              <track kind="captions" src="/media/gauntlet-tour.vtt" srcLang="en" label="English" default />
            </video>
            {!playing && (
              <button type="button" className="lp-fig1-play" onClick={watch} aria-label="Play the film">
                <span>
                  <Play aria-hidden />
                  Play, 2:49
                </span>
              </button>
            )}
            <span className="lp-fig1-rule" aria-hidden />
            <svg
              aria-hidden
              viewBox="0 0 100 10"
              preserveAspectRatio="none"
              style={{ position: "absolute", left: 0, top: "100%", width: "100%", height: 12, marginTop: 12 }}
              className="lp-fig1-axes"
            >
              {Array.from({ length: 41 }, (_, i) => (
                <line key={i} x1={i * 2.5} x2={i * 2.5} y1={0} y2={i % 10 === 0 ? 10 : i % 5 === 0 ? 6 : 3.5} className={i % 10 === 0 ? "major" : ""} />
              ))}
            </svg>
            <svg
              aria-hidden
              viewBox="0 0 10 100"
              preserveAspectRatio="none"
              style={{ position: "absolute", right: "100%", top: 0, width: 12, height: "100%", marginRight: 12 }}
              className="lp-fig1-axes"
            >
              {Array.from({ length: 19 }, (_, i) => (
                <line key={i} y1={i * (100 / 18)} y2={i * (100 / 18)} x1={10} x2={i % 6 === 0 ? 0 : i % 3 === 0 ? 4 : 6.5} className={i % 6 === 0 ? "major" : ""} />
              ))}
            </svg>
            {TICKS.map((t) => (
              <span
                key={t}
                className="lp-fig1-tick"
                style={{ left: `${t * 100}%`, top: "calc(100% + 30px)", transform: `translateX(-${t * 100}%)` }}
              >
                {clock(DURATION * t)}
              </span>
            ))}
          </div>
          <figcaption id="fig1-cap" className="lp-cap" style={{ marginTop: "3.4rem" }}>
            <b>Fig. 1.</b> One real run, end to end. Live model spend: <span className="mono">$0.11</span>.
          </figcaption>
        </figure>
      </Blur>
    </section>
  );
}
