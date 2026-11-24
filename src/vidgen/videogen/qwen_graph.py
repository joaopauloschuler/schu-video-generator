"""The ComfyUI API-format graphs that make a photoreal version of a shot's first frame
(``first_frame: restyled``, DESIGN.md §113.21), shared by vidgen and
``tools/colab/build_image_workflow.py`` (which loads this file by its path).

Two routes (both models ungated on Hugging Face; files from tools/colab/setup_image.sh):

- :func:`qwen_graph`: Qwen-Image-Edit-2511 (GGUF Q4_K_M) + the 4-step Lightning LoRA, an
  instruction edit ("make this a real photo, keep everything in place"); the input picture is
  the reference latent and sets the output size, so the layout stays. vidgen's restyled frame;
- :func:`zimage_graph`: Z-Image-Turbo + Fun ControlNet Union 2.1 (canny or depth of frame 0) as
  img2img at ``denoise`` < 1 (tried in Step 405; it changed the aircraft's shape).

The input picture is the frame at 1.5x the output size (1440x768 for 960x512; multiples of 16);
the result is scaled back to ``width`` x ``height`` (Lanczos). Standard library only.
"""

from __future__ import annotations

#: vidgen's default edit prompt (``first_frame_prompt:`` replaces it): :data:`QWEN_PROMPT`'s wording
#: made general: name the usual computer-graphics giveaways and ask for real, irregular detail.
RESTYLE_PROMPT = (
    "Turn this computer-graphics render into a real photograph. "
    "Do not move, resize, add or remove anything: every object's position, size, angle and "
    "outline, the horizon line and the bright highlights must stay exactly where they are; add "
    "no new objects, land, rocks or plants. "
    "Replace the regular, repeating computer-generated patterns and textures (a uniform ripple "
    "pattern on water, tiled ground or foliage) with real, irregular natural detail of different "
    "sizes; water becomes real open water with swells, wind chop and a few small whitecaps. "
    "Make smooth plastic-looking surfaces real materials with fine texture, panel lines and "
    "subtle wear, and soften too-clean, perfectly sharp edges. Real sunlight with natural "
    "highlights, real atmospheric haze in the distance. "
    "Real 35 mm photograph, natural colours, not CGI.")
#: The input picture's size over the output size.
UPSCALE = 1.5
#: The input picture of the tools script's runs (prep_image_inputs.py).
INPUT = "ff_up.png"

# Prompt C of the Step 405 test (qwen_c, the chosen frame; the tools script's default). Prompt A (keep everything, "make the sea real
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


def qwen_graph(run: str, prompt: str = RESTYLE_PROMPT, seed: int = 42, denoise: float = 1.0, width: int = 960, height: int = 512,
               steps: int = 4, lora: bool = True, image: str = INPUT, full: bool = True) -> dict:
    """Qwen-Image-Edit-2511 edit of ``image`` (in ComfyUI's input folder); output ``<run>_00001_.png``
    scaled to ``width`` x ``height`` (``full``: also ``<run>_full_00001_.png`` at the input's size)."""
    model = ["1", 0]
    g: dict = {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "qwen-image-edit-2511-Q4_K_M.gguf"}},
        "5": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": "qwen_2.5_vl_7b_fp8_scaled.safetensors", "type": "qwen_image", "device": "default"}},
        "6": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "7": {"class_type": "LoadImage", "inputs": {"image": image}},
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
    return _tail(g, "15", "6", run, width, height, full)


def zimage_graph(run: str, prompt: str, seed: int, denoise: float, width: int, height: int,
                 control: str, strength: float, steps: int, image: str = INPUT) -> dict:
    """Z-Image-Turbo + Fun ControlNet Union 2.1, img2img from ``image``."""
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
        "10": {"class_type": "LoadImage", "inputs": {"image": image}},
        "11": {"class_type": "VAEEncode", "inputs": {"pixels": ["10", 0], "vae": ["3", 0]}},
        "15": {"class_type": "KSampler", "inputs": {
            "model": ["7", 0], "seed": seed, "steps": steps, "cfg": 1.0,
            "sampler_name": "res_multistep", "scheduler": "simple", "positive": ["8", 0],
            "negative": ["9", 0], "latent_image": ["11", 0], "denoise": denoise}},
    }
    return _tail(g, "15", "3", run, width, height)


def _tail(g: dict, sampler: str, vae: str, run: str, width: int, height: int, full: bool = True) -> dict:
    """Decode, scale to the LTX size and save as <run>_00001_.png (``full``: also unscaled)."""
    g["20"] = {"class_type": "VAEDecode", "inputs": {"samples": [sampler, 0], "vae": [vae, 0]}}
    g["21"] = {"class_type": "ImageScale", "inputs": {
        "image": ["20", 0], "upscale_method": "lanczos", "width": width, "height": height,
        "crop": "disabled"}}
    g["22"] = {"class_type": "SaveImage", "inputs": {"images": ["21", 0], "filename_prefix": run}}
    if full:
        g["23"] = {"class_type": "SaveImage", "inputs": {"images": ["20", 0], "filename_prefix": run + "_full"}}
    return g


__all__ = ["INPUT", "QWEN_PROMPT", "RESTYLE_PROMPT", "UPSCALE", "ZIMAGE_PROMPT", "qwen_graph", "zimage_graph"]
