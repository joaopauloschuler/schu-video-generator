"""Build the ComfyUI API-format graphs that make a photoreal version of frame 0.

Two routes (both models ungated on Hugging Face; files from setup_image.sh):
  qwen    Qwen-Image-Edit-2511 (GGUF Q4_K_M) + the 4-step Lightning LoRA: an instruction edit
          ("make this a real photo, keep everything in place"); the input frame is the reference
          latent and sets the output size, so the layout stays.
  zimage  Z-Image-Turbo + Fun ControlNet Union 2.1 (canny or depth of frame 0) as img2img from
          frame 0 at DENOISE < 1.

  python build_image_workflow.py qwen --run qwen_a --out workflow_qwen_a.json [--seed 42]
      [--denoise 1.0] [--prompt-file p.txt]
  python build_image_workflow.py zimage --run zi_canny --control ff_canny.png --strength 0.8
      --denoise 0.7 --out workflow_zi_canny.json
Inputs (in ComfyUI/input, from prep_image_inputs.py): ff_up.png (frame 0 at 1440x768) and the
control image. Output: ComfyUI/output/<run>_00001_.png, scaled back to 960x512 (--width/--height).
"""
import argparse
import json
from pathlib import Path

# Prompt C of the test (qwen_c, the chosen frame). Prompt A (keep everything, "make the sea real
# ocean water") kept the CG ripple pattern: name the CG pattern and ask for it to be replaced.
QWEN_PROMPT = (
    "Turn this computer-graphics render into a real photograph taken from a chase plane. "
    "Do not move or resize anything: the aircraft's position, size, angle and outline, the "
    "horizon line and the bright sun glint on the water must stay exactly where they are. "
    "Replace the regular, repeating computer-generated ripple pattern of the water with real, "
    "irregular open-ocean waves: swells of different sizes, wind chop, a few small whitecaps, "
    "and real sunlight sparkling on the water. Add real atmospheric haze over the horizon. "
    "Make the aircraft a real grey jet glider with painted metal panels, panel lines and subtle "
    "wear. Real 35 mm aerial photograph, natural colours, not CGI.")
ZIMAGE_PROMPT = (
    "Real aerial photograph from a chase plane: a small grey jet glider seen from behind and "
    "above, flying low over the open ocean in the late afternoon. Real sea water with natural "
    "waves and small whitecaps, bright sun glint sparkling on the water to the right, light "
    "haze over a straight flat horizon, pale sky. Painted metal aircraft with panel lines, two "
    "engine nozzles, red wing-tip lights. 35 mm photo, natural colours, sharp, photographic.")
NEGATIVE_ZI = "cgi, 3d render, video game, cartoon, illustration, painting, blurry"


