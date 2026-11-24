# Run with: colab exec -s ltx -f object_info_image.py
# Prints the input specs of the nodes used by build_image_workflow.py (from /object_info).
import json
import urllib.request

info = json.load(urllib.request.urlopen("http://127.0.0.1:8188/object_info"))
want = ["UnetLoaderGGUF", "UNETLoader", "CLIPLoader", "VAELoader", "LoraLoaderModelOnly",
        "ModelSamplingAuraFlow", "CFGNorm", "TextEncodeQwenImageEditPlus", "ReferenceLatent",
        "FluxKontextMultiReferenceLatentMethod", "ModelPatchLoader", "QwenImageDiffsynthControlnet",
        "ZImageFunControlnet", "KSampler", "ImageScale", "SaveImage", "VAEEncode"]
for k in want:
    if k not in info:
        print("MISSING", k)
        continue
    print("==", k)
    for sect in ("required", "optional"):
        for name, spec in info[k]["input"].get(sect, {}).items():
            print("   ", sect[0], name, json.dumps(spec)[:240])
print("other zimage/controlnet nodes:", [k for k in info if "ZImage" in k or "Diffsynth" in k or "Fun" in k])
