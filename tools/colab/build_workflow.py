"""Build ComfyUI API-format graphs for the LTX-2.3 IC-LoRA Union Control runs.

Faithful translation of example_workflows/2.3/LTX-2.3_ICLoRA_Union_Control_Distilled.json
(ComfyUI-LTXVideo ced6bad), with these changes:
  - loaders: UnetLoaderGGUF (distilled-1.1 Q5_K_M) instead of CheckpointLoaderSimple(dev) +
    LoraLoaderModelOnly(distilled-lora-384-1.1, 0.5); the transformer is already distilled.
  - text encoder: core DualCLIPLoader(gemma fp8, embeddings_connectors, type ltxv)
    instead of LTXAVTextEncoderLoader(gemma, full ckpt).
  - VAEs: VAELoaderKJ for video and audio VAE files (as in unsloth's own GGUF workflow).
  - control preprocessing done outside the graph (exact depth from three.js; canny with
    OpenCV 92/200 at 512 px) and the size fixed at 960x512 x 121 frames instead of the
    GetImageSize / ResizeImageMaskNode(multiple of 64) chain; the result is the same.
  - output via VHS_VideoCombine (h264 mp4) instead of CreateVideo + SaveVideo.
Usage (local, plain Python 3.10+, no dependencies):
  python build_workflow.py --experiment [--out-dir DIR]
      writes the seven workflow_<run>.json of the 2026-11-24 test (byte-identical to the ones run)
  python build_workflow.py --run NAME --control canny_121_960x512.mp4 [--second-control FILE]
      [--first-frame first_frame_960x512.png | --no-first-frame] [--first-frame-strength 0.5]
      [--prompt TEXT | --prompt-file FILE] [--width 960 --height 512 --frames 121 --fps 24 --seed 42]
      writes workflow_NAME.json (output prefix ltx_NAME). File names are names inside
      ComfyUI/input/ on the VM, not local paths.
"""
import argparse
import json
from pathlib import Path

PROMPT = ("a grey glider flies low over a rough open sea and banks gently, the chase camera "
          "following close behind. Real 35 mm aerial footage shot from a chase plane: natural "
          "daylight, real atmosphere and haze, real waves, spray and whitecaps, fine film grain; "
          "photographic, not computer graphics")
NEGATIVE = "pc game, console game, video game, cartoon, childish, ugly"
SIGMAS = "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"
W, H, FRAMES, FPS, SEED = 960, 512, 121, 24, 42
FIRST_FRAME = "first_frame_960x512.png"


