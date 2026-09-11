import os
import json

def update_posters_cache(output_dir="output", cache_file="posters_cache.json"):
    posters = []
    if os.path.exists(output_dir):
        for fn in sorted(os.listdir(output_dir), reverse=True):
            if fn.lower().endswith((".jpg", ".png", ".jpeg", ".webp")):
                fp = os.path.join(output_dir, fn)
                posters.append({
                    "filename": fn,
                    "url": f"output/{fn}",
                    "download_url": f"https://raw.githubusercontent.com/aashuthapa2023-sudo/autoimgpost/main/output/{fn}",
                    "size": os.path.getsize(fp),
                    "modified": int(os.path.getmtime(fp))
                })

    data = {
        "count": len(posters),
        "posters": posters
    }
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Updated {cache_file} with {len(posters)} posters.")
    return data

if __name__ == "__main__":
    update_posters_cache()
