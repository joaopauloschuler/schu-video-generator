# Run with: colab exec -s ltx -f object_info.py
# Prints the input specs of the nodes used by the workflow (from ComfyUI's /object_info),
# and saves the full object_info to /content/object_info.json.
import json
import urllib.request

info = json.load(urllib.request.urlopen("http://127.0.0.1:8188/object_info"))
json.dump(info, open("/content/object_info.json", "w"))
want = ["UnetLoaderGGUF", "DualCLIPLoader", "VAELoaderKJ", "LTXICLoRALoaderModelOnly",
        "LTXAddVideoICLoRAGuide", "LTXVImgToVideoConditionOnly", "LTXVTiledVAEDecode",
        "LTXVEmptyLatentAudio", "EmptyLTXVLatentVideo", "LTXVConditioning", "LTXVCropGuides",
        "LTXVConcatAVLatent", "LTXVSeparateAVLatent", "LTXVAudioVAEDecode", "ManualSigmas",
        "KSamplerSelect", "CFGGuider", "RandomNoise", "SamplerCustomAdvanced", "CreateVideo",
        "SaveVideo", "LoadVideo", "GetVideoComponents", "LoadImage", "ResizeImageMaskNode",
        "VHS_LoadVideo", "VHS_VideoCombine", "LTXAVTextEncoderLoader", "LTXFloatToInt"]
for k in want:
    if k not in info:
        print("MISSING", k)
        continue
    n = info[k]
    print("==", k, "->", n.get("output"), n.get("output_name"))
    for sect in ("required", "optional"):
        for name, spec in n["input"].get(sect, {}).items():
            s = json.dumps(spec)
            print("   ", sect[0], name, s[:300])
