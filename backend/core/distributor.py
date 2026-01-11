from __future__ import annotations
import shutil
from pathlib import Path
from typing import Literal

JointMode = Literal["copy","combine"]

def distribute_plan(plan: list[dict], root: Path, joint_mode: JointMode = "copy", singletons: bool = True) -> dict:
    moved = copied = 0
    created_clusters: set[str] = set()

    for item in plan:
        img_path = Path(item["path"])
        clusters: list[int] = item.get("clusters", [])

        if not clusters:
            if singletons:
                target = root / "singletons" / img_path.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(img_path), str(target))
                moved += 1
            continue

        if len(clusters) == 1:
            cid = clusters[0]
            target = root / str(cid) / img_path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            created_clusters.add(str(cid))
            shutil.move(str(img_path), str(target))
            moved += 1
        else:
            if joint_mode == "copy":
                for cid in clusters:
                    target = root / str(cid) / img_path.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    created_clusters.add(str(cid))
                    shutil.copy2(str(img_path), str(target))
                    copied += 1
                img_path.unlink(missing_ok=True)
            else:
                name = "+".join(map(str, sorted(clusters)))
                target = root / name / img_path.name
                target.parent.mkdir(parents=True, exist_ok=True)
                created_clusters.add(name)
                shutil.move(str(img_path), str(target))
                moved += 1

    return {"moved": moved, "copied": copied, "clusters": len(created_clusters)}