def graph(control_file: str, prefix: str, use_first_frame: bool,
          guide_strength: float = 1.0, lora_strength: float = 1.0,
          second_control_file: str | None = None, first_frame_strength: float = 1.0,
          prompt: str = PROMPT, negative: str = NEGATIVE, width: int = W, height: int = H,
          frames: int = FRAMES, fps: int = FPS, seed: int = SEED,
          first_frame_file: str = FIRST_FRAME) -> dict:
    """Return the API-format prompt graph for one run.

    second_control_file: chain a second LTXAddVideoICLoRAGuide (node 31) after the first,
    so two control videos (e.g. depth + canny) guide the same generation.
    width and height must be multiples of 64 (the ref0.5 LoRA halves the guide), frames 8k+1.
    """
    if width % 64 or height % 64:
        raise SystemExit(f"width and height must be multiples of 64, not {width}x{height}")
    if (frames - 1) % 8:
        raise SystemExit(f"frames must be 8k+1 (e.g. 121), not {frames}")
    g = {
        "1": {"class_type": "UnetLoaderGGUF",
              "inputs": {"unet_name": "ltx-2.3-22b-distilled-1.1-Q5_K_M.gguf"}},
        "2": {"class_type": "LTXICLoRALoaderModelOnly",
              "inputs": {"model": ["1", 0],
                         "lora_name": "ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors",
                         "strength_model": lora_strength}},
        "3": {"class_type": "DualCLIPLoader",
              "inputs": {"clip_name1": "gemma_3_12B_it_fp8_scaled.safetensors",
                         "clip_name2": "ltx-2.3-22b-distilled_embeddings_connectors.safetensors",
                         "type": "ltxv", "device": "default"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["3", 0]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["3", 0]}},
        "6": {"class_type": "LTXVConditioning",
              "inputs": {"positive": ["4", 0], "negative": ["5", 0], "frame_rate": float(fps)}},
        "7": {"class_type": "VAELoaderKJ",
              "inputs": {"vae_name": "ltx-2.3-22b-distilled_video_vae.safetensors",
                         "device": "main_device", "weight_dtype": "bf16"}},
        "8": {"class_type": "VAELoaderKJ",
              "inputs": {"vae_name": "ltx-2.3-22b-distilled_audio_vae.safetensors",
                         "device": "main_device", "weight_dtype": "bf16"}},
        "9": {"class_type": "LoadImage", "inputs": {"image": first_frame_file}},
        "10": {"class_type": "LoadVideo", "inputs": {"file": control_file}},
        "11": {"class_type": "GetVideoComponents", "inputs": {"video": ["10", 0]}},
        "12": {"class_type": "EmptyLTXVLatentVideo",
               "inputs": {"width": width, "height": height, "length": frames, "batch_size": 1}},
        "13": {"class_type": "LTXVImgToVideoConditionOnly",
               "inputs": {"vae": ["7", 0], "image": ["9", 0], "latent": ["12", 0],
                          "strength": first_frame_strength, "bypass": not use_first_frame}},
        "14": {"class_type": "LTXAddVideoICLoRAGuide",
               "inputs": {"positive": ["6", 0], "negative": ["6", 1], "vae": ["7", 0],
                          "latent": ["13", 0], "image": ["11", 0], "frame_idx": 0,
                          "strength": guide_strength, "latent_downscale_factor": ["2", 1],
                          "crop": "disabled", "use_tiled_encode": False,
                          "tile_size": 256, "tile_overlap": 64}},
        "15": {"class_type": "LTXVEmptyLatentAudio",
               "inputs": {"frames_number": frames, "frame_rate": fps, "batch_size": 1,
                          "audio_vae": ["8", 0]}},
        "16": {"class_type": "LTXVConcatAVLatent",
               "inputs": {"video_latent": ["14", 2], "audio_latent": ["15", 0]}},
        "17": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "18": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler_ancestral_cfg_pp"}},
        "19": {"class_type": "ManualSigmas", "inputs": {"sigmas": SIGMAS}},
        "20": {"class_type": "CFGGuider",
               "inputs": {"model": ["2", 0], "positive": ["14", 0], "negative": ["14", 1],
                          "cfg": 1.0}},
        "21": {"class_type": "SamplerCustomAdvanced",
               "inputs": {"noise": ["17", 0], "guider": ["20", 0], "sampler": ["18", 0],
                          "sigmas": ["19", 0], "latent_image": ["16", 0]}},
        "22": {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["21", 0]}},
        "23": {"class_type": "LTXVCropGuides",
               "inputs": {"positive": ["14", 0], "negative": ["14", 1], "latent": ["22", 0]}},
        "24": {"class_type": "LTXVTiledVAEDecode",
               "inputs": {"vae": ["7", 0], "latents": ["23", 2], "horizontal_tiles": 2,
                          "vertical_tiles": 2, "overlap": 6, "last_frame_fix": False,
                          "working_device": "auto", "working_dtype": "auto"}},
        "25": {"class_type": "LTXVAudioVAEDecode",
               "inputs": {"samples": ["22", 1], "audio_vae": ["8", 0]}},
        "26": {"class_type": "VHS_VideoCombine",
               "inputs": {"images": ["24", 0], "audio": ["25", 0], "frame_rate": float(fps),
                          "loop_count": 0, "filename_prefix": prefix,
                          "format": "video/h264-mp4", "pix_fmt": "yuv420p", "crf": 16,
                          "save_metadata": True, "trim_to_audio": False,
                          "pingpong": False, "save_output": True}},
    }
    if second_control_file:
        g["30"] = {"class_type": "LoadVideo", "inputs": {"file": second_control_file}}
        g["29"] = {"class_type": "GetVideoComponents", "inputs": {"video": ["30", 0]}}
        g["31"] = {"class_type": "LTXAddVideoICLoRAGuide",
                   "inputs": {**g["14"]["inputs"], "positive": ["14", 0], "negative": ["14", 1],
                              "latent": ["14", 2], "image": ["29", 0]}}
        for nid in ("16",):
            g[nid]["inputs"]["video_latent"] = ["31", 2]
        for nid in ("20", "23"):
            g[nid]["inputs"]["positive"] = ["31", 0]
            g[nid]["inputs"]["negative"] = ["31", 1]
    return g


