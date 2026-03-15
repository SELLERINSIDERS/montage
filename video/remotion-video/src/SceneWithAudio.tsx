import { Audio } from "@remotion/media";
import {
  AbsoluteFill,
  OffthreadVideo,
  Sequence,
  staticFile,
  useVideoConfig,
  interpolate,
} from "remotion";

export interface AudioLayer {
  src: string;
  volume: number;
  loop: boolean;
  delaySeconds?: number;
  fadeIn?: boolean;
}

export const SceneWithAudio: React.FC<{
  videoSrc: string;
  layers?: AudioLayer[];
}> = ({ videoSrc, layers }) => {
  const { fps, durationInFrames } = useVideoConfig();

  const defaultLayers: AudioLayer[] = [
    { src: "sfx/ocean_waves.mp3", volume: 0.75, loop: true },
    { src: "sfx/wind.mp3", volume: 0.4, loop: true },
    { src: "sfx/ship_creak.mp3", volume: 0.25, loop: true, delaySeconds: 0.5 },
  ];

  const audioLayers = layers ?? defaultLayers;

  return (
    <AbsoluteFill>
      <OffthreadVideo src={videoSrc} muted style={{ width: "100%", height: "100%" }} />

      {audioLayers.map((layer, i) => {
        const delayFrames = Math.round((layer.delaySeconds ?? 0) * fps);
        const audioElement = (
          <Audio
            key={i}
            src={staticFile(layer.src)}
            volume={(f) => {
              if (layer.fadeIn) {
                const fadeIn = interpolate(f, [0, fps], [0, layer.volume], {
                  extrapolateRight: "clamp",
                });
                const fadeOut = interpolate(
                  f + delayFrames,
                  [durationInFrames - fps, durationInFrames],
                  [layer.volume, 0],
                  { extrapolateLeft: "clamp" }
                );
                return Math.min(fadeIn, fadeOut);
              }
              return layer.volume;
            }}
            loop={layer.loop}
          />
        );

        if (delayFrames > 0) {
          return (
            <Sequence key={i} from={delayFrames}>
              {audioElement}
            </Sequence>
          );
        }
        return audioElement;
      })}
    </AbsoluteFill>
  );
};
