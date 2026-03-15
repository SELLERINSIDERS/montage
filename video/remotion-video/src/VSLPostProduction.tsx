import {
  AbsoluteFill,
  OffthreadVideo,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  cancelRender,
  useDelayRender,
} from "remotion";
import {
  Caption,
  TikTokPage,
  createTikTokStyleCaptions,
} from "@remotion/captions";
import { fitText } from "@remotion/layout-utils";
import { makeTransform, scale, translateY } from "@remotion/animation-utils";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { loadFont, TheBoldFont } from "./load-font";

// ---------- Types ----------

interface CameraMove {
  type: string;
  scale_start: number;
  scale_end: number;
  origin: string;
}

interface ColorGrade {
  brightness: number;
  contrast: number;
  saturate: number;
  sepia: number;
  hue_rotate: number;
}

interface SceneEntry {
  id: string;
  start_s: number;
  end_s: number;
  act: string;
  transition_in: string;
  camera: CameraMove;
  color_grade?: ColorGrade;
  vignette?: number;
}

interface PostProdEDL {
  meta: {
    fps: number;
    width: number;
    height: number;
    total_duration_s: number;
    source_video: string;
    whisper_data: string;
  };
  scenes: SceneEntry[];
}

interface WhisperWord {
  text: string;
  start: number;
  end: number;
}

interface WhisperData {
  text: string;
  words: WhisperWord[];
}

// ---------- Helpers ----------

function whisperToCaptions(words: WhisperWord[]): Caption[] {
  return words.map((w) => ({
    text: w.text,
    startMs: Math.round(w.start * 1000),
    endMs: Math.round(w.end * 1000),
    timestampMs: Math.round(w.start * 1000),
    confidence: 1,
  }));
}

function buildColorFilter(grade: ColorGrade): string {
  const parts: string[] = [];
  if (grade.brightness !== 1.0) parts.push(`brightness(${grade.brightness})`);
  if (grade.contrast !== 1.0) parts.push(`contrast(${grade.contrast})`);
  if (grade.saturate !== 1.0) parts.push(`saturate(${grade.saturate})`);
  if (grade.sepia > 0) parts.push(`sepia(${grade.sepia})`);
  if (grade.hue_rotate !== 0) parts.push(`hue-rotate(${grade.hue_rotate}deg)`);
  return parts.length > 0 ? parts.join(" ") : "none";
}

const CAMERA_AMPLIFY = 3.0;

function amplifyScale(s: number): number {
  return 1.0 + (s - 1.0) * CAMERA_AMPLIFY;
}

function findActiveScene(
  scenes: SceneEntry[],
  timeS: number,
): SceneEntry | null {
  for (let i = scenes.length - 1; i >= 0; i--) {
    if (timeS >= scenes[i].start_s) {
      return scenes[i];
    }
  }
  return scenes[0] ?? null;
}

// ---------- Egyptian Caption Page ----------
// Rendered inside a <Sequence>, so useCurrentFrame() is relative to sequence start

const GOLD_BASE = "#E8D5A3";
const GOLD_ACTIVE = "#FFD700";
const STROKE_COLOR = "#1A0F00";