RUNS = {
    "depth": dict(control_file="depth_121_960x512.mp4", prefix="ltx_depth", use_first_frame=True),
    "canny": dict(control_file="canny_121_960x512.mp4", prefix="ltx_canny", use_first_frame=True),
    "depth_noff": dict(control_file="depth_121_960x512.mp4", prefix="ltx_depth_noff",
                       use_first_frame=False),
    "depth_canny": dict(control_file="depth_121_960x512.mp4", prefix="ltx_depth_canny",
                        use_first_frame=True, second_control_file="canny_121_960x512.mp4"),
    "canny_noff": dict(control_file="canny_121_960x512.mp4", prefix="ltx_canny_noff",
                       use_first_frame=False),
    "depth_canny_noff": dict(control_file="depth_121_960x512.mp4", prefix="ltx_depth_canny_noff",
                             use_first_frame=False,
                             second_control_file="canny_121_960x512.mp4"),
    "depth_canny_ff05": dict(control_file="depth_121_960x512.mp4", prefix="ltx_depth_canny_ff05",
                             use_first_frame=True, first_frame_strength=0.5,
                             second_control_file="canny_121_960x512.mp4"),
}

def main() -> None:
    """Write the experiment's graphs, or one graph from the command line."""
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--experiment", action="store_true", help="write the seven graphs of the test")
    p.add_argument("--out-dir", type=Path, default=Path.cwd())
    p.add_argument("--run", help="run name: writes workflow_<run>.json, output prefix ltx_<run>")
    p.add_argument("--control", help="control video in ComfyUI/input/ (full output size)")
    p.add_argument("--second-control", help="a second control video, chained as a second guide")
    p.add_argument("--first-frame", default=FIRST_FRAME, help="first-frame picture in ComfyUI/input/")
    p.add_argument("--no-first-frame", action="store_true", help="bypass the first-frame node")
    p.add_argument("--first-frame-strength", type=float, default=1.0)
    p.add_argument("--guide-strength", type=float, default=1.0)
    p.add_argument("--lora-strength", type=float, default=1.0)
    p.add_argument("--prompt", default=PROMPT)
    p.add_argument("--prompt-file", type=Path, help="read the prompt from this UTF-8 text file")
    p.add_argument("--negative", default=NEGATIVE)
    p.add_argument("--width", type=int, default=W)
    p.add_argument("--height", type=int, default=H)
    p.add_argument("--frames", type=int, default=FRAMES)
    p.add_argument("--fps", type=int, default=FPS)
    p.add_argument("--seed", type=int, default=SEED)
    a = p.parse_args()
    a.out_dir.mkdir(parents=True, exist_ok=True)
    if a.experiment:
        runs = RUNS
    elif a.run and a.control:
        prompt = a.prompt_file.read_text(encoding="utf-8").strip() if a.prompt_file else a.prompt
        runs = {a.run: dict(control_file=a.control, prefix=f"ltx_{a.run}",
                            use_first_frame=not a.no_first_frame,
                            second_control_file=a.second_control,
                            first_frame_strength=a.first_frame_strength,
                            guide_strength=a.guide_strength, lora_strength=a.lora_strength,
                            prompt=prompt, negative=a.negative, width=a.width, height=a.height,
                            frames=a.frames, fps=a.fps, seed=a.seed,
                            first_frame_file=a.first_frame)}
    else:
        p.error("give --experiment, or --run and --control")
    for name, kw in runs.items():
        path = a.out_dir / f"workflow_{name}.json"
        path.write_text(json.dumps(graph(**kw), indent=1), encoding="utf-8")
        print("wrote", path)


if __name__ == "__main__":
    main()
