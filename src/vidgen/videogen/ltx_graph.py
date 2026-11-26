"""The ComfyUI API-format graph of the ``ltx-2.3-union-control`` workflow (LTX-2.3 IC-LoRA
Union Control), shared by the ``comfyui`` video provider and ``tools/colab/build_workflow.py``.

A translation of example_workflows/2.3/LTX-2.3_ICLoRA_Union_Control_Distilled.json
(ComfyUI-LTXVideo ced6bad), with these changes:

- loaders: UnetLoaderGGUF (distilled-1.1 Q5_K_M) instead of CheckpointLoaderSimple(dev) +
  LoraLoaderModelOnly(distilled-lora-384-1.1, 0.5); the transformer is already distilled;
- text encoder: core DualCLIPLoader(gemma fp8, embeddings_connectors, type ltxv);
- VAEs: VAELoaderKJ for the video and audio VAE files;
- the control video is prepared outside the graph at the output size and length (no
  GetImageSize / ResizeImageMaskNode chain);
- output through VHS_VideoCombine (h264 mp4).

With a sheet (``sheet_file``, a stylesheet picture at the output size) the graph is the one of
trial run T2c (2026-11-25): LTX Multi IC-LoRA (comfyui-hrnodes, class ``LTXMultiICLoRA``) loads
the Ingredients IC-LoRA (LoRA a, guide 0) and the Union Control IC-LoRA (LoRA b, guide 1) and
routes each to its own LTXAddVideoICLoRAGuide: first the sheet repeated to the clip's frame count
(RepeatImageBatch; strength 1, frame 0), then the control video. ComfyUI must run with
``--disable-comfy-compiler`` (with the compiler on, the routing node's first step never ends).

Standard library only, no vidgen imports: the tools script loads this file by its path.
"""

from __future__ import annotations

PROMPT = ("a grey glider flies low over a rough open sea and banks gently, the chase camera "
          "following close behind. Real 35 mm aerial footage shot from a chase plane: natural "
          "daylight, real atmosphere and haze, real waves, spray and whitecaps, fine film grain; "
          "photographic, not computer graphics")
NEGATIVE = "pc game, console game, video game, cartoon, childish, ugly"
SIGMAS = "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"
W, H, FRAMES, FPS, SEED = 960, 512, 121, 24, 42
FIRST_FRAME = "first_frame_960x512.png"
UNION_LORA = "ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors"
INGREDIENTS_LORA = "ltx-2.3-22b-ic-lora-ingredients-0.9.safetensors"


def graph(control_file: str, prefix: str, use_first_frame: bool,
          guide_strength: float = 1.0, lora_strength: float = 1.0,
          second_control_file: str | None = None, first_frame_strength: float = 1.0,
          prompt: str = PROMPT, negative: str = NEGATIVE, width: int = W, height: int = H,
          frames: int = FRAMES, fps: int = FPS, seed: int = SEED,
          first_frame_file: str = FIRST_FRAME, with_audio: bool = True, sheet_file: str | None = None,
          text_encoder: str = "cpu") -> dict:
    """Return the API-format prompt graph for one run.

    second_control_file: chain a second LTXAddVideoICLoRAGuide (node 31) after the first,
    so two control videos (e.g. depth + canny) guide the same generation.
    width and height must be multiples of 64 (the ref0.5 LoRA halves the guide), frames 8k+1.
    with_audio false: the model's own sound is not decoded and the clip is silent.
    sheet_file: a stylesheet picture at width x height, given with the control video (see the
    module docstring); not with second_control_file.
    text_encoder: "cpu" runs the text encoder (node 3) on the CPU and in RAM, so it takes no VRAM;
    "gpu" leaves it on ComfyUI's default device.
    """
    if width % 64 or height % 64:
        raise ValueError(f"width and height must be multiples of 64, not {width}x{height}")
    if (frames - 1) % 8:
        raise ValueError(f"frames must be 8k+1 (e.g. 121), not {frames}")
    if text_encoder not in ("cpu", "gpu"):
        raise ValueError(f"text_encoder must be cpu or gpu, not {text_encoder!r}")
    if sheet_file and second_control_file:
        raise ValueError("a sheet goes with one control video, not two")
    g = {
        "1": {"class_type": "UnetLoaderGGUF",
              "inputs": {"unet_name": "ltx-2.3-22b-distilled-1.1-Q5_K_M.gguf"}},
        "2": {"class_type": "LTXICLoRALoaderModelOnly",
              "inputs": {"model": ["1", 0],
                         "lora_name": UNION_LORA,
                         "strength_model": lora_strength}},
        "3": {"class_type": "DualCLIPLoader",
              "inputs": {"clip_name1": "gemma_3_12B_it_fp8_scaled.safetensors",
                         "clip_name2": "ltx-2.3-22b-distilled_embeddings_connectors.safetensors",
                         "type": "ltxv", "device": "cpu" if text_encoder == "cpu" else "default"}},
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
    if not with_audio:
        del g["25"]
        del g["26"]["inputs"]["audio"]
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
    if sheet_file:
        g["2"] = {"class_type": "LTXMultiICLoRA",
                  "inputs": {"model": ["1", 0], "ic_lora_count": 2, "noisy_blend": 1.0,
                             "lora_a": INGREDIENTS_LORA, "strength_a": 1.0, "guide_index_a": 0, "enable_a": True,
                             "lora_b": UNION_LORA, "strength_b": lora_strength, "guide_index_b": 1, "enable_b": True}}
        g["40"] = {"class_type": "LoadImage", "inputs": {"image": sheet_file}}
        g["41"] = {"class_type": "RepeatImageBatch", "inputs": {"image": ["40", 0], "amount": frames}}
        g["42"] = {"class_type": "LTXAddVideoICLoRAGuide",
                   "inputs": {**g["14"]["inputs"], "image": ["41", 0], "frame_idx": 0, "strength": 1.0,
                              "latent_downscale_factor": ["2", 1]}}
        g["14"]["inputs"].update(positive=["42", 0], negative=["42", 1], latent=["42", 2],
                                 latent_downscale_factor=["2", 2])
    return g