const EgyptianPage: React.FC<{ page: TikTokPage }> = ({ page }) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();

  // Current time relative to sequence start → convert to absolute
  const currentTimeMs = (frame / fps) * 1000;
  const absoluteTimeMs = page.startMs + currentTimeMs;

  // Enter animation over first 6 frames
  const enterProgress = Math.min(1, frame / 6);

  const fittedText = fitText({
    fontFamily: TheBoldFont,
    text: page.text,
    withinWidth: width * 0.85,
    textTransform: "uppercase",
  });
  const fontSize = Math.min(80, fittedText.fontSize);

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        top: undefined,
        bottom: 200,
        height: 180,
      }}
    >
      <div
        style={{
          fontSize,
          color: GOLD_BASE,
          WebkitTextStroke: `16px ${STROKE_COLOR}`,
          paintOrder: "stroke",
          transform: makeTransform([
            scale(interpolate(enterProgress, [0, 1], [0.7, 1])),
            translateY(interpolate(enterProgress, [0, 1], [40, 0])),
          ]),
          fontFamily: TheBoldFont,
          textTransform: "uppercase",
          textAlign: "center",
          maxWidth: width * 0.85,
          textShadow: `0 0 20px rgba(212, 168, 75, 0.4), 0 2px 4px rgba(0, 0, 0, 0.8)`,
          letterSpacing: "2px",
        }}
      >
        {page.tokens.map((token) => {
          const isActive =
            token.fromMs <= absoluteTimeMs && token.toMs > absoluteTimeMs;

          return (
            <span
              key={token.fromMs}
              style={{
                display: "inline",
                whiteSpace: "pre",
                color: isActive ? GOLD_ACTIVE : GOLD_BASE,
                textShadow: isActive
                  ? `0 0 30px rgba(255, 215, 0, 0.6), 0 0 60px rgba(255, 215, 0, 0.3)`
                  : undefined,
              }}
            >
              {token.text}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

// ---------- Caption Layer (uses Sequences) ----------

const SWITCH_CAPTIONS_EVERY_MS = 1200;

const CaptionLayer: React.FC<{ captions: Caption[] }> = ({ captions }) => {
  const { fps } = useVideoConfig();

  const { pages } = useMemo(() => {
    return createTikTokStyleCaptions({
      captions,
      combineTokensWithinMilliseconds: SWITCH_CAPTIONS_EVERY_MS,
    });
  }, [captions]);

  return (
    <AbsoluteFill>
      {pages.map((page, index) => {
        const nextPage = pages[index + 1] ?? null;
        const startFrame = (page.startMs / 1000) * fps;
        const endFrame = Math.min(
          nextPage ? (nextPage.startMs / 1000) * fps : Infinity,
          startFrame + (SWITCH_CAPTIONS_EVERY_MS / 1000) * fps,
        );
        const durationInFrames = endFrame - startFrame;

        if (durationInFrames <= 0) {
          return null;
        }

        return (
          <Sequence
            key={index}
            from={Math.round(startFrame)}
            durationInFrames={Math.round(durationInFrames)}
          >
            <EgyptianPage page={page} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

// ---------- Scene Transitions ----------

const SceneTransitions: React.FC<{
  scenes: SceneEntry[];
}> = ({ scenes }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  for (let i = 1; i < scenes.length; i++) {
    const scene = scenes[i];
    const cutFrame = Math.round(scene.start_s * fps);
    const dist = frame - cutFrame;

    if (scene.transition_in === "crossfade" && dist >= -10 && dist <= 10) {
      const opacity = interpolate(
        dist,
        [-10, -2, 0, 2, 10],
        [0, 0.45, 0.6, 0.45, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
      );
      return (
        <AbsoluteFill
          style={{
            backgroundColor: `rgba(15, 10, 5, ${opacity})`,
            pointerEvents: "none",
          }}
        />
      );
    }

    if (scene.transition_in === "tonal_shift_cut" && dist >= -3 && dist <= 8) {
      const opacity = interpolate(dist, [-3, 0, 8], [0, 0.85, 0], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      });
      return (
        <AbsoluteFill
          style={{
            backgroundColor: `rgba(255, 235, 200, ${opacity})`,
            pointerEvents: "none",
          }}
        />
      );
    }
  }

  return null;
};

// ---------- Film Grain ----------

const FilmGrain: React.FC<{ opacity: number }> = ({ opacity }) => {
  const frame = useCurrentFrame();
  if (opacity <= 0) return null;

  const seed = frame % 120;
  return (
    <AbsoluteFill
      style={{ mixBlendMode: "overlay", opacity, pointerEvents: "none" }}
    >
      <svg width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
        <filter id={`grain${seed}`}>
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.7"
            numOctaves="3"
            seed={seed}
            stitchTiles="stitch"
          />
        </filter>
        <rect width="100%" height="100%" filter={`url(#grain${seed})`} />
      </svg>
    </AbsoluteFill>
  );
};

// ---------- Vignette ----------

const Vignette: React.FC<{ intensity: number }> = ({ intensity }) => {
  if (intensity <= 0) return null;
  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(ellipse at center, transparent ${Math.round((1 - intensity) * 100)}%, rgba(0,0,0,${intensity * 0.5}) 100%)`,
        pointerEvents: "none",
      }}
    />
  );
};

// ---------- Main Composition ----------

export const VSLPostProduction: React.FC<{
  edl: PostProdEDL;
}> = ({ edl }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const [captions, setCaptions] = useState<Caption[]>([]);
  const { delayRender, continueRender } = useDelayRender();
  const [handle] = useState(() => delayRender());

  const fetchData = useCallback(async () => {
    try {
      await loadFont();
      const res = await fetch(staticFile(edl.meta.whisper_data));
      const whisper = (await res.json()) as WhisperData;
      setCaptions(whisperToCaptions(whisper.words));
      continueRender(handle);
    } catch (e) {
      cancelRender(e);
    }
  }, [continueRender, handle, edl.meta.whisper_data]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const timeS = frame / fps;
  const scene = findActiveScene(edl.scenes, timeS);

  // Camera
  let cameraScale = 1.0;
  let cameraOrigin = "center center";

  if (scene) {
    const sceneStartFrame = Math.round(scene.start_s * fps);
    const sceneEndFrame = Math.round(scene.end_s * fps);
    const sceneLocalFrame = frame - sceneStartFrame;

    if (scene.id === "scene_01") {
      cameraScale = interpolate(
        frame,
        [sceneStartFrame, sceneEndFrame],
        [1.25, 1.0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
      );
      cameraOrigin = "center 35%";
    } else {
      const scaleStart = amplifyScale(scene.camera.scale_start);
      const scaleEnd = amplifyScale(scene.camera.scale_end);
      cameraScale = interpolate(
        frame,
        [sceneStartFrame, sceneEndFrame],
        [scaleStart, scaleEnd],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
      );
      cameraOrigin = scene.camera.origin;
    }

    if (
      sceneLocalFrame >= 0 &&
      sceneLocalFrame < 8 &&
      scene.id !== "scene_01"
    ) {
      const bump = interpolate(sceneLocalFrame, [0, 8], [1.04, 1.0], {
        extrapolateRight: "clamp",
      });
      cameraScale *= bump;
    }
  }

  // Color grade + vignette from active scene
  const colorFilter = scene?.color_grade
    ? buildColorFilter(scene.color_grade)
    : "none";
  const vignetteIntensity = scene?.vignette ?? 0.15;

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {/* Layer 0: Source video with camera movement + color grade */}
      <AbsoluteFill style={{ overflow: "hidden" }}>
        <OffthreadVideo
          src={staticFile(edl.meta.source_video)}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            transform: `scale(${cameraScale})`,
            transformOrigin: cameraOrigin,
            filter: colorFilter,
          }}
        />
      </AbsoluteFill>

      {/* Layer 1: Scene transitions */}
      <SceneTransitions scenes={edl.scenes} />

      {/* Layer 2: Per-scene vignette */}
      <Vignette intensity={vignetteIntensity} />

      {/* Layer 3: Film grain */}
      <FilmGrain opacity={0.06} />

      {/* Layer 4: Egyptian-styled captions */}
      {captions.length > 0 && <CaptionLayer captions={captions} />}
    </AbsoluteFill>
  );
};

// ---------- Metadata Calculator ----------

export const calculatePostProdMetadata = async () => {
  const res = await fetch(staticFile("vsl_postprod_edl.json"));
  const edl = (await res.json()) as PostProdEDL;

  const totalFrames = Math.round(edl.meta.total_duration_s * edl.meta.fps);

  return {
    props: { edl },
    durationInFrames: totalFrames,
    fps: edl.meta.fps,
    width: edl.meta.width,
    height: edl.meta.height,
  };
};
