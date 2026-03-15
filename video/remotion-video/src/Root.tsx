import { Composition, staticFile } from "remotion";
import {
  CaptionedVideo,
  calculateCaptionedVideoMetadata,
  captionedVideoSchema,
} from "./CaptionedVideo";
import { SceneWithAudio, AudioLayer } from "./SceneWithAudio";
import {
  VSLPostProduction,
  calculatePostProdMetadata,
} from "./VSLPostProduction";
import { SCENE_AUDIO } from "./audioDesigns";
import { SCENE_MANIFEST } from "./sceneManifest";
import {
  UniversalComposition,
  calculateUniversalMetadata,
} from "./UniversalComposition";
import { edlSchema } from "./types";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="CaptionedVideo"
        component={CaptionedVideo}
        calculateMetadata={calculateCaptionedVideoMetadata}
        schema={captionedVideoSchema}
        width={1080}
        height={1920}
        defaultProps={{
          src: staticFile("sample-video.mp4"),
        }}
      />
      {/* All VSL scenes with audio from audioDesigns.ts (including v2/v3 variants) */}
      {SCENE_MANIFEST.map((scene) => (
        <Composition
          key={scene.compId}
          id={scene.compId}
          component={SceneWithAudio}
          width={scene.width}
          height={scene.height}
          fps={scene.fps}
          durationInFrames={scene.durationInFrames}
          defaultProps={{
            videoSrc: staticFile(scene.videoFile),
            layers: (SCENE_AUDIO[scene.id] ?? []) as AudioLayer[],
          }}
        />
      ))}
      <Composition
        id="VSLPostProduction"
        component={VSLPostProduction}
        calculateMetadata={calculatePostProdMetadata}
        width={1080}
        height={1920}
        defaultProps={{
          edl: {
            meta: {
              fps: 24,
              width: 1080,
              height: 1920,
              total_duration_s: 0,
              source_video: "",
              whisper_data: "",
            },
            scenes: [],
          },
        }}
      />
      {/* Universal EDL-driven composition — renders any format (VSL, ad, UGC) */}
      <Composition
        id="UniversalVSL"
        component={UniversalComposition}
        calculateMetadata={calculateUniversalMetadata}
        schema={edlSchema}
        width={1080}
        height={1920}
        fps={24}
        durationInFrames={100}
        defaultProps={{
          meta: {
            fps: 24,
            width: 1080,
            height: 1920,
            title: "Preview",
            format: "vsl" as const,
            caption_preset: "tiktok_bold" as const,
            platform_target: "generic" as const,
            render_quality: "preview" as const,
            version: 1,
          },
          voiceover: null,
          scenes: [
            {
              id: "preview_scene_1",
              clip_src: "sample-video.mp4",
              duration_s: 4,
              trim_start_s: 0,
              trim_end_s: 4,
              audio_type: "silent" as const,
              ambient_audio: [],
              transition_in: "hard_cut" as const,
              label: "Preview scene",
            },
          ],
          changelog: [],
        }}
      />
    </>
  );
};
