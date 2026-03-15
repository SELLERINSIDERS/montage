/**
 * UniversalComposition — EDL-driven composition for any format.
 *
 * Reads all parameters from EDL JSON props:
 * dimensions, fps, scenes with clip paths/durations, voiceover track, caption preset,
 * and optional intro/outro cards.
 *
 * Key behaviors:
 * - Clip audio always muted (voiceover is primary audio track)
 * - Playback rate clamped at 0.5 minimum
 * - Hard cuts only (crossfade transitions deferred)
 * - Voiceover spans full composition as continuous track
 * - CaptionLayer overlays word-level highlighting from Whisper data
 */
import React from "react";
import {
  AbsoluteFill,
  Audio,
  OffthreadVideo,
  Sequence,
  Series,
  staticFile,
  useVideoConfig,
} from "remotion";
import type { CalculateMetadataFunction } from "remotion";
import type { EDL, SceneEntry } from "./types";
import { CaptionLayer } from "./CaptionLayer";
import { IntroCard, OutroCard } from "./IntroOutroCards";

// ── Constants ──────────────────────────────────────────────────────

const MIN_PLAYBACK_RATE = 0.5;
const DEFAULT_CLIP_DURATION_S = 5.0;

// ── Calculate Metadata ─────────────────────────────────────────────

export const calculateUniversalMetadata: CalculateMetadataFunction<
  EDL
> = ({ props }) => {
  const { meta, scenes, intro, outro } = props;

  // Calculate total duration from all segments
  let totalDurationS = 0;

  if (intro) {
    totalDurationS += intro.duration_s;
  }

  for (const scene of scenes) {
    totalDurationS += scene.duration_s;
  }

  if (outro) {
    totalDurationS += outro.duration_s;
  }

  const durationInFrames = Math.max(1, Math.round(totalDurationS * meta.fps));

  return {
    fps: meta.fps,
    width: meta.width,
    height: meta.height,
    durationInFrames,
    props,
  };
};

// ── Scene Clip ─────────────────────────────────────────────────────

const SceneClip: React.FC<{
  scene: SceneEntry;
  durationInFrames: number;
}> = ({ scene, durationInFrames }) => {
  const { fps } = useVideoConfig();

  // Calculate usable clip frames (after trimming)
  const clipDurationS = scene.trim_end_s - scene.trim_start_s;
  const clipFrames = Math.round(
    (clipDurationS > 0 ? clipDurationS : DEFAULT_CLIP_DURATION_S) * fps,
  );

  // Calculate playback rate: slow clip to match scene duration
  // If scene duration > clip duration, slow down (clamp at 0.5x)
  // If scene duration <= clip duration, play at 1x
  let playbackRate = 1;
  if (scene.playback_rate_override !== undefined) {
    playbackRate = Math.max(MIN_PLAYBACK_RATE, scene.playback_rate_override);
  } else if (durationInFrames > clipFrames) {
    playbackRate = Math.max(MIN_PLAYBACK_RATE, clipFrames / durationInFrames);
  }

  return (
    <AbsoluteFill>
      <OffthreadVideo
        src={staticFile(scene.clip_src)}
        muted
        playbackRate={playbackRate}
        startFrom={Math.round(scene.trim_start_s * fps)}
        style={{ width: "100%", height: "100%" }}
      />

      {/* Ambient audio for scene_dominant or mixed scenes */}
      {(scene.audio_type === "scene_dominant" ||
        scene.audio_type === "mixed") &&
        scene.ambient_audio.map((audio, i) => {
          const delayFrames = Math.round((audio.delay_s ?? 0) * fps);
          return (
            <Sequence key={i} from={delayFrames}>
              <Audio
                src={staticFile(audio.src)}
                volume={audio.volume}
                loop={audio.loop}
              />
            </Sequence>
          );
        })}
    </AbsoluteFill>
  );
};

// ── Main Composition ───────────────────────────────────────────────

export const UniversalComposition: React.FC<EDL> = (edl) => {
  const { fps } = useVideoConfig();
  const { meta, scenes, voiceover, intro, outro } = edl;

  // Pre-calculate scene frame durations, ensuring they sum correctly
  const sceneFrameDurations = scenes.map((scene) =>
    Math.round(scene.duration_s * fps),
  );

  // Calculate intro/outro frame durations
  const introFrames = intro ? Math.round(intro.duration_s * fps) : 0;
  const outroFrames = outro ? Math.round(outro.duration_s * fps) : 0;

  return (
    <AbsoluteFill>
      {/* Scene timeline using Series for hard cuts */}
      <Series>
        {/* Optional intro card */}
        {intro && (
          <Series.Sequence durationInFrames={introFrames}>
            <IntroCard
              type={intro.type}
              durationS={intro.duration_s}
              logoSrc={intro.logo_src}
              text={intro.text}
              backgroundColor={intro.background_color}
            />
          </Series.Sequence>
        )}

        {/* Scene clips */}
        {scenes.map((scene, i) => (
          <Series.Sequence
            key={scene.id}
            durationInFrames={sceneFrameDurations[i]}
          >
            <SceneClip
              scene={scene}
              durationInFrames={sceneFrameDurations[i]}
            />
          </Series.Sequence>
        ))}

        {/* Optional outro card */}
        {outro && (
          <Series.Sequence durationInFrames={outroFrames}>
            <OutroCard
              type={outro.type}
              durationS={outro.duration_s}
              text={outro.text}
              url={outro.url}
              productImageSrc={outro.product_image_src}
              backgroundColor={outro.background_color}
            />
          </Series.Sequence>
        )}
      </Series>

      {/* Continuous voiceover spanning full composition */}
      {voiceover && (
        <Sequence from={introFrames}>
          <Audio
            src={staticFile(voiceover.src)}
            volume={voiceover.volume}
          />
        </Sequence>
      )}

      {/* Caption overlay spanning full composition (offset by intro) */}
      {voiceover?.whisper_data && (
        <Sequence from={introFrames}>
          <CaptionLayer
            whisperDataSrc={voiceover.whisper_data}
            presetId={meta.caption_preset}
            platformTarget={meta.platform_target}
          />
        </Sequence>
      )}
    </AbsoluteFill>
  );
};