def qwen_graph(run: str, prompt: str, seed: int, denoise: float, width: int, height: int,
               steps: int, lora: bool) -> dict:
    """Qwen-Image-Edit-2511 edit of ff_up.png; output scaled to width x height."""
    model = ["1", 0]
    g: dict = {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "qwen-image-edit-2511-Q4_K_M.gguf"}},
        "5": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": "qwen_2.5_vl_7b_fp8_scaled.safetensors", "type": "qwen_image", "device": "default"}},
        "6": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "7": {"class_type": "LoadImage", "inputs": {"image": "ff_up.png"}},
        "8": {"class_type": "VAEEncode", "inputs": {"pixels": ["7", 0], "vae": ["6", 0]}},
        "9": {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {
            "clip": ["5", 0], "prompt": prompt, "image1": ["7", 0]}},
        "10": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["9", 0], "latent": ["8", 0]}},
        "11": {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {
            "clip": ["5", 0], "prompt": "", "image1": ["7", 0]}},
        "12": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["11", 0], "latent": ["8", 0]}},
        "13": {"class_type": "FluxKontextMultiReferenceLatentMethod", "inputs": {
            "conditioning": ["10", 0], "reference_latents_method": "index_timestep_zero"}},
        "14": {"class_type": "FluxKontextMultiReferenceLatentMethod", "inputs": {
            "conditioning": ["12", 0], "reference_latents_method": "index_timestep_zero"}},
    }
    if lora:
        g["2"] = {"class_type": "LoraLoaderModelOnly", "inputs": {
            "model": model, "strength_model": 1.0,
            "lora_name": "Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors"}}
        model = ["2", 0]
    g["3"] = {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": model, "shift": 3.1}}
    g["4"] = {"class_type": "CFGNorm", "inputs": {"model": ["3", 0], "strength": 1.0}}
    g["15"] = {"class_type": "KSampler", "inputs": {
        "model": ["4", 0], "seed": seed, "steps": steps, "cfg": 1.0 if lora else 4.0,
        "sampler_name": "euler", "scheduler": "simple", "positive": ["13", 0],
        "negative": ["14", 0], "latent_image": ["8", 0], "denoise": denoise}}
    return _tail(g, "15", "6", run, width, height)


def zimage_graph(run: str, prompt: str, seed: int, denoise: float, width: int, height: int,
                 control: str, strength: float, steps: int) -> dict:
    """Z-Image-Turbo + Fun ControlNet Union 2.1, img2img from ff_up.png."""
    g: dict = {
        "1": {"class_type": "UNETLoader", "inputs": {
            "unet_name": "z_image_turbo_bf16.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": "qwen_3_4b.safetensors", "type": "lumina2", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "4": {"class_type": "ModelPatchLoader", "inputs": {
            "name": "Z-Image-Turbo-Fun-Controlnet-Union-2.1-8steps.safetensors"}},
        "5": {"class_type": "LoadImage", "inputs": {"image": control}},
        "6": {"class_type": "ZImageFunControlnet", "inputs": {
            "model": ["1", 0], "model_patch": ["4", 0], "vae": ["3", 0], "image": ["5", 0],
            "strength": strength}},
        "7": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["6", 0], "shift": 3.0}},
        "8": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "9": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": NEGATIVE_ZI}},
        "10": {"class_type": "LoadImage", "inputs": {"image": "ff_up.png"}},
        "11": {"class_type": "VAEEncode", "inputs": {"pixels": ["10", 0], "vae": ["3", 0]}},
        "15": {"class_type": "KSampler", "inputs": {
            "model": ["7", 0], "seed": seed, "steps": steps, "cfg": 1.0,
            "sampler_name": "res_multistep", "scheduler": "simple", "positive": ["8", 0],
            "negative": ["9", 0], "latent_image": ["11", 0], "denoise": denoise}},
    }
    return _tail(g, "15", "3", run, width, height)


def _tail(g: dict, sampler: str, vae: str, run: str, width: int, height: int) -> dict:
    """Decode, scale to the LTX size and save as <run>_00001_.png."""
    g["20"] = {"class_type": "VAEDecode", "inputs": {"samples": [sampler, 0], "vae": [vae, 0]}}
    g["21"] = {"class_type": "ImageScale", "inputs": {
        "image": ["20", 0], "upscale_method": "lanczos", "width": width, "height": height,
        "crop": "disabled"}}
    g["22"] = {"class_type": "SaveImage", "inputs": {"images": ["21", 0], "filename_prefix": run}}
    g["23"] = {"class_type": "SaveImage", "inputs": {"images": ["20", 0], "filename_prefix": run + "_full"}}
    return g


def main() -> None:
    """Parse the arguments and write one graph."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("route", choices=["qwen", "zimage"])
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--denoise", type=float)
    ap.add_argument("--steps", type=int)
    ap.add_argument("--no-lora", action="store_true", help="qwen: without Lightning (cfg 4)")
    ap.add_argument("--control", default="ff_canny.png", help="zimage: control image in input/")
    ap.add_argument("--strength", type=float, default=0.8, help="zimage: controlnet strength")
    ap.add_argument("--prompt-file", type=Path)
    ap.add_argument("--width", type=int, default=960)
    ap.add_argument("--height", type=int, default=512)
    a = ap.parse_args()
    prompt = a.prompt_file.read_text(encoding="utf-8").strip() if a.prompt_file else None
    if a.route == "qwen":
        steps = a.steps or (20 if a.no_lora else 4)
        g = qwen_graph(a.run, prompt or QWEN_PROMPT, a.seed, a.denoise or 1.0, a.width, a.height,
                       steps, not a.no_lora)
    else:
        g = zimage_graph(a.run, prompt or ZIMAGE_PROMPT, a.seed, a.denoise or 0.7, a.width,
                         a.height, a.control, a.strength, a.steps or 8)
    a.out.write_text(json.dumps(g, indent=1), encoding="utf-8")
    print("wrote", a.out)


main()
